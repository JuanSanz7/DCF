import streamlit as st
import matplotlib.pyplot as plt
import io
import yfinance as yf
import json
import os
from datetime import datetime
from pathlib import Path
from DCF_main import run_monte_carlo_simulation

st.set_page_config(page_title="DCF Monte Carlo Valuation Tool", layout="wide")
st.title("DCF Monte Carlo Valuation Tool")

# --- ANALYSIS STORAGE FUNCTIONS ---
ANALYSES_DIR = Path("saved_analyses")
ANALYSES_DIR.mkdir(exist_ok=True)
ANALYSES_INDEX_FILE = ANALYSES_DIR / "analyses_index.json"

def load_analyses_index():
    """Load the index of all saved analyses"""
    if ANALYSES_INDEX_FILE.exists():
        with open(ANALYSES_INDEX_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_analyses_index(index):
    """Save the index of all analyses"""
    with open(ANALYSES_INDEX_FILE, 'w') as f:
        json.dump(index, f, indent=2)

def save_analysis(ticker, company_name, valuation_summary, fig_es, fig_distribution_only, fig_sensitivity):
    """Save an analysis to disk"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    analysis_id = f"{ticker}_{timestamp}"
    analysis_dir = ANALYSES_DIR / analysis_id
    analysis_dir.mkdir(exist_ok=True)
    
    # Save only the results plot
    fig_es.savefig(analysis_dir / "results_plot.png", dpi=150, bbox_inches='tight')
    
    # Save valuation summary as JSON
    with open(analysis_dir / "valuation_summary.json", 'w') as f:
        json.dump(valuation_summary, f, indent=2)
    
    # Update index
    index = load_analyses_index()
    if ticker not in index:
        index[ticker] = {}
    index[ticker][analysis_id] = {
        'company_name': company_name,
        'timestamp': timestamp,
        'date': valuation_summary['date'],
        'analysis_id': analysis_id,
        'path': str(analysis_dir)
    }
    save_analyses_index(index)
    return analysis_id

def load_analysis(analysis_id):
    """Load a saved analysis"""
    analysis_dir = ANALYSES_DIR / analysis_id
    if not analysis_dir.exists():
        return None
    
    # Load valuation summary
    with open(analysis_dir / "valuation_summary.json", 'r') as f:
        valuation_summary = json.load(f)
    
    # Load results plot
    results_plot_path = analysis_dir / "results_plot.png"
    
    return {
        'valuation_summary': valuation_summary,
        'results_plot': results_plot_path
    }

def display_saved_analyses():
    """Display the saved analyses organized by ticker"""
    st.header("Performed Analyses")
    
    index = load_analyses_index()
    
    if not index:
        st.info("No analyses have been performed yet. Run a simulation to save your first analysis.")
        return
    
    # Initialize session state for selected analysis
    if 'selected_analysis' not in st.session_state:
        st.session_state.selected_analysis = None
    
    # Create a list of all analyses for selection
    all_analyses_list = []
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
                
                # Create display label
                display_label = f"{ticker} - {date_str} {formatted_time}"
                all_analyses_list.append((display_label, analysis_id))
                
                st.write(f"**Date:** {date_str} | **Time:** {formatted_time}")
    
    # Display analysis selector
    if all_analyses_list:
        st.markdown("---")
        st.subheader("Select Analysis to View")
        selected_label = st.selectbox(
            "Choose an analysis:",
            options=[label for label, _ in all_analyses_list],
            index=0 if not st.session_state.selected_analysis else next(
                (i for i, (_, aid) in enumerate(all_analyses_list) if aid == st.session_state.selected_analysis), 0
            ),
            key="analysis_selector"
        )
        
        # Get the analysis_id from the selected label
        try:
            selected_analysis_id = next(aid for label, aid in all_analyses_list if label == selected_label)
            st.session_state.selected_analysis = selected_analysis_id
            
            # Display selected analysis
            st.markdown("---")
            st.subheader("Selected Analysis")
            display_analysis(selected_analysis_id)
        except StopIteration:
            st.error("Selected analysis not found. Please try selecting again.")

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

# --- LÓGICA DE RECUPERACIÓN ---
def fetch_data(ticker, target_curr):
    try:
        tk = yf.Ticker(ticker)
        info = tk.info
        native_curr = info.get("currency", "USD")
        data = {
            "price": info.get("currentPrice", 168.4),
            "shares": info.get("sharesOutstanding", 12700e6) / 1e6,
            "cash": info.get("totalCash", 96000e6) / 1e6,
            "ebit": info.get("ebitda", 154740e6) * 0.85 / 1e6,
            "debt": info.get("totalDebt", 22000e6) / 1e6,
        }
        if target_curr != native_curr:
            rate = yf.Ticker(f"{native_curr}{target_curr}=X").history(period="1d")['Close'].iloc[-1]
            for k in ["price", "cash", "ebit", "debt"]: data[k] *= rate
        return data
    except: return None

if 'st_vals' not in st.session_state:
    st.session_state.st_vals = {"price": 168.4, "shares": 12700.0, "cash": 96000.0, "ebit": 154740.0, "debt": 22000.0}

with st.sidebar:
    st.header("1. Automatic Search")
    t_input = st.text_input("Ticker", value="GOOGL").upper()
    target_currency = st.text_input("Target Currency", value="USD").upper()
    if st.button("Fetch & Auto-fill"):
        res = fetch_data(t_input, target_currency)
        if res: st.session_state.st_vals.update(res)

with st.sidebar.form("input_form"):
    st.header("Company Information")
    company_name = st.text_input("Company Name", value=t_input)
    # Currency se usa desde target_currency de arriba

    st.header("Financial Information")
    col1, col2 = st.columns(2)
    with col1:
        current_price = st.number_input("Current Price", value=st.session_state.st_vals['price'])
        shares_outstanding = st.number_input("Shares Outstanding (millions)", value=st.session_state.st_vals['shares'])
        cash = st.number_input("Cash (millions)", value=st.session_state.st_vals['cash'])
    with col2:
        operating_income_base = st.number_input("Operating Income Base (millions)", value=st.session_state.st_vals['ebit'])
        debt = st.number_input("Debt (millions)", value=st.session_state.st_vals['debt'])
        tax_rate = st.number_input("Tax Rate (%)", value=21.0) # NUEVO
    
    # Calculate and display implied NOPAT
    nopat_implied = operating_income_base * (1 - tax_rate / 100)
    st.info(f"**Implied NOPAT:** {nopat_implied:.2f} millions {target_currency} (Operating Income × (1 - Tax Rate))")

    # TODOS LOS PARÁMETROS ORIGINALES
    st.header("Growth Parameters")
    growth_rate_5y = st.number_input("Growth Rate 5y (%)", value=15.0)
    growth_rate_5_10y = st.number_input("Growth Rate 5-10y (%)", value=8.0)

    st.header("Risk Parameters")
    risk_free_rate = st.number_input("Risk Free Rate (%)", value=4.5)
    equity_risk_premium = st.number_input("Equity Risk Premium (%)", value=5.13)
    WACC = st.number_input("WACC (%)", value=9.6)

    st.header("Reinvestment Rates")
    reinvestment_rate_5y = st.number_input("Reinvestment Rate 5y (%)", value=50.0)
    reinvestment_rate_5_10y = st.number_input("Reinvestment Rate 5-10y (%)", value=50.0)

    st.header("Standard Deviations")
    std_growth_5y = st.number_input("Std Growth 5y (%)", value=2.0)
    std_growth_5_10y = st.number_input("Std Growth 5-10y (%)", value=3.0)
    std_risk_free = st.number_input("Std Risk Free (%)", value=0.5)
    std_equity_premium = st.number_input("Std Equity Premium (%)", value=0.5)
    std_WACC = st.number_input("Std WACC (%)", value=0.5)
    std_reinv_5y = st.number_input("Std Reinv 5y (%)", value=2.5)
    std_reinv_5_10y = st.number_input("Std Reinv 5-10y (%)", value=5.0)

    n_simulations = st.number_input("Simulations", value=10000)
    submitted = st.form_submit_button("Run Simulation")

if submitted:
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
    tab1, tab2 = st.tabs(["New Analysis", "Performed Analyses"])
    with tab2:
        display_saved_analyses()
