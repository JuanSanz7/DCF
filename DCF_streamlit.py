import streamlit as st
import matplotlib.pyplot as plt
import io
import yfinance as yf
import json
import shutil
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
        with open(ANALYSES_INDEX_FILE, "r") as f:
            return json.load(f)
    return {}


def save_analyses_index(index):
    """Save the index of all analyses"""
    with open(ANALYSES_INDEX_FILE, "w") as f:
        json.dump(index, f, indent=2)


def save_analysis(ticker, company_name, valuation_summary, fig_es, fig_distribution_only, fig_sensitivity):
    """Save an analysis to disk"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    analysis_id = f"{ticker}_{timestamp}"
    analysis_dir = ANALYSES_DIR / analysis_id
    analysis_dir.mkdir(exist_ok=True)

    # Save only the results plot
    fig_es.savefig(analysis_dir / "results_plot.png", dpi=150, bbox_inches="tight")

    # Save valuation summary as JSON
    with open(analysis_dir / "valuation_summary.json", "w") as f:
        json.dump(valuation_summary, f, indent=2)

    # Update index
    index = load_analyses_index()
    if ticker not in index:
        index[ticker] = {}
    index[ticker][analysis_id] = {
        "company_name": company_name,
        "timestamp": timestamp,
        "date": valuation_summary.get("date", ""),
        "analysis_id": analysis_id,
        "path": str(analysis_dir),
    }
    save_analyses_index(index)
    return analysis_id


def load_analysis(analysis_id):
    """Load a saved analysis"""
    analysis_dir = ANALYSES_DIR / analysis_id
    if not analysis_dir.exists():
        return None

    # Load valuation summary
    with open(analysis_dir / "valuation_summary.json", "r") as f:
        valuation_summary = json.load(f)

    # Load results plot
    results_plot_path = analysis_dir / "results_plot.png"

    return {"valuation_summary": valuation_summary, "results_plot": results_plot_path}


def delete_analysis(analysis_id):
    """Delete an analysis from disk and index"""
    index = load_analyses_index()

    # Find and remove from index
    for ticker in list(index.keys()):
        if analysis_id in index[ticker]:
            del index[ticker][analysis_id]
            # Remove ticker entry if no analyses left
            if not index[ticker]:
                del index[ticker]
            break

    # Save updated index
    save_analyses_index(index)

    # Delete analysis directory
    analysis_dir = ANALYSES_DIR / analysis_id
    if analysis_dir.exists():
        shutil.rmtree(analysis_dir)

    # Clear selected analysis if it was the deleted one
    if st.session_state.get("selected_analysis") == analysis_id:
        st.session_state.selected_analysis = None


def display_saved_analyses():
    """Display the saved analyses organized by ticker"""
    st.header("Performed Analyses")

    index = load_analyses_index()

    if not index:
        st.info("No analyses have been performed yet. Run a simulation to save your first analysis.")
        return

    # Initialize session state for selected analysis
    if "selected_analysis" not in st.session_state:
        st.session_state.selected_analysis = None

    # Check if an analysis was deleted
    if "delete_analysis_id" in st.session_state:
        delete_analysis(st.session_state.delete_analysis_id)
        del st.session_state.delete_analysis_id
        st.experimental_rerun()

    # Display analyses organized by ticker with View and Delete buttons
    for ticker in sorted(index.keys()):
        analyses = index[ticker]
        company_name = list(analyses.values())[0]["company_name"]

        with st.expander(
            f"📊 {ticker} - {company_name} ({len(analyses)} {'analyses' if len(analyses) > 1 else 'analysis'})"
        ):
            # Sort analyses by timestamp (newest first)
            sorted_analyses = sorted(analyses.items(), key=lambda x: x[1]["timestamp"], reverse=True)

            for analysis_id, analysis_info in sorted_analyses:
                date_str = analysis_info.get("date", "")
                timestamp_str = analysis_info.get("timestamp", "")
                # Format timestamp for display
                try:
                    dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    formatted_time = timestamp_str

                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.write(f"**Date:** {date_str} | **Time:** {formatted_time}")
                with col2:
                    if st.button("View", key=f"view_{analysis_id}"):
                        st.session_state.selected_analysis = analysis_id
                        st.session_state.active_tab = "Performed Analyses"
                        # Set query param to persist tab selection
                        st.experimental_set_query_params(tab="performed")
                        # Clear the radio button state to force it to use our index on rerun
                        if "tab_selector" in st.session_state:
                            del st.session_state["tab_selector"]
                        st.experimental_rerun()
                with col3:
                    if st.button("🗑️ Delete", key=f"delete_{analysis_id}"):
                        st.session_state.delete_analysis_id = analysis_id
                        st.experimental_rerun()

    # Display selected analysis
    if st.session_state.get("selected_analysis"):
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
    results_plot = analysis["results_plot"]
    if not Path(results_plot).exists():
        st.error(f"Results plot file not found for analysis: {analysis_id}")
        return

    valuation_summary = analysis["valuation_summary"]

    # Display results plot
    st.image(str(results_plot), caption="Results Plot", use_container_width=True)

    # Display summary
    st.markdown("### Valuation Summary")
    sum_col1, sum_col2 = st.columns(2)

    with sum_col1:
        st.markdown(
            f"""
            <div class="summary-text">
            <p><strong>Current Price:</strong> {valuation_summary.get('current_price','')}<br>
            <strong>Mean Value:</strong> {valuation_summary.get('mean_value','')}<br>
            <strong>Median Value:</strong> {valuation_summary.get('median_value','')}<br>
            <strong>Upside Potential:</strong> {valuation_summary.get('upside_potential','')}</p>

            <p><strong>Probabilities:</strong><br>
            Overvaluation: {valuation_summary.get('prob_overvalued','')}<br>
            Undervaluation: {valuation_summary.get('prob_undervalued','')}</p>

            <p><strong>Risk Metrics:</strong><br>
            VaR 95%: {valuation_summary.get('VaR 95%','')}<br>
            CVaR 95%: {valuation_summary.get('CVaR 95%','')}<br>
            Std. Deviation: {valuation_summary.get('Std. Deviation','')}</p>
            </div>
        """,
            unsafe_allow_html=True,
        )

    with sum_col2:
        vp = valuation_summary.get("Variable Parameters", {})
        tv = valuation_summary.get("Terminal Value Params", {})
        st.markdown(
            f"""
            <div class="summary-text">
            <p><strong>Variable Parameters:</strong><br>
            Growth 5y: {vp.get('Growth 5y','')}<br>
            Growth 5-10y: {vp.get('Growth 5-10y','')}<br>
            WACC: {vp.get('WACC','')}<br>
            Risk Premium: {vp.get('Risk Premium','')}<br>
            Risk Free Rate: {vp.get('Risk Free Rate','')}<br>
            Reinvestment 5y: {vp.get('Reinvestment 5y','')}<br>
            Reinvestment 5-10y: {vp.get('Reinvestment 5-10y','')}</p>

            <p><strong>Terminal Value Params:</strong><br>
            Term. Growth: {tv.get('Term. Growth','')}<br>
            Term. WACC: {tv.get('Term. WACC','')}<br>
            Term. Reinv Rate: {tv.get('Term. Reinv Rate','')}</p>
            </div>
        """,
            unsafe_allow_html=True,
        )


# --- DATA FETCHING LOGIC ---
def fetch_data(ticker, target_curr):
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        native_curr = info.get("currency", "USD")
        data = {
            "price": info.get("currentPrice", 168.4),
            "shares": (info.get("sharesOutstanding", 12700e6) / 1e6),
            "cash": (info.get("totalCash", 96000e6) / 1e6),
            # approximate ebit from ebitda if available; fallback default
            "ebit": (info.get("ebitda", 154740e6) * 0.85 / 1e6),
            "debt": (info.get("totalDebt", 22000e6) / 1e6),
        }
        if target_curr and target_curr != native_curr:
            fx_ticker = f"{native_curr}{target_curr}=X"
            fx = yf.Ticker(fx_ticker)
            hist = fx.history(period="1d")
            if not hist.empty:
                rate = hist["Close"].iloc[-1]
                for k in ["price", "cash", "ebit", "debt"]:
                    data[k] *= rate
        return data
    except Exception:
        return None


if "st_vals" not in st.session_state:
    st.session_state.st_vals = {
        "price": 168.4,
        "shares": 12700.0,
        "cash": 96000.0,
        "ebit": 154740.0,
        "debt": 22000.0,
    }

# Initialize tab state
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "New Analysis"


# Helper: dual slider + number input with two-way sync
def _make_dual_input(key, label, default, min_value, max_value, step, fmt="%.2f", integer=False):
    """
    Create a slider and a numeric input side-by-side that stay in sync.
    Returns the current value (float or int depending on `integer`).
    Keys used in session_state: f"{key}_slider" and f"{key}_input"
    """
    slider_key = f"{key}_slider"
    input_key = f"{key}_input"

    # Initialize state if not present
    if slider_key not in st.session_state:
        st.session_state[slider_key] = default
    if input_key not in st.session_state:
        st.session_state[input_key] = default

    # Callbacks to keep both widgets in sync
    def _sync_slider_to_input(k=key):
        st.session_state[f"{k}_input"] = st.session_state[f"{k}_slider"]

    def _sync_input_to_slider(k=key):
        st.session_state[f"{k}_slider"] = st.session_state[f"{k}_input"]

    col_a, col_b = st.columns([3, 1])
    with col_a:
        if integer:
            st.session_state[slider_key] = st.slider(
                label,
                min_value=int(min_value),
                max_value=int(max_value),
                value=int(st.session_state[slider_key]),
                step=int(step),
                key=slider_key,
                on_change=_sync_slider_to_input,
            )
        else:
            st.session_state[slider_key] = st.slider(
                label,
                min_value=float(min_value),
                max_value=float(max_value),
                value=float(st.session_state[slider_key]),
                step=float(step),
                format=fmt,
                key=slider_key,
                on_change=_sync_slider_to_input,
            )
    with col_b:
        if integer:
            st.session_state[input_key] = st.number_input(
                "",
                min_value=int(min_value),
                max_value=int(max_value),
                value=int(st.session_state[input_key]),
                step=int(step),
                key=input_key,
                on_change=_sync_input_to_slider,
                format="%d",
            )
        else:
            st.session_state[input_key] = st.number_input(
                "",
                min_value=float(min_value),
                max_value=float(max_value),
                value=float(st.session_state[input_key]),
                step=float(step),
                key=input_key,
                on_change=_sync_input_to_slider,
                format=fmt,
            )

    return int(st.session_state[slider_key]) if integer else float(st.session_state[slider_key])


with st.sidebar:
    st.header("1. Automatic Search")
    t_input = st.text_input("Ticker", value="GOOGL").upper()
    target_currency = st.text_input("Target Currency", value="USD").upper()
    if st.button("Fetch & Auto-fill"):
        with st.spinner("Fetching data..."):
            res = fetch_data(t_input, target_currency)
        if res:
            # update general store
            st.session_state.st_vals.update(res)

            # Map fetched fields to widget keys used by _make_dual_input and update them
            mapping = {
                "current_price": res.get("price"),
                "shares_outstanding": res.get("shares"),
                "cash": res.get("cash"),
                "operating_income_base": res.get("ebit"),
                "debt": res.get("debt"),
            }
            for k, v in mapping.items():
                if v is None:
                    continue
                try:
                    val = float(v)
                except Exception:
                    continue
                st.session_state[f"{k}_slider"] = val
                st.session_state[f"{k}_input"] = val

            st.success("Auto-fill applied.")
            # rerun so form widgets pick up the new session_state values
            st.experimental_rerun()
        else:
            st.error("Could not fetch data. Check ticker, currency and internet connection.")


with st.sidebar.form("input_form"):
    st.header("Company Information")
    company_name = st.text_input("Company Name", value=t_input)

    st.header("Financial Information")

    # determine sensible maxima based on fetched/default values
    current_price_default = st.session_state.st_vals.get("price", 168.4)
    shares_default = st.session_state.st_vals.get("shares", 12700.0)
    cash_default = st.session_state.st_vals.get("cash", 96000.0)
    ebit_default = st.session_state.st_vals.get("ebit", 154740.0)
    debt_default = st.session_state.st_vals.get("debt", 22000.0)

    # Current price, shares, cash, operating income, debt, tax rate
    with st.container():
        current_price = _make_dual_input(
            key="current_price",
            label="Current Price",
            default=current_price_default,
            min_value=0.0,
            max_value=max(current_price_default * 5, 10.0),
            step=0.1,
            fmt="%.2f",
        )

        shares_outstanding = _make_dual_input(
            key="shares_outstanding",
            label="Shares Outstanding (millions)",
            default=shares_default,
            min_value=0.0,
            max_value=max(shares_default * 5, 1.0),
            step=1,
            fmt="%.1f",
        )

        cash = _make_dual_input(
            key="cash",
            label="Cash (millions)",
            default=cash_default,
            min_value=0.0,
            max_value=max(cash_default * 2, 10.0),
            step=1,
            fmt="%.1f",
        )

        operating_income_base = _make_dual_input(
            key="operating_income_base",
            label="Operating Income Base (millions)",
            default=ebit_default,
            min_value=0.0,
            max_value=max(ebit_default * 3, 10.0),
            step=1,
            fmt="%.1f",
        )

        debt = _make_dual_input(
            key="debt",
            label="Debt (millions)",
            default=debt_default,
            min_value=0.0,
            max_value=max(debt_default * 2, 10.0),
            step=1,
            fmt="%.1f",
        )

        tax_rate = _make_dual_input(
            key="tax_rate",
            label="Tax Rate (%)",
            default=21.0,
            min_value=0.0,
            max_value=100.0,
            step=0.1,
            fmt="%.1f",
        )

    # Calculate and display implied NOPAT
    nopat_implied = operating_income_base * (1 - tax_rate / 100)
    st.info(f"**Implied NOPAT:** {nopat_implied:.2f} millions {target_currency} (Operating Income × (1 - Tax Rate))")

    # Growth Parameters
    st.header("Growth Parameters")
    growth_rate_5y = _make_dual_input(
        key="growth_rate_5y",
        label="Growth Rate 5y (%)",
        default=15.0,
        min_value=-50.0,
        max_value=200.0,
        step=0.1,
        fmt="%.1f",
    )
    growth_rate_5_10y = _make_dual_input(
        key="growth_rate_5_10y",
        label="Growth Rate 5-10y (%)",
        default=8.0,
        min_value=-50.0,
        max_value=200.0,
        step=0.1,
        fmt="%.1f",
    )

    # Risk Parameters
    st.header("Risk Parameters")
    risk_free_rate = _make_dual_input(
        key="risk_free_rate",
        label="Risk Free Rate (%)",
        default=4.5,
        min_value=-5.0,
        max_value=50.0,
        step=0.1,
        fmt="%.2f",
    )
    equity_risk_premium = _make_dual_input(
        key="equity_risk_premium",
        label="Equity Risk Premium (%)",
        default=5.13,
        min_value=0.0,
        max_value=50.0,
        step=0.1,
        fmt="%.2f",
    )
    WACC = _make_dual_input(
        key="WACC",
        label="WACC (%)",
        default=9.6,
        min_value=0.0,
        max_value=50.0,
        step=0.1,
        fmt="%.2f",
    )

    # Reinvestment Rates
    st.header("Reinvestment Rates")
    reinvestment_rate_5y = _make_dual_input(
        key="reinvestment_rate_5y",
        label="Reinvestment Rate 5y (%)",
        default=50.0,
        min_value=0.0,
        max_value=100.0,
        step=0.1,
        fmt="%.1f",
    )
    reinvestment_rate_5_10y = _make_dual_input(
        key="reinvestment_rate_5_10y",
        label="Reinvestment Rate 5-10y (%)",
        default=50.0,
        min_value=0.0,
        max_value=100.0,
        step=0.1,
        fmt="%.1f",
    )

    # Standard Deviations
    st.header("Standard Deviations")
    std_growth_5y = _make_dual_input(
        key="std_growth_5y",
        label="Std Growth 5y (%)",
        default=2.0,
        min_value=0.0,
        max_value=50.0,
        step=0.1,
        fmt="%.2f",
    )
    std_growth_5_10y = _make_dual_input(
        key="std_growth_5_10y",
        label="Std Growth 5-10y (%)",
        default=3.0,
        min_value=0.0,
        max_value=50.0,
        step=0.1,
        fmt="%.2f",
    )
    std_risk_free = _make_dual_input(
        key="std_risk_free",
        label="Std Risk Free (%)",
        default=0.5,
        min_value=0.0,
        max_value=10.0,
        step=0.01,
        fmt="%.2f",
    )
    std_equity_premium = _make_dual_input(
        key="std_equity_premium",
        label="Std Equity Premium (%)",
        default=0.5,
        min_value=0.0,
        max_value=10.0,
        step=0.01,
        fmt="%.2f",
    )
    std_WACC = _make_dual_input(
        key="std_WACC",
        label="Std WACC (%)",
        default=0.5,
        min_value=0.0,
        max_value=10.0,
        step=0.01,
        fmt="%.2f",
    )
    std_reinv_5y = _make_dual_input(
        key="std_reinv_5y",
        label="Std Reinv 5y (%)",
        default=2.5,
        min_value=0.0,
        max_value=50.0,
        step=0.1,
        fmt="%.2f",
    )
    std_reinv_5_10y = _make_dual_input(
        key="std_reinv_5_10y",
        label="Std Reinv 5-10y (%)",
        default=5.0,
        min_value=0.0,
        max_value=50.0,
        step=0.1,
        fmt="%.2f",
    )

    # Simulations (integer)
    n_simulations = _make_dual_input(
        key="n_simulations",
        label="Simulations",
        default=10000,
        min_value=100,
        max_value=100000,
        step=100,
        fmt="%d",
        integer=True,
    )

    submitted = st.form_submit_button("Run Simulation")

# If an analysis is selected for viewing, force to else block for proper tab handling
# This ensures consistent behavior whether coming from a new analysis or directly
viewing_analysis = st.session_state.get("selected_analysis") and not submitted

if submitted and not viewing_analysis:
    params = {
        "company_name": company_name,
        "currency": target_currency,
        "current_price": float(current_price),
        "shares_outstanding": float(shares_outstanding),
        "cash": float(cash),
        "debt": float(debt),
        "operating_income_base": float(operating_income_base),
        "tax_rate": float(tax_rate) / 100,
        "growth_rate_5y": float(growth_rate_5y) / 100,
        "growth_rate_5_10y": float(growth_rate_5_10y) / 100,
        "risk_free_rate": float(risk_free_rate) / 100,
        "equity_risk_premium": float(equity_risk_premium) / 100,
        "WACC": float(WACC) / 100,
        "reinvestment_rate_5y": float(reinvestment_rate_5y) / 100,
        "reinvestment_rate_5_10y": float(reinvestment_rate_5_10y) / 100,
        "std_growth_5y": float(std_growth_5y) / 100,
        "std_growth_5_10y": float(std_growth_5_10y) / 100,
        "std_risk_free": float(std_risk_free) / 100,
        "std_equity_premium": float(std_equity_premium) / 100,
        "std_WACC": float(std_WACC) / 100,
        "std_reinv_5y": float(std_reinv_5y) / 100,
        "std_reinv_5_10y": float(std_reinv_5_10y) / 100,
        "n_simulations": int(n_simulations),
    }

    with st.spinner("Running Monte Carlo simulation..."):
        fig_es, fig_distribution_only, fig_sensitivity, valuation_summary = run_monte_carlo_simulation(params)

        # Save the analysis
        analysis_id = save_analysis(
            t_input, company_name, valuation_summary, fig_es, fig_distribution_only, fig_sensitivity
        )
        st.success(f"Monte Carlo simulation for {company_name} completed successfully! Analysis saved.")

        tab1, tab2, tab3 = st.tabs(["Results", "Summary", "Performed Analyses"])

        with tab1:
            st.pyplot(fig_es)

            # Add download button for the results plot
            buf_es = io.BytesIO()
            fig_es.savefig(buf_es, format="png")
            st.download_button(
                label="Download Results Plot",
                data=buf_es.getvalue(),
                file_name=f"{company_name}_results_plot.png",
                mime="image/png",
            )

        with tab2:
            col1_dist, col2_summary = st.columns([2, 1])
            with col1_dist:
                st.pyplot(fig_distribution_only)
                buf_dist_summary = io.BytesIO()
                fig_distribution_only.savefig(buf_dist_summary, format="png")
                st.download_button(
                    label="Download Intrinsic Value Distribution Plot",
                    data=buf_dist_summary.getvalue(),
                    file_name=f"{company_name}_intrinsic_value_distribution_summary_plot.png",
                    mime="image/png",
                )

            with col2_summary:
                st.markdown(
                    """
                    <style>
                    .summary-text {
                        font-size: 0.9em;
                    }
                    </style>
                """,
                    unsafe_allow_html=True,
                )

                st.markdown("<h3 style='text-align: center;'>Valuation Summary</h3>", unsafe_allow_html=True)

                st.markdown(
                    f"""
                    <div class="summary-text">
                    <p><strong>Company:</strong> {valuation_summary.get('company_name','')}<br>
                    <strong>Date:</strong> {valuation_summary.get('date','')}<br>
                    <strong>-------------------</strong></p>
                    </div>
                """,
                    unsafe_allow_html=True,
                )

                sum_col1, sum_col2 = st.columns(2)

                with sum_col1:
                    st.markdown(
                        f"""
                        <div class="summary-text">
                        <p><strong>Current Price:</strong> {valuation_summary.get('current_price','')}<br>
                        <strong>Mean Value:</strong> {valuation_summary.get('mean_value','')}<br>
                        <strong>Median Value:</strong> {valuation_summary.get('median_value','')}<br>
                        <strong>Upside Potential:</strong> {valuation_summary.get('upside_potential','')}</p>

                        <p><strong>Probabilities:</strong><br>
                        Overvaluation: {valuation_summary.get('prob_overvalued','')}<br>
                        Undervaluation: {valuation_summary.get('prob_undervalued','')}</p>

                        <p><strong>Risk Metrics:</strong><br>
                        VaR 95%: {valuation_summary.get('VaR 95%','')}<br>
                        CVaR 95%: {valuation_summary.get('CVaR 95%','')}<br>
                        Std. Deviation: {valuation_summary.get('Std. Deviation','')}</p>
                        </div>
                    """,
                        unsafe_allow_html=True,
                    )

                with sum_col2:
                    vp = valuation_summary.get("Variable Parameters", {})
                    tv = valuation_summary.get("Terminal Value Params", {})
                    st.markdown(
                        f"""
                        <div class="summary-text">
                        <p><strong>Variable Parameters:</strong><br>
                        Growth 5y: {vp.get('Growth 5y','')}<br>
                        Growth 5-10y: {vp.get('Growth 5-10y','')}<br>
                        WACC: {vp.get('WACC','')}<br>
                        Risk Premium: {vp.get('Risk Premium','')}<br>
                        Risk Free Rate: {vp.get('Risk Free Rate','')}<br>
                        Reinvestment 5y: {vp.get('Reinvestment 5y','')}<br>
                        Reinvestment 5-10y: {vp.get('Reinvestment 5-10y','')}</p>

                        <p><strong>Terminal Value Params:</strong><br>
                        Term. Growth: {tv.get('Term. Growth','')}<br>
                        Term. WACC: {tv.get('Term. WACC','')}<br>
                        Term. Reinv Rate: {tv.get('Term. Reinv Rate','')}</p>
                        </div>
                    """,
                        unsafe_allow_html=True,
                    )

        # Close the plot figures to free up memory
        plt.close(fig_es)
        plt.close(fig_distribution_only)
        plt.close(fig_sensitivity)

        # Performed Analyses tab
        with tab3:
            display_saved_analyses()
else:
    # Show Performed Analyses tab even when no simulation is running
    tab_names = ["New Analysis", "Performed Analyses"]

    # Check query params first (most reliable for persistence)
    query_tab = None
    if "tab" in st.experimental_get_query_params():
        tab_param = st.experimental_get_query_params().get("tab")
        query_tab = tab_param[0] if isinstance(tab_param, list) else tab_param

    # PRIORITY: If an analysis is selected, ALWAYS force to Performed Analyses tab
    if st.session_state.get("selected_analysis"):
        st.session_state.active_tab = "Performed Analyses"
        if query_tab != "performed":
            st.experimental_set_query_params(tab="performed")
        if "tab_selector" in st.session_state:
            del st.session_state["tab_selector"]
        default_index = 1
    elif query_tab == "performed":
        st.session_state.active_tab = "Performed Analyses"
        default_index = 1
    elif st.session_state.active_tab == "Performed Analyses":
        default_index = 1
    else:
        default_index = 0
        if st.session_state.active_tab != "New Analysis":
            st.session_state.active_tab = "New Analysis"

    # Create tabs with radio buttons to maintain state
    if st.session_state.get("selected_analysis"):
        tab_selection = st.radio("Navigation", options=tab_names, index=1, horizontal=True, key="tab_selector")
    else:
        tab_selection = st.radio("Navigation", options=tab_names, index=default_index, horizontal=True, key="tab_selector")

    # Update session state and query params when tab changes
    if tab_selection != st.session_state.active_tab:
        st.session_state.active_tab = tab_selection
        if tab_selection == "Performed Analyses":
            st.experimental_set_query_params(tab="performed")
        else:
            st.experimental_set_query_params(tab="new")
            if "selected_analysis" in st.session_state:
                st.session_state.selected_analysis = None

    if tab_selection == "New Analysis":
        st.info("Fill out the form in the sidebar and click 'Run Simulation' to perform a new analysis.")
    else:
        display_saved_analyses()
