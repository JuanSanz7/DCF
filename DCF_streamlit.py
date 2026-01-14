# IMPORTANT: st.set_page_config must be the first Streamlit command
import streamlit as st
st.set_page_config(page_title="DCF Monte Carlo Valuation Tool", layout="wide")

import matplotlib.pyplot as plt
import io
import yfinance as yf
import json
import os
import shutil
import requests
from datetime import datetime
from pathlib import Path
from DCF_main import run_monte_carlo_simulation

# --- ANALYSIS STORAGE FUNCTIONS (MUST BE DEFINED FIRST) ---
# Use absolute path for better persistence
BASE_DIR = Path(__file__).parent.absolute()
ANALYSES_DIR = BASE_DIR / "saved_analyses"
ANALYSES_DIR.mkdir(exist_ok=True)
ANALYSES_INDEX_FILE = ANALYSES_DIR / "analyses_index.json"

def load_analyses_index():
    """Load the index of all saved analyses"""
    if ANALYSES_INDEX_FILE.exists():
        try:
            with open(ANALYSES_INDEX_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            # Don't show warning here as it might be called before Streamlit is ready
            return {}
    return {}

def get_user_name_from_index():
    """Get all unique user names from the index"""
    index = load_analyses_index()
    user_names = set()
    for ticker, analyses in index.items():
        for analysis_id, analysis_info in analyses.items():
            user_name = analysis_info.get('user_name')
            if user_name:
                user_names.add(user_name)
    return sorted(list(user_names))

def normalize_user_key(user_name: str) -> str:
    """Normalize a user name for matching (case-insensitive)."""
    if user_name is None:
        return ""
    # casefold() is stronger than lower() for international characters
    return str(user_name).strip().casefold()

def get_user_id_from_name(user_name):
    """Get or create a user ID for a given user name"""
    import hashlib
    # Create a consistent user_id from normalized name (deterministic hash)
    key = normalize_user_key(user_name)
    user_id = hashlib.md5(key.encode()).hexdigest()[:12]
    return user_id

def is_user_name_taken(user_name):
    """
    Check if a user has existing saved analyses (case-insensitive).

    NOTE: This is *not* an auth check; it only tells us whether this name
    matches any stored analyses.
    """
    key = normalize_user_key(user_name)
    if not key:
        return False
    idx = load_analyses_index()
    for _ticker, analyses in idx.items():
        for _analysis_id, info in analyses.items():
            info_key = info.get("user_key") or normalize_user_key(info.get("user_name", ""))
            if info_key == key:
                return True
    return False

def get_user_name():
    """Get the current user's name (must be set before use)"""
    return st.session_state.get('user_name', None)

def get_user_key():
    """Get the current user's normalized key (case-insensitive)."""
    key = st.session_state.get('user_key', None)
    if key:
        return key
    # Backward compatible: derive from user_name if present
    name = st.session_state.get('user_name', None)
    derived = normalize_user_key(name)
    if derived:
        st.session_state.user_key = derived
        return derived
    return None

def get_user_id():
    """Get the current user's ID (derived from name)"""
    return st.session_state.get("user_id", None)

def set_user_name(name):
    """Set the user name and load their existing analyses"""
    if not name or not name.strip():
        return False
    
    name = str(name).strip()
    user_key = normalize_user_key(name)
    user_id = get_user_id_from_name(user_key)
    
    # Store user info
    st.session_state.user_name = name
    st.session_state.user_key = user_key
    st.session_state.user_id = user_id
    st.session_state.user_initialized = True
    
    return True

def get_user_analyses_index(user_name=None):
    """Get analyses index filtered for a specific user (case-insensitive)."""
    if user_name is None:
        user_key = get_user_key()
        if not user_key:
            return {}
    else:
        user_key = normalize_user_key(user_name)
        if not user_key:
            return {}
    
    all_index = load_analyses_index()
    user_index = {}
    
    # Filter by user_key (preferred) or normalized user_name (backward compatible)
    for ticker, analyses in all_index.items():
        user_analyses = {}
        for analysis_id, analysis_info in analyses.items():
            info_key = analysis_info.get("user_key") or normalize_user_key(analysis_info.get("user_name", ""))
            if info_key == user_key:
                user_analyses[analysis_id] = analysis_info
        if user_analyses:
            user_index[ticker] = user_analyses
    
    return user_index

def count_user_analyses(user_name):
    """Count how many analyses a user has"""
    user_index = get_user_analyses_index(user_name)
    count = 0
    for ticker, analyses in user_index.items():
        count += len(analyses)
    return count

def save_analyses_index(index):
    """Save the index of all analyses with error handling"""
    try:
        # Create backup before saving
        if ANALYSES_INDEX_FILE.exists():
            backup_file = ANALYSES_INDEX_FILE.with_suffix('.json.bak')
            shutil.copy2(ANALYSES_INDEX_FILE, backup_file)
        
        # Save with atomic write (write to temp file first, then rename)
        temp_file = ANALYSES_INDEX_FILE.with_suffix('.json.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        
        # Atomic rename
        temp_file.replace(ANALYSES_INDEX_FILE)
        return True
    except Exception as e:
        st.error(f"Error saving analyses index: {e}")
        return False

def validate_analysis_files(analysis_id):
    """Check if analysis files still exist on disk"""
    analysis_dir = ANALYSES_DIR / analysis_id
    if not analysis_dir.exists():
        return False
    
    # Check for required files
    required_files = [
        analysis_dir / "results_plot.png",
        analysis_dir / "valuation_summary.json"
    ]
    
    return all(f.exists() for f in required_files)

def cleanup_orphaned_analyses(user_name=None):
    """Remove entries from index where files no longer exist (for current user only)"""
    if user_name is None:
        user_key = get_user_key()
        if not user_key:
            return False
    else:
        user_key = normalize_user_key(user_name)
        if not user_key:
            return False
    
    index = load_analyses_index()
    cleaned = False
    
    for ticker in list(index.keys()):
        for analysis_id in list(index[ticker].keys()):
            analysis_info = index[ticker][analysis_id]
            # Only clean up analyses belonging to this user
            info_key = analysis_info.get("user_key") or normalize_user_key(analysis_info.get("user_name", ""))
            if info_key == user_key:
                if not validate_analysis_files(analysis_id):
                    # File doesn't exist, remove from index
                    del index[ticker][analysis_id]
                    cleaned = True
        
        # Remove empty ticker entries
        if not index[ticker]:
            del index[ticker]
    
    if cleaned:
        save_analyses_index(index)
        return True
    return False

def save_analysis(ticker, company_name, valuation_summary, fig_es, fig_distribution_only, fig_sensitivity):
    """Save an analysis to disk with error handling"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    analysis_id = f"{ticker}_{timestamp}"
    analysis_dir = ANALYSES_DIR / analysis_id
    
    try:
        # Create directory
        analysis_dir.mkdir(exist_ok=True, parents=True)
        
        # Save only the results plot
        plot_path = analysis_dir / "results_plot.png"
        fig_es.savefig(plot_path, dpi=150, bbox_inches='tight')
        
        # Save valuation summary as JSON
        summary_path = analysis_dir / "valuation_summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(valuation_summary, f, indent=2, ensure_ascii=False)
        
        # Verify files were saved
        if not plot_path.exists() or not summary_path.exists():
            raise IOError("Failed to save analysis files")
        
        # Update index with user information
        user_name = get_user_name()
        if not user_name:
            raise ValueError("User name must be set before saving analyses")
        
        user_id = get_user_id()
        user_key = get_user_key() or normalize_user_key(user_name)
        index = load_analyses_index()
        if ticker not in index:
            index[ticker] = {}
        index[ticker][analysis_id] = {
            'company_name': company_name,
            'timestamp': timestamp,
            'date': valuation_summary['date'],
            'analysis_id': analysis_id,
            'path': str(analysis_dir.absolute()),  # Store absolute path
            'user_id': user_id,              # deterministic from user_key
            'user_key': user_key,            # case-insensitive match key
            'user_name': user_name           # display name (backward compatible)
        }
        
        if save_analyses_index(index):
            return analysis_id
        else:
            raise Exception("Failed to save index")
            
    except Exception as e:
        st.error(f"Error saving analysis: {e}")
        # Clean up partial save
        if analysis_dir.exists():
            try:
                shutil.rmtree(analysis_dir)
            except:
                pass
        return None

def load_analysis(analysis_id):
    """Load a saved analysis with error handling"""
    analysis_dir = ANALYSES_DIR / analysis_id
    if not analysis_dir.exists():
        return None
    
    try:
        # Load valuation summary
        summary_file = analysis_dir / "valuation_summary.json"
        if not summary_file.exists():
            return None
        
        with open(summary_file, 'r', encoding='utf-8') as f:
            valuation_summary = json.load(f)
        
        # Load results plot
        results_plot_path = analysis_dir / "results_plot.png"
        if not results_plot_path.exists():
            return None
        
        return {
            'valuation_summary': valuation_summary,
            'results_plot': results_plot_path
        }
    except Exception as e:
        st.error(f"Error loading analysis {analysis_id}: {e}")
        return None

def delete_analysis(analysis_id):
    """Delete an analysis from disk and index (only if owned by current user)"""
    user_key = get_user_key()
    if not user_key:
        return
    
    index = load_analyses_index()
    
    # Find and remove from index (only if owned by current user)
    for ticker in list(index.keys()):
        if analysis_id in index[ticker]:
            analysis_info = index[ticker][analysis_id]
            # Verify ownership by user_key (case-insensitive, backward compatible)
            info_key = analysis_info.get("user_key") or normalize_user_key(analysis_info.get("user_name", ""))
            if info_key == user_key:
                del index[ticker][analysis_id]
                # Remove ticker entry if no analyses left
                if not index[ticker]:
                    del index[ticker]
                
                # Save updated index
                save_analyses_index(index)
                
                # Delete analysis directory
                analysis_dir = ANALYSES_DIR / analysis_id
                if analysis_dir.exists():
                    shutil.rmtree(analysis_dir)
                
                # Clear selected analysis if it was the deleted one
                if st.session_state.get('selected_analysis') == analysis_id:
                    st.session_state.selected_analysis = None
                break

def display_saved_analyses():
    """Display the saved analyses organized by ticker (for current user only)"""
    # Check if user is set
    user_name = get_user_name()
    user_key = get_user_key()
    if not user_key or not st.session_state.get('user_initialized'):
        st.warning("⚠️ Please set your user name at the top of the page to view your analyses.")
        return
    
    st.header("Performed Analyses")
    
    # Show storage info
    with st.expander("ℹ️ About Analysis Storage", expanded=False):
        st.info(f"""
        **Storage Location:** Analyses are saved to: `{ANALYSES_DIR.absolute()}`
        
        **User Isolation:**
        - Each user has their own separate analyses section
        - Analyses are tagged with your user name: **{user_name}** (matching is case-insensitive)
        - You can only see and manage your own analyses
        - Entering the same name (e.g., Juan/juan) will retrieve the same analyses
        
        **Persistence:**
        - **Local deployment:** Analyses persist across app restarts
        - **Streamlit Cloud:** Files may be cleared after app restarts or inactivity periods
        - **Recommendation:** Download important analyses or export data for permanent storage
        
        **What's Saved:**
        - Results plot (PNG image)
        - Valuation summary (JSON with all parameters and results)
        - Analysis metadata (timestamp, company name, user name, etc.)
        """)
    
    # Clean up orphaned entries (analyses in index but files missing) for current user
    cleanup_orphaned_analyses()
    
    # Get only current user's analyses
    index = get_user_analyses_index()
    
    if not index:
        st.info(f"No analyses have been performed yet. Run a simulation to save your first analysis.")
        st.caption(f"Currently logged in as: **{user_name}**")
        return
    
    # Show current user indicator
    user_analyses_count = count_user_analyses(user_name)
    st.caption(f"👤 Showing analyses for: **{user_name}** ({user_analyses_count} analyses)")
    
    # Initialize session state for selected analysis
    if 'selected_analysis' not in st.session_state:
        st.session_state.selected_analysis = None
    
    # Check if an analysis was deleted
    if 'delete_analysis_id' in st.session_state:
        delete_analysis(st.session_state.delete_analysis_id)
        del st.session_state.delete_analysis_id
        st.rerun()
    
    # Display analyses organized by ticker with View and Delete buttons
    for ticker in sorted(index.keys()):
        analyses = index[ticker]
        company_name = list(analyses.values())[0]['company_name']
        
        with st.expander(f"📊 {ticker} - {company_name} ({len(analyses)} {'analyses' if len(analyses) > 1 else 'analysis'})"):
            # Sort analyses by timestamp (newest first)
            sorted_analyses = sorted(analyses.items(), key=lambda x: x[1]['timestamp'], reverse=True)
            
            for analysis_id, analysis_info in sorted_analyses:
                date_str = analysis_info['date']
                timestamp_str = analysis_info['timestamp']
                # Format timestamp for display
                try:
                    dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    formatted_time = timestamp_str
                
                # Validate files exist
                files_exist = validate_analysis_files(analysis_id)
                
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    status_icon = "⚠️" if not files_exist else ""
                    st.write(f"{status_icon} **Date:** {date_str} | **Time:** {formatted_time}")
                    if not files_exist:
                        st.caption("⚠️ Analysis files not found (may have been cleared)")
                with col2:
                    if files_exist:
                        if st.button("View", key=f"view_{analysis_id}"):
                            st.session_state.selected_analysis = analysis_id
                            st.session_state.active_tab = "Performed Analyses"
                            # Set query param to persist tab selection
                            st.query_params.tab = "performed"
                            # Clear the radio button state to force it to use our index on rerun
                            # This is critical when viewing from within a newly submitted analysis
                            if 'tab_selector' in st.session_state:
                                del st.session_state.tab_selector
                            st.rerun()
                    else:
                        st.caption("Unavailable")
                with col3:
                    if st.button("🗑️ Delete", key=f"delete_{analysis_id}"):
                        st.session_state.delete_analysis_id = analysis_id
                        st.rerun()
    
    # Display selected analysis
    if st.session_state.selected_analysis:
        st.markdown("---")
        st.subheader("Selected Analysis")
        display_analysis(st.session_state.selected_analysis)

def display_analysis(analysis_id):
    """Display a saved analysis"""
    analysis = load_analysis(analysis_id)
    if not analysis:
        st.error(f"Analysis not found: {analysis_id}")
        return
    
    # Verify files exist
    if not Path(analysis['results_plot']).exists():
        st.error(f"Results plot file not found for analysis: {analysis_id}")
        return
    
    valuation_summary = analysis['valuation_summary']
    
    # Display results plot
    st.image(str(analysis['results_plot']), caption="Results Plot", use_container_width=True)
    
    # Display summary
    st.markdown("### Valuation Summary")
    sum_col1, sum_col2 = st.columns(2)
    
    with sum_col1:
        st.markdown(f"""
            <div class="summary-text">
            <p><strong>Current Price:</strong> {valuation_summary['current_price']}<br>
            <strong>Mean Value:</strong> {valuation_summary['mean_value']}<br>
            <strong>Median Value:</strong> {valuation_summary['median_value']}<br>
            <strong>Upside Potential:</strong> {valuation_summary['upside_potential']}</p>
            
            <p><strong>Probabilities:</strong><br>
            Overvaluation: {valuation_summary['prob_overvalued']}<br>
            Undervaluation: {valuation_summary['prob_undervalued']}</p>
            
            <p><strong>Risk Metrics:</strong><br>
            VaR 95%: {valuation_summary['VaR 95%']}<br>
            CVaR 95%: {valuation_summary['CVaR 95%']}<br>
            Std. Deviation: {valuation_summary['Std. Deviation']}</p>
            </div>
        """, unsafe_allow_html=True)
    
    with sum_col2:
        st.markdown(f"""
            <div class="summary-text">
            <p><strong>Variable Parameters:</strong><br>
            Growth 5y: {valuation_summary['Variable Parameters']['Growth 5y']}<br>
            Growth 5-10y: {valuation_summary['Variable Parameters']['Growth 5-10y']}<br>
            WACC: {valuation_summary['Variable Parameters']['WACC']}<br>
            Risk Premium: {valuation_summary['Variable Parameters']['Risk Premium']}<br>
            Risk Free Rate: {valuation_summary['Variable Parameters']['Risk Free Rate']}<br>
            Reinvestment 5y: {valuation_summary['Variable Parameters']['Reinvestment 5y']}<br>
            Reinvestment 5-10y: {valuation_summary['Variable Parameters']['Reinvestment 5-10y']}</p>
            
            <p><strong>Terminal Value Params:</strong><br>
            Term. Growth: {valuation_summary['Terminal Value Params']['Term. Growth']}<br>
            Term. WACC: {valuation_summary['Terminal Value Params']['Term. WACC']}<br>
            Term. Reinv Rate: {valuation_summary['Terminal Value Params']['Term. Reinv Rate']}</p>
            </div>
        """, unsafe_allow_html=True)

st.title("DCF Monte Carlo Valuation Tool")

# --- USER IDENTIFICATION (MUST BE SET FIRST) ---
st.markdown("---")
st.subheader("👤 User Identification")

if 'user_initialized' not in st.session_state:
    st.session_state.user_initialized = False

# A user is considered logged in if we have a non-empty user_key.
user_is_initialized = bool(get_user_key())

if not user_is_initialized:
    # Robust login: one form, one submit button.
    # Entering an existing name logs you in (case-insensitive) and shows your analyses.
    with st.form("user_login_form", clear_on_submit=False):
        user_input = st.text_input(
            "Enter your name/identifier:",
            key="user_name_input",
            help="Use the same name each time to retrieve your saved analyses. Matching is case-insensitive (Juan == juan).",
            placeholder="e.g., Juan"
        )
        submitted = st.form_submit_button("Continue anyway", type="primary")

    if submitted:
        name = (user_input or "").strip()
        if not name:
            st.error("Please enter a valid name.")
        else:
            existed = is_user_name_taken(name)
            set_user_name(name)
            # Show feedback and proceed in the SAME run (no fragile multi-click flows)
            n = count_user_analyses(name)
            if existed and n > 0:
                st.success(f"✅ Welcome back, {get_user_name()}! Loaded {n} saved analyses.")
            else:
                st.success(f"✅ User set to: {get_user_name()}")
            st.rerun()
else:
    current_user = get_user_name()
    user_analyses_count = count_user_analyses(current_user)

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.info(
            f"👤 **Current User:** {current_user}"
            + (f" ({user_analyses_count} analyses)" if user_analyses_count > 0 else "")
        )
    with col2:
        if st.button("Change User", key="change_user_btn"):
            st.session_state.user_initialized = False
            st.session_state.user_name = None
            st.session_state.user_key = None
            st.session_state.user_id = None
            st.rerun()
    with col3:
        if st.button("Logout", key="logout_btn"):
            st.session_state.user_initialized = False
            st.session_state.user_name = None
            st.session_state.user_key = None
            st.session_state.user_id = None
            st.rerun()

st.markdown("---")

# --- TICKER SEARCH FUNCTIONALITY ---
@st.cache_data(ttl=86400)  # Cache for 24 hours
def get_ticker_database():
    """Get a comprehensive list of major world stocks"""
    return {
        # US Stocks
        'AAPL': 'Apple Inc.',
        'GOOGL': 'Alphabet Inc. (Class A)',
        'GOOG': 'Alphabet Inc. (Class C)',
        'MSFT': 'Microsoft Corporation',
        'AMZN': 'Amazon.com Inc.',
        'META': 'Meta Platforms Inc.',
        'TSLA': 'Tesla Inc.',
        'NVDA': 'NVIDIA Corporation',
        'JPM': 'JPMorgan Chase & Co.',
        'V': 'Visa Inc.',
        'JNJ': 'Johnson & Johnson',
        'WMT': 'Walmart Inc.',
        'MA': 'Mastercard Inc.',
        'PG': 'Procter & Gamble',
        'UNH': 'UnitedHealth Group',
        'HD': 'The Home Depot',
        'DIS': 'The Walt Disney Company',
        'BAC': 'Bank of America',
        'XOM': 'Exxon Mobil',
        'CVX': 'Chevron Corporation',
        'ABBV': 'AbbVie Inc.',
        'PFE': 'Pfizer Inc.',
        'AVGO': 'Broadcom Inc.',
        'COST': 'Costco Wholesale',
        'MRK': 'Merck & Co.',
        'ABT': 'Abbott Laboratories',
        'TMO': 'Thermo Fisher Scientific',
        'ACN': 'Accenture',
        'CSCO': 'Cisco Systems',
        'NFLX': 'Netflix Inc.',
        'AMD': 'Advanced Micro Devices',
        'INTC': 'Intel Corporation',
        'CMCSA': 'Comcast Corporation',
        'ADBE': 'Adobe Inc.',
        'NKE': 'Nike Inc.',
        'TXN': 'Texas Instruments',
        'QCOM': 'Qualcomm Inc.',
        'HON': 'Honeywell International',
        'AMGN': 'Amgen Inc.',
        'SBUX': 'Starbucks Corporation',
        'GILD': 'Gilead Sciences',
        'MDT': 'Medtronic',
        'ISRG': 'Intuitive Surgical',
        'VZ': 'Verizon Communications',
        'LMT': 'Lockheed Martin',
        'RTX': 'Raytheon Technologies',
        'UPS': 'United Parcel Service',
        'BMY': 'Bristol-Myers Squibb',
        'PM': 'Philip Morris International',
        'T': 'AT&T Inc.',
        'DE': 'Deere & Company',
        'CAT': 'Caterpillar Inc.',
        'GS': 'Goldman Sachs',
        'MS': 'Morgan Stanley',
        'BLK': 'BlackRock',
        'AXP': 'American Express',
        'SPGI': 'S&P Global',
        'INTU': 'Intuit Inc.',
        'BKNG': 'Booking Holdings',
        'ADI': 'Analog Devices',
        'AMAT': 'Applied Materials',
        'KLAC': 'KLA Corporation',
        'LRCX': 'Lam Research',
        'CDNS': 'Cadence Design Systems',
        'SNPS': 'Synopsys',
        'CRWD': 'CrowdStrike',
        'PANW': 'Palo Alto Networks',
        'FTNT': 'Fortinet',
        'ZS': 'Zscaler',
        'NET': 'Cloudflare',
        'DDOG': 'Datadog',
        'MDB': 'MongoDB',
        'NOW': 'ServiceNow',
        'TEAM': 'Atlassian',
        'WDAY': 'Workday',
        'VEEV': 'Veeva Systems',
        'ZM': 'Zoom Video Communications',
        'DOCN': 'DigitalOcean',
        'GTLB': 'GitLab',
        'ESTC': 'Elastic',
        'FROG': 'JFrog',
        'PATH': 'UiPath',
        'BILL': 'Bill.com',
        'COUP': 'Coupa Software',
        'OKTA': 'Okta',
        'SPLK': 'Splunk',
        'QLYS': 'Qualys',
        'RPD': 'Rapid7',
        'TENB': 'Tenable',
        'VRNS': 'Varonis Systems',
        'RDWR': 'Radware',
        'CHKP': 'Check Point Software',
        'QLYS': 'Qualys',
        'RDWR': 'Radware',
        'CHKP': 'Check Point Software',
        'FTNT': 'Fortinet',
        'ZS': 'Zscaler',
        'NET': 'Cloudflare',
        'DDOG': 'Datadog',
        'MDB': 'MongoDB',
        'NOW': 'ServiceNow',
        'TEAM': 'Atlassian',
        'WDAY': 'Workday',
        'VEEV': 'Veeva Systems',
        'ZM': 'Zoom Video Communications',
        'DOCN': 'DigitalOcean',
        'GTLB': 'GitLab',
        'ESTC': 'Elastic',
        'FROG': 'JFrog',
        'PATH': 'UiPath',
        'BILL': 'Bill.com',
        'COUP': 'Coupa Software',
        'OKTA': 'Okta',
        'SPLK': 'Splunk',
        'QLYS': 'Qualys',
        'RPD': 'Rapid7',
        'TENB': 'Tenable',
        'VRNS': 'Varonis Systems',
        'RDWR': 'Radware',
        'CHKP': 'Check Point Software',
        # European Stocks
        'NVO': 'Novo Nordisk A/S',
        'NVO.CO': 'Novo Nordisk A/S (Copenhagen)',
        'ASML': 'ASML Holding N.V.',
        'ASML.AS': 'ASML Holding (Amsterdam)',
        'SAP': 'SAP SE',
        'SAP.DE': 'SAP SE (Germany)',
        'SHEL': 'Shell plc',
        'SHEL.L': 'Shell plc (London)',
        'BP': 'BP p.l.c.',
        'BP.L': 'BP p.l.c. (London)',
        'GSK': 'GSK plc',
        'GSK.L': 'GSK plc (London)',
        'AZN': 'AstraZeneca',
        'AZN.L': 'AstraZeneca (London)',
        'UL': 'Unilever',
        'ULVR.L': 'Unilever (London)',
        'DEO': 'Diageo',
        'DEO.L': 'Diageo (London)',
        'RDS-A': 'Royal Dutch Shell',
        'RDS-B': 'Royal Dutch Shell',
        'BTI': 'British American Tobacco',
        'BTI.L': 'British American Tobacco (London)',
        'RIO': 'Rio Tinto',
        'RIO.L': 'Rio Tinto (London)',
        'BHP': 'BHP Group',
        'BHP.L': 'BHP Group (London)',
        'GLEN.L': 'Glencore (London)',
        'NG': 'National Grid',
        'NG.L': 'National Grid (London)',
        'VOD': 'Vodafone',
        'VOD.L': 'Vodafone (London)',
        'TSCO.L': 'Tesco (London)',
        'SBRY.L': 'Sainsbury\'s (London)',
        'MKS.L': 'Marks & Spencer (London)',
        'NXT.L': 'Next (London)',
        'JD.L': 'JD Sports (London)',
        'FRES.L': 'Fresnillo (London)',
        'POLY.L': 'Polymetal (London)',
        'AAL.L': 'Anglo American (London)',
        'ANTO.L': 'Antofagasta (London)',
        'EVR.L': 'Evercore (London)',
        'FERG.L': 'Ferguson (London)',
        'FOUR.L': '4imprint (London)',
        'GFTU.L': 'Grafton (London)',
        'HWDN.L': 'Howden Joinery (London)',
        'IHG.L': 'InterContinental Hotels (London)',
        'JD.L': 'JD Sports Fashion (London)',
        'KGF.L': 'Kingfisher (London)',
        'LAND.L': 'Land Securities (London)',
        'LGEN.L': 'Legal & General (London)',
        'LLOY.L': 'Lloyds Banking (London)',
        'MKS.L': 'Marks & Spencer (London)',
        'NXT.L': 'Next (London)',
        'OCDO.L': 'Ocado (London)',
        'PSN.L': 'Persimmon (London)',
        'RTO.L': 'Rentokil Initial (London)',
        'SBRY.L': 'Sainsbury\'s (London)',
        'SGE.L': 'Sage Group (London)',
        'SGRO.L': 'Segro (London)',
        'SN.L': 'Smith & Nephew (London)',
        'SPX.L': 'Spirax-Sarco Engineering (London)',
        'SSE.L': 'SSE (London)',
        'STAN.L': 'Standard Chartered (London)',
        'STJ.L': 'St. James\'s Place (London)',
        'SVT.L': 'Severn Trent (London)',
        'TSCO.L': 'Tesco (London)',
        'TW.L': 'Taylor Wimpey (London)',
        'ULVR.L': 'Unilever (London)',
        'VOD.L': 'Vodafone (London)',
        'WEIR.L': 'Weir Group (London)',
        'WTB.L': 'Whitbread (London)',
        # Asian Stocks
        'TSM': 'Taiwan Semiconductor',
        'TSM.TW': 'Taiwan Semiconductor (Taiwan)',
        'BABA': 'Alibaba Group',
        'BABA.HK': 'Alibaba Group (Hong Kong)',
        'JD': 'JD.com',
        'JD.HK': 'JD.com (Hong Kong)',
        'PDD': 'Pinduoduo',
        'PDD.HK': 'Pinduoduo (Hong Kong)',
        'BIDU': 'Baidu',
        'BIDU.HK': 'Baidu (Hong Kong)',
        'NIO': 'NIO Inc.',
        'NIO.HK': 'NIO Inc. (Hong Kong)',
        'XPEV': 'XPeng',
        'XPEV.HK': 'XPeng (Hong Kong)',
        'LI': 'Li Auto',
        'LI.HK': 'Li Auto (Hong Kong)',
        'TME': 'Tencent Music',
        'TME.HK': 'Tencent Music (Hong Kong)',
        'NTES': 'NetEase',
        'NTES.HK': 'NetEase (Hong Kong)',
        'WB': 'Weibo',
        'WB.HK': 'Weibo (Hong Kong)',
        'DOYU': 'DouYu',
        'DOYU.HK': 'DouYu (Hong Kong)',
        'HUYA': 'Huya',
        'HUYA.HK': 'Huya (Hong Kong)',
        'YY': 'YY Inc.',
        'YY.HK': 'YY Inc. (Hong Kong)',
        'VIPS': 'Vipshop',
        'VIPS.HK': 'Vipshop (Hong Kong)',
        'WB': 'Weibo',
        'WB.HK': 'Weibo (Hong Kong)',
        # Canadian Stocks
        'SHOP': 'Shopify',
        'SHOP.TO': 'Shopify (Toronto)',
        'RY': 'Royal Bank of Canada',
        'RY.TO': 'Royal Bank of Canada (Toronto)',
        'TD': 'TD Bank',
        'TD.TO': 'TD Bank (Toronto)',
        'BNS': 'Bank of Nova Scotia',
        'BNS.TO': 'Bank of Nova Scotia (Toronto)',
        'BMO': 'Bank of Montreal',
        'BMO.TO': 'Bank of Montreal (Toronto)',
        'CM': 'Canadian Imperial Bank',
        'CM.TO': 'Canadian Imperial Bank (Toronto)',
        'ENB': 'Enbridge',
        'ENB.TO': 'Enbridge (Toronto)',
        'TRP': 'TC Energy',
        'TRP.TO': 'TC Energy (Toronto)',
        'CP': 'Canadian Pacific',
        'CP.TO': 'Canadian Pacific (Toronto)',
        'CNR': 'Canadian National Railway',
        'CNR.TO': 'Canadian National Railway (Toronto)',
        'ATD': 'Alimentation Couche-Tard',
        'ATD.TO': 'Alimentation Couche-Tard (Toronto)',
        'WCN': 'Waste Connections',
        'WCN.TO': 'Waste Connections (Toronto)',
        'FNV': 'Franco-Nevada',
        'FNV.TO': 'Franco-Nevada (Toronto)',
        'WPM': 'Wheaton Precious Metals',
        'WPM.TO': 'Wheaton Precious Metals (Toronto)',
        'NTR': 'Nutrien',
        'NTR.TO': 'Nutrien (Toronto)',
        'SU': 'Suncor Energy',
        'SU.TO': 'Suncor Energy (Toronto)',
        'IMO': 'Imperial Oil',
        'IMO.TO': 'Imperial Oil (Toronto)',
        'CVE': 'Cenovus Energy',
        'CVE.TO': 'Cenovus Energy (Toronto)',
        'MEG': 'MEG Energy',
        'MEG.TO': 'MEG Energy (Toronto)',
        'TOU': 'Tourmaline Oil',
        'TOU.TO': 'Tourmaline Oil (Toronto)',
        'ARX': 'ARC Resources',
        'ARX.TO': 'ARC Resources (Toronto)',
        'PPL': 'Pembina Pipeline',
        'PPL.TO': 'Pembina Pipeline (Toronto)',
        'KEY': 'Keyera',
        'KEY.TO': 'Keyera (Toronto)',
        'IPL': 'Inter Pipeline',
        'IPL.TO': 'Inter Pipeline (Toronto)',
        'PXT': 'Parex Resources',
        'PXT.TO': 'Parex Resources (Toronto)',
        'VET': 'Vermilion Energy',
        'VET.TO': 'Vermilion Energy (Toronto)',
        'BAY': 'Baytex Energy',
        'BAY.TO': 'Baytex Energy (Toronto)',
        'CR': 'Crew Energy',
        'CR.TO': 'Crew Energy (Toronto)',
        'GTE': 'Gran Tierra Energy',
        'GTE.TO': 'Gran Tierra Energy (Toronto)',
        'TVE': 'Tamarack Valley Energy',
        'TVE.TO': 'Tamarack Valley Energy (Toronto)',
        'WCP': 'Whitecap Resources',
        'WCP.TO': 'Whitecap Resources (Toronto)',
        'TOU': 'Tourmaline Oil',
        'TOU.TO': 'Tourmaline Oil (Toronto)',
        'ARX': 'ARC Resources',
        'ARX.TO': 'ARC Resources (Toronto)',
        'PPL': 'Pembina Pipeline',
        'PPL.TO': 'Pembina Pipeline (Toronto)',
        'KEY': 'Keyera',
        'KEY.TO': 'Keyera (Toronto)',
        'IPL': 'Inter Pipeline',
        'IPL.TO': 'Inter Pipeline (Toronto)',
        'PXT': 'Parex Resources',
        'PXT.TO': 'Parex Resources (Toronto)',
        'VET': 'Vermilion Energy',
        'VET.TO': 'Vermilion Energy (Toronto)',
        'BAY': 'Baytex Energy',
        'BAY.TO': 'Baytex Energy (Toronto)',
        'CR': 'Crew Energy',
        'CR.TO': 'Crew Energy (Toronto)',
        'GTE': 'Gran Tierra Energy',
        'GTE.TO': 'Gran Tierra Energy (Toronto)',
        'TVE': 'Tamarack Valley Energy',
        'TVE.TO': 'Tamarack Valley Energy (Toronto)',
        'WCP': 'Whitecap Resources',
        'WCP.TO': 'Whitecap Resources (Toronto)',
    }

@st.cache_data(ttl=3600)  # Cache for 1 hour
def search_tickers(query):
    """Search for ticker symbols using ticker database"""
    if not query or len(query) < 1:
        return []
    
    results = []
    query_upper = query.upper()
    ticker_db = get_ticker_database()
    
    # Search through database
    for ticker, name in ticker_db.items():
        if query_upper in ticker.upper() or query_upper in name.upper():
            results.append({
                'ticker': ticker,
                'name': name,
                'exchange': ''
            })
    
    # Try to validate ticker by attempting to fetch info (for tickers not in database)
    if len(results) < 5 and len(query_upper) >= 1:
        # Try the query as a ticker directly
        try:
            tk = yf.Ticker(query_upper)
            info = tk.info
            if info and len(info) > 0:
                name = info.get('longName') or info.get('shortName') or query_upper
                results.insert(0, {
                    'ticker': query_upper,
                    'name': name,
                    'exchange': info.get('exchange', '')
                })
        except:
            pass
    
    # Remove duplicates
    seen = set()
    unique_results = []
    for r in results:
        if r['ticker'] not in seen:
            seen.add(r['ticker'])
            unique_results.append(r)
    
    return unique_results[:20]  # Limit to 20 results

# --- LÓGICA DE RECUPERACIÓN ---
def fetch_data(ticker, target_curr):
    """
    Fetch financial data for a ticker using yfinance.
    Returns a dict with price, shares, cash, ebit, debt or None if failed.
    """
    import time
    
    # Clean the ticker
    ticker = ticker.strip().upper()
    if not ticker:
        return None
    
    # Try different ticker formats (some stocks need exchange suffixes)
    ticker_variants = [ticker]
    
    # Common exchange suffixes to try (only if ticker doesn't already have an exchange suffix)
    if "." not in ticker and len(ticker) <= 5:
        ticker_variants.extend([
            f"{ticker}.CO",  # Copenhagen (e.g., NVO.CO for Novo Nordisk)
            f"{ticker}.TO",  # Toronto
            f"{ticker}.L",   # London
            f"{ticker}.ST",  # Stockholm
            f"{ticker}.DE",  # Germany
            f"{ticker}.PA",  # Paris
            f"{ticker}.AS",  # Amsterdam
        ])
    
    last_error = None
    for ticker_to_try in ticker_variants:
        try:
            # Create ticker object
            tk = yf.Ticker(ticker_to_try)
            
            # First, try to get price from history (more reliable)
            price_from_history = None
            try:
                hist = tk.history(period="5d")
                if not hist.empty and len(hist) > 0:
                    price_from_history = float(hist['Close'].iloc[-1])
            except:
                pass
            
            # Try to get info - this can sometimes fail or return empty dict
            # Add a small delay to avoid rate limiting
            time.sleep(0.1)
            info = None
            try:
                info = tk.info
            except:
                # If info fails, we can still use history data
                if price_from_history and price_from_history > 0:
                    # Return minimal data with price from history
                    return {
                        "price": price_from_history,
                        "shares": 1e9,  # Default
                        "cash": 0,
                        "ebit": 0,
                        "debt": 0,
                    }
                continue
            
            # If info is empty or invalid, try fast_info as fallback
            if not info or (isinstance(info, dict) and len(info) < 5):
                try:
                    fast_info = tk.fast_info
                    if fast_info:
                        # Merge fast_info into info if available
                        if isinstance(info, dict):
                            info.update(fast_info)
                        else:
                            info = fast_info
                except:
                    pass
            
            # Check if info is valid - sometimes yfinance returns empty dict or dict with error
            if not info:
                continue
                
            # Check for common error indicators in yfinance response
            if isinstance(info, dict):
                # Check for explicit error fields
                if 'error' in info or 'Error' in info:
                    continue
                    
                # Check if we have at least some basic info (but be lenient - some tickers have minimal data)
                if len(info) < 3:
                    continue
                    
                # Check for quoteType to ensure it's a valid security
                # But don't fail if it's missing - some exchanges don't provide this
                if 'quoteType' in info and info.get('quoteType') == 'NONE':
                    continue
            
            # Try to get price - use history first if available, then try info fields
            price = price_from_history
            
            if price is None or price <= 0:
                # Try info fields
                price_fields = [
                    "currentPrice",
                    "regularMarketPrice", 
                    "previousClose",
                    "regularMarketPreviousClose",
                    "open",
                    "ask",
                    "bid",
                    "lastPrice"
                ]
                
                for field in price_fields:
                    if info and field in info and info[field] is not None:
                        price_val = info[field]
                        if isinstance(price_val, (int, float)) and price_val > 0:
                            price = float(price_val)
                            break
            
            # Final fallback: try history again if we still don't have price
            if (price is None or price <= 0) and not price_from_history:
                try:
                    hist = tk.history(period="1d")
                    if not hist.empty and len(hist) > 0:
                        price = float(hist['Close'].iloc[-1])
                except:
                    pass
            
            if price is None or price <= 0:
                continue
            
            # Get currency
            native_curr = info.get("currency", "USD")
            if not native_curr:
                native_curr = "USD"
            
            # Get shares outstanding - try multiple methods
            shares = None
            
            # Method 1: Direct field
            shares_fields = [
                "sharesOutstanding",
                "impliedSharesOutstanding", 
                "sharesShort",
                "floatShares",
                "sharesShortPriorMonth"
            ]
            
            for field in shares_fields:
                if field in info and info[field] is not None:
                    shares_val = info[field]
                    if isinstance(shares_val, (int, float)) and shares_val > 0:
                        shares = float(shares_val)
                        break
            
            # Method 2: Calculate from market cap
            if shares is None or shares <= 0:
                market_cap = info.get("marketCap") or info.get("enterpriseValue")
                if market_cap and isinstance(market_cap, (int, float)) and market_cap > 0 and price > 0:
                    shares = float(market_cap) / price
            
            # Method 3: Use shares outstanding from financials
            if (shares is None or shares <= 0) and 'sharesOutstanding' in info:
                shares_val = info['sharesOutstanding']
                if isinstance(shares_val, (int, float)) and shares_val > 0:
                    shares = float(shares_val)
            
            # If shares still not found, use a default or calculate from market cap
            if shares is None or shares <= 0:
                # Try one more time with marketCap
                market_cap = info.get("marketCap")
                if market_cap and price > 0:
                    shares = market_cap / price
                # If still no shares, use a default (user can adjust)
                if shares is None or shares <= 0:
                    # Default to 1 billion shares if we can't determine
                    shares = 1e9
            
            # Get cash - try multiple fields
            cash = 0
            cash_fields = ["totalCash", "totalCashPerShare", "cash", "cashAndCashEquivalents"]
            for field in cash_fields:
                if field in info and info[field] is not None:
                    cash_val = info[field]
                    if isinstance(cash_val, (int, float)) and cash_val >= 0:
                        if "PerShare" in field and shares > 0:
                            cash = float(cash_val) * shares
                        else:
                            cash = float(cash_val)
                        break
            
            # Get EBITDA/Operating Income
            ebitda = 0
            ebitda_fields = ["ebitda", "operatingIncome", "ebit", "operatingCashflow"]
            for field in ebitda_fields:
                if field in info and info[field] is not None:
                    ebitda_val = info[field]
                    if isinstance(ebitda_val, (int, float)):
                        ebitda = float(ebitda_val)
                        break
            
            # Get debt
            debt = 0
            debt_fields = ["totalDebt", "totalDebt", "longTermDebt", "debt"]
            for field in debt_fields:
                if field in info and info[field] is not None:
                    debt_val = info[field]
                    if isinstance(debt_val, (int, float)) and debt_val >= 0:
                        debt = float(debt_val)
                        break
            
            # Build data dictionary
            data = {
                "price": price,
                "shares": shares / 1e6,  # Convert to millions
                "cash": cash / 1e6 if cash > 0 else 0,
                "ebit": (ebitda * 0.85) / 1e6 if ebitda > 0 else 0,
                "debt": debt / 1e6 if debt > 0 else 0,
            }
            
            # Validate we have at least price and shares
            if data["price"] > 0 and data["shares"] > 0:
                # Handle currency conversion
                if target_curr.upper() != native_curr.upper():
                    try:
                        rate_ticker = yf.Ticker(f"{native_curr}{target_curr}=X")
                        time.sleep(0.1)  # Small delay
                        rate_history = rate_ticker.history(period="1d")
                        if not rate_history.empty and len(rate_history) > 0:
                            rate = rate_history['Close'].iloc[-1]
                            if rate and rate > 0:
                                for k in ["price", "cash", "ebit", "debt"]: 
                                    data[k] *= rate
                    except Exception as conv_error:
                        # If currency conversion fails, continue with native currency
                        pass
                
                return data
            else:
                # Last resort: try to get price from history if info failed
                if data["price"] <= 0:
                    try:
                        hist = tk.history(period="5d")
                        if not hist.empty and len(hist) > 0:
                            price_from_hist = float(hist['Close'].iloc[-1])
                            if price_from_hist > 0:
                                data["price"] = price_from_hist
                                # If we now have price and shares, return
                                if data["shares"] > 0:
                                    return data
                    except:
                        pass
                continue
                
        except Exception as e:
            last_error = str(e)
            # Continue to next variant
            continue
    
    # If all variants failed, return None
    return None

if 'st_vals' not in st.session_state:
    st.session_state.st_vals = {"price": 168.4, "shares": 12700.0, "cash": 96000.0, "ebit": 154740.0, "debt": 22000.0}


# Initialize tab state
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = "New Analysis"

with st.sidebar:
    st.header("1. Automatic Search")
    
    # Initialize ticker search state
    if 'selected_ticker' not in st.session_state:
        st.session_state.selected_ticker = "GOOGL - Alphabet Inc. (Class A)"
    
    # Get all tickers from database
    ticker_db = get_ticker_database()
    all_ticker_options = [f"{ticker} - {name}" for ticker, name in sorted(ticker_db.items())]
    
    # Find current selection index
    current_selection = st.session_state.get('selected_ticker', "GOOGL - Alphabet Inc. (Class A)")
    try:
        default_index = all_ticker_options.index(current_selection)
    except ValueError:
        default_index = 0
        # Add current selection if not in database
        all_ticker_options.insert(0, current_selection)
    
    # Single searchable selectbox - Streamlit's selectbox has built-in search/filter
    # As you type, it filters the options and shows suggestions in a dropdown
    selected_option = st.selectbox(
        "Search Ticker (type to see suggestions)",
        options=all_ticker_options,
        index=default_index,
        key="ticker_selectbox",
        help="Start typing to search. Suggestions will appear in the dropdown as you type."
    )
    
    # Extract ticker from selection
    t_input = selected_option.split(" - ")[0].strip()
    st.session_state.selected_ticker = selected_option
    
    target_currency = st.text_input("Target Currency", value="USD").upper()
    
    if st.button("Fetch & Auto-fill"):
        with st.spinner(f"Fetching data for {t_input}..."):
            try:
                res = fetch_data(t_input, target_currency)
                if res: 
                    st.session_state.st_vals.update(res)
                    st.success(f"✅ Data fetched for {t_input}! Values updated.")
                    st.rerun()
                else:
                    st.error(f"❌ Failed to fetch data for {t_input}.")
                    st.info(f"💡 Tip: Some tickers need exchange suffixes. Try: {t_input}.CO (Copenhagen), {t_input}.TO (Toronto), {t_input}.L (London), etc.")
                    # Try to show what went wrong
                    try:
                        test_ticker = yf.Ticker(t_input)
                        test_info = test_ticker.info
                        if test_info:
                            st.warning(f"⚠️ Ticker {t_input} exists but missing required data fields.")
                        else:
                            st.warning(f"⚠️ Ticker {t_input} not found. Try with exchange suffix.")
                    except:
                        pass
            except Exception as e:
                st.error(f"❌ Error fetching data: {str(e)}")
                st.info(f"💡 Tip: Try with exchange suffix (e.g., {t_input}.CO, {t_input}.TO, {t_input}.L)")

with st.sidebar.form("input_form"):
    # Check if user is set
    if not st.session_state.get('user_initialized') or not get_user_name():
        st.error("⚠️ **Please set your user name at the top of the page before filling out this form.**")
        st.info("Your analyses will be saved under your name, and you'll be able to access them later.")
        st.stop()
    
    st.header("Company Information")
    company_name = st.text_input("Company Name", value=t_input)
    # Currency se usa desde target_currency de arriba

    st.header("Financial Information")
    
    # Check which values are missing (0) and show warning
    missing_fields = []
    if float(st.session_state.st_vals.get('price', 0.0)) == 0:
        missing_fields.append("Current Price")
    if float(st.session_state.st_vals.get('shares', 0.0)) == 0:
        missing_fields.append("Shares Outstanding")
    if float(st.session_state.st_vals.get('cash', 0.0)) == 0:
        missing_fields.append("Cash")
    if float(st.session_state.st_vals.get('ebit', 0.0)) == 0:
        missing_fields.append("Operating Income Base")
    if float(st.session_state.st_vals.get('debt', 0.0)) == 0:
        missing_fields.append("Debt")
    
    if missing_fields:
        st.warning(f"⚠️ The following fields are 0 (not retrieved by autofetch): {', '.join(missing_fields)}. Please enter them manually.")
    
    # Two columns layout for financial information
    col1, col2 = st.columns(2)
    with col1:
        # Dynamically adjust max based on current value to accommodate fetched data
        price_val = float(st.session_state.st_vals.get('price', 0.0))
        shares_val = float(st.session_state.st_vals.get('shares', 0.0))
        cash_val = float(st.session_state.st_vals.get('cash', 0.0))
        
        price_max = max(10000.0, price_val * 2) if price_val > 0 else 10000.0
        shares_max = max(100000.0, shares_val * 2) if shares_val > 0 else 100000.0
        cash_max = max(1000000.0, cash_val * 2) if cash_val > 0 else 1000000.0
        
        current_price = st.number_input("Current Price", min_value=0.0, max_value=price_max, value=price_val, step=0.1)
        shares_outstanding = st.number_input("Shares Outstanding (millions)", min_value=0.0, max_value=shares_max, value=shares_val, step=1.0)
        cash = st.number_input("Cash (millions)", min_value=0.0, max_value=cash_max, value=cash_val, step=100.0)
    with col2:
        ebit_val = float(st.session_state.st_vals.get('ebit', 0.0))
        debt_val = float(st.session_state.st_vals.get('debt', 0.0))
        
        ebit_max = max(1000000.0, ebit_val * 2) if ebit_val > 0 else 1000000.0
        debt_max = max(1000000.0, debt_val * 2) if debt_val > 0 else 1000000.0
        
        operating_income_base = st.number_input("Operating Income Base (millions)", min_value=0.0, max_value=ebit_max, value=ebit_val, step=100.0)
        debt = st.number_input("Debt (millions)", min_value=0.0, max_value=debt_max, value=debt_val, step=100.0)
        tax_rate = st.number_input("Tax Rate (%)", min_value=0.0, max_value=50.0, value=21.0, step=0.1)
    
    # Calculate and display implied NOPAT
    nopat_implied = operating_income_base * (1 - tax_rate / 100)
    st.info(f"**Implied NOPAT:** {nopat_implied:.2f} millions {target_currency} (Operating Income × (1 - Tax Rate))")

    # TODOS LOS PARÁMETROS ORIGINALES
    st.header("Growth Parameters")
    col1, col2 = st.columns(2)
    with col1:
        growth_rate_5y = st.number_input("Growth Rate 5y (%)", min_value=-50.0, max_value=100.0, value=15.0, step=0.1)
    with col2:
        growth_rate_5_10y = st.number_input("Growth Rate 5-10y (%)", min_value=-50.0, max_value=100.0, value=8.0, step=0.1)

    st.header("Risk Parameters")
    col1, col2 = st.columns(2)
    with col1:
        risk_free_rate = st.number_input("Risk Free Rate (%)", min_value=0.0, max_value=20.0, value=4.5, step=0.01)
        equity_risk_premium = st.number_input("Equity Risk Premium (%)", min_value=0.0, max_value=15.0, value=5.13, step=0.01)
    with col2:
        WACC = st.number_input("WACC (%)", min_value=0.0, max_value=30.0, value=9.6, step=0.1)

    st.header("Reinvestment Rates")
    col1, col2 = st.columns(2)
    with col1:
        reinvestment_rate_5y = st.number_input("Reinvestment Rate 5y (%)", min_value=0.0, max_value=100.0, value=50.0, step=0.1)
    with col2:
        reinvestment_rate_5_10y = st.number_input("Reinvestment Rate 5-10y (%)", min_value=0.0, max_value=100.0, value=50.0, step=0.1)

    st.header("Standard Deviations")
    col1, col2 = st.columns(2)
    with col1:
        std_growth_5y = st.number_input("Std Growth 5y (%)", min_value=0.0, max_value=20.0, value=2.0, step=0.1)
        std_growth_5_10y = st.number_input("Std Growth 5-10y (%)", min_value=0.0, max_value=20.0, value=3.0, step=0.1)
        std_risk_free = st.number_input("Std Risk Free (%)", min_value=0.0, max_value=5.0, value=0.5, step=0.01)
        std_equity_premium = st.number_input("Std Equity Premium (%)", min_value=0.0, max_value=5.0, value=0.5, step=0.01)
    with col2:
        std_WACC = st.number_input("Std WACC (%)", min_value=0.0, max_value=5.0, value=0.5, step=0.01)
        std_reinv_5y = st.number_input("Std Reinv 5y (%)", min_value=0.0, max_value=20.0, value=2.5, step=0.1)
        std_reinv_5_10y = st.number_input("Std Reinv 5-10y (%)", min_value=0.0, max_value=20.0, value=5.0, step=0.1)

    n_simulations = st.number_input("Simulations", min_value=1000, max_value=100000, value=10000, step=1000)
    submitted = st.form_submit_button("Run Simulation")

# If an analysis is selected for viewing, force to else block for proper tab handling
# This ensures consistent behavior whether coming from a new analysis or directly
viewing_analysis = st.session_state.get('selected_analysis') and not submitted

if submitted and not viewing_analysis:
    # Check if user name is set
    if not st.session_state.get('user_initialized') or not get_user_name():
        st.error("❌ Please set your user name at the top of the page before running a simulation.")
        st.stop()
    
    params = {
        'company_name': company_name, 'currency': target_currency,
        'current_price': current_price, 'shares_outstanding': shares_outstanding,
        'cash': cash, 'debt': debt, 'operating_income_base': operating_income_base,
        'tax_rate': tax_rate/100,
        'growth_rate_5y': growth_rate_5y/100, 'growth_rate_5_10y': growth_rate_5_10y/100,
        'risk_free_rate': risk_free_rate/100, 'equity_risk_premium': equity_risk_premium/100,
        'WACC': WACC/100, 'reinvestment_rate_5y': reinvestment_rate_5y/100,
        'reinvestment_rate_5_10y': reinvestment_rate_5_10y/100,
        'std_growth_5y': std_growth_5y/100, 'std_growth_5_10y': std_growth_5_10y/100,
        'std_risk_free': std_risk_free/100, 'std_equity_premium': std_equity_premium/100,
        'std_WACC': std_WACC/100, 'std_reinv_5y': std_reinv_5y/100,
        'std_reinv_5_10y': std_reinv_5_10y/100, 'n_simulations': int(n_simulations)
    }

    with st.spinner("Running Monte Carlo simulation..."):
        fig_es, fig_distribution_only, fig_sensitivity, valuation_summary = run_monte_carlo_simulation(params)
        
        # Save the analysis
        analysis_id = save_analysis(t_input, company_name, valuation_summary, fig_es, fig_distribution_only, fig_sensitivity)
        st.success(f"Monte Carlo simulation for {company_name} completed successfully! Analysis saved.")

        tab1, tab2, tab3 = st.tabs(["Results", "Summary", "Performed Analyses"])
        
        with tab1:
            # Removed Results header
            st.pyplot(fig_es)
            
            # Add download button for the results plot
            buf_es = io.BytesIO()
            fig_es.savefig(buf_es, format="png")
            st.download_button(
                label="Download Results Plot",
                data=buf_es.getvalue(),
                file_name=f"{company_name}_results_plot.png",
                mime="image/png"
            )

        with tab2:
            # Use columns to display the distribution plot and the summary side-by-side
            col1_dist, col2_summary = st.columns([2, 1]) # Adjust column ratios as needed
            with col1_dist:
                # Removed Intrinsic Value Distribution header
                st.pyplot(fig_distribution_only)

                # Add download button for the intrinsic value distribution plot in Summary tab
                buf_dist_summary = io.BytesIO()
                fig_distribution_only.savefig(buf_dist_summary, format="png")
                st.download_button(
                    label="Download Intrinsic Value Distribution Plot",
                    data=buf_dist_summary.getvalue(),
                    file_name=f"{company_name}_intrinsic_value_distribution_summary_plot.png",
                    mime="image/png"
                )

            with col2_summary:
                st.markdown("""
                    <style>
                    .summary-text {
                        font-size: 0.9em;
                    }
                    </style>
                """, unsafe_allow_html=True)
                
                # Centered header for the Valuation Summary
                st.markdown("<h3 style='text-align: center;'>Valuation Summary</h3>", unsafe_allow_html=True)
                
                st.markdown(f"""
                    <div class="summary-text">
                    <p><strong>Company:</strong> {valuation_summary['company_name']}<br>
                    <strong>Date:</strong> {valuation_summary['date']}<br>
                    <strong>-------------------</strong></p>
                    </div>
                """, unsafe_allow_html=True)
                
                # Create two columns for the summary content
                sum_col1, sum_col2 = st.columns(2)
                
                with sum_col1:
                    st.markdown(f"""
                        <div class="summary-text">
                        <p><strong>Current Price:</strong> {valuation_summary['current_price']}<br>
                        <strong>Mean Value:</strong> {valuation_summary['mean_value']}<br>
                        <strong>Median Value:</strong> {valuation_summary['median_value']}<br>
                        <strong>Upside Potential:</strong> {valuation_summary['upside_potential']}</p>
                        
                        <p><strong>Probabilities:</strong><br>
                        Overvaluation: {valuation_summary['prob_overvalued']}<br>
                        Undervaluation: {valuation_summary['prob_undervalued']}</p>
                        
                        <p><strong>Risk Metrics:</strong><br>
                        VaR 95%: {valuation_summary['VaR 95%']}<br>
                        CVaR 95%: {valuation_summary['CVaR 95%']}<br>
                        Std. Deviation: {valuation_summary['Std. Deviation']}</p>
                        </div>
                    """, unsafe_allow_html=True)
                
                with sum_col2:
                    st.markdown(f"""
                        <div class="summary-text">
                        <p><strong>Variable Parameters:</strong><br>
                        Growth 5y: {valuation_summary['Variable Parameters']['Growth 5y']}<br>
                        Growth 5-10y: {valuation_summary['Variable Parameters']['Growth 5-10y']}<br>
                        WACC: {valuation_summary['Variable Parameters']['WACC']}<br>
                        Risk Premium: {valuation_summary['Variable Parameters']['Risk Premium']}<br>
                        Risk Free Rate: {valuation_summary['Variable Parameters']['Risk Free Rate']}<br>
                        Reinvestment 5y: {valuation_summary['Variable Parameters']['Reinvestment 5y']}<br>
                        Reinvestment 5-10y: {valuation_summary['Variable Parameters']['Reinvestment 5-10y']}</p>
                        
                        <p><strong>Terminal Value Params:</strong><br>
                        Term. Growth: {valuation_summary['Terminal Value Params']['Term. Growth']}<br>
                        Term. WACC: {valuation_summary['Terminal Value Params']['Term. WACC']}<br>
                        Term. Reinv Rate: {valuation_summary['Terminal Value Params']['Term. Reinv Rate']}</p>
                        </div>
                    """, unsafe_allow_html=True)

        # Close the plot figures to free up memory
        plt.close(fig_es)
        plt.close(fig_distribution_only)
        plt.close(fig_sensitivity)
        
        # Performed Analyses tab
        with tab3:
            display_saved_analyses()
else:
    # Show Performed Analyses tab even when no simulation is running
    # Use query params and session state to maintain tab selection
    tab_names = ["New Analysis", "Performed Analyses"]
    
    # Check query params first (most reliable for persistence)
    query_tab = None
    if "tab" in st.query_params:
        tab_param = st.query_params.get("tab")
        query_tab = tab_param[0] if isinstance(tab_param, list) else tab_param
    
    # PRIORITY: If an analysis is selected, ALWAYS force to Performed Analyses tab
    # This must be checked FIRST before any other logic
    if st.session_state.get('selected_analysis'):
        st.session_state.active_tab = "Performed Analyses"
        if query_tab != "performed":
            st.query_params.tab = "performed"
        # Force the radio button to use Performed Analyses by clearing its state
        if 'tab_selector' in st.session_state:
            # Reset the radio button state to force it to use our index
            del st.session_state.tab_selector
        default_index = 1
    # Check query params
    elif query_tab == "performed":
        st.session_state.active_tab = "Performed Analyses"
        default_index = 1
    # Otherwise, use the stored active_tab state
    elif st.session_state.active_tab == "Performed Analyses":
        default_index = 1
    else:
        default_index = 0
        if st.session_state.active_tab != "New Analysis":
            st.session_state.active_tab = "New Analysis"
    
    # Create tabs with radio buttons to maintain state
    # If selected_analysis exists, force the value to "Performed Analyses"
    if st.session_state.get('selected_analysis'):
        # Force the radio to show Performed Analyses
        tab_selection = st.radio(
            "Navigation",
            options=tab_names,
            index=1,  # Force index 1
            horizontal=True,
            key="tab_selector"
        )
    else:
        tab_selection = st.radio(
            "Navigation",
            options=tab_names,
            index=default_index,
            horizontal=True,
            key="tab_selector"
        )
    
    # Update session state and query params when tab changes
    if tab_selection != st.session_state.active_tab:
        st.session_state.active_tab = tab_selection
        if tab_selection == "Performed Analyses":
            st.query_params.tab = "performed"
        else:
            st.query_params.tab = "new"
            # Clear selected analysis when switching to New Analysis
            if 'selected_analysis' in st.session_state:
                st.session_state.selected_analysis = None
    
    if tab_selection == "New Analysis":
        st.info("Fill out the form in the sidebar and click 'Run Simulation' to perform a new analysis.")
    else:
        display_saved_analyses()












