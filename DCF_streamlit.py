import streamlit as st
import matplotlib.pyplot as plt
import io
import yfinance as yf
from DCF_main import run_monte_carlo_simulation

st.set_page_config(page_title="DCF Monte Carlo Valuation Tool", layout="wide")
st.title("DCF Monte Carlo Valuation Tool")

# --- 1. DATA RETRIEVAL LOGIC ---
@st.cache_data
def fetch_financial_data(ticker_symbol, target_curr):
    try:
        tk = yf.Ticker(ticker_symbol)
        info = tk.info
        native_curr = info.get("currency", "USD")
        
        data = {
            "price": info.get("currentPrice", 168.4),
            "shares": info.get("sharesOutstanding", 12700.0e6) / 1e6,
            "cash": info.get("totalCash", 96000.0e6) / 1e6,
            "ebit": info.get("ebitda", 154740.0e6) * 0.85 / 1e6, 
            "debt": info.get("totalDebt", 22000.0e6) / 1e6,
        }

        # Currency Conversion
        if target_curr and target_curr != native_curr:
            pair = f"{native_curr}{target_curr}=X"
            rate_df = yf.Ticker(pair).history(period="1d")
            if not rate_df.empty:
                rate = rate_df['Close'].iloc[-1]
                for key in ["price", "cash", "ebit", "debt"]:
                    data[key] *= rate
        return data
    except:
        return None

# Session state to hold fetched values
if 'defaults' not in st.session_state:
    st.session_state.defaults = {
        "price": 168.4, "shares": 12700.0, "cash": 96000.0, 
        "ebit": 154740.0, "debt": 22000.0, "curr": "USD"
    }

with st.sidebar:
    st.header("Search & Currency")
    ticker_search = st.text_input("Ticker Symbol", value="GOOGL").upper()
    target_currency = st.text_input("Target Currency", value=st.session_state.defaults['curr']).upper()
    
    if st.button("Fetch & Auto-fill"):
        fetched = fetch_financial_data(ticker_search, target_currency)
        if fetched:
            st.session_state.defaults.update(fetched)
            st.session_state.defaults['curr'] = target_currency
            st.success(f"Updated data for {ticker_search}")

# --- 2. ORIGINAL FORM (MINIMAL TOUCHES) ---
with st.sidebar.form("input_form"):
    st.header("Company Information")
    # Currency field removed here as it's now taken from Target Currency above
    company_name = st.text_input("Company Name", value=ticker_search)

    st.header("Financial Information")
    col1, col2 = st.columns(2)
    with col1:
        current_price = st.number_input("Current Price", value=st.session_state.defaults['price'])
        shares_outstanding = st.number_input("Shares Outstanding (millions)", value=st.session_state.defaults['shares'])
        cash = st.number_input("Cash (millions)", value=st.session_state.defaults['cash'])
    with col2:
        operating_income_base = st.number_input("Operating Income Base (millions)", value=st.session_state.defaults['ebit'])
        debt = st.number_input("Debt (millions)", value=st.session_state.defaults['debt'])

    # ALL ORIGINAL PARAMETERS RESTORED BELOW
    st.header("Growth Parameters")
    col1, col2 = st.columns(2)
    with col1:
        growth_rate_5y = st.number_input("Growth Rate 5y (%)", value=15.0)
    with col2:
        growth_rate_5_10y = st.number_input("Growth Rate 5-10y (%)", value=8.0)

    st.header("Risk Parameters")
    col1, col2 = st.columns(2)
    with col1:
        risk_free_rate = st.number_input("Risk Free Rate (%)", value=4.5)
        equity_risk_premium = st.number_input("Equity Risk Premium (%)", value=5.13)
    with col2:
        WACC = st.number_input("WACC (%)", value=9.6)

    st.header("Reinvestment Rates")
    col1, col2 = st.columns(2)
    with col1:
        reinvestment_rate_5y = st.number_input("Reinvestment Rate 5y (%)", value=50.0)
    with col2:
        reinvestment_rate_5_10y = st.number_input("Reinvestment Rate 5-10y (%)", value=50.0)

    st.header("Standard Deviations")
    col1, col2 = st.columns(2)
    with col1:
        std_growth_5y = st.number_input("Std Growth 5y (%)", value=2.0)
        std_risk_free = st.number_input("Std Risk Free (%)", value=0.5)
        std_WACC = st.number_input("Std WACC (%)", value=0.5)
        std_reinv_5y = st.number_input("Std Reinv 5y (%)", value=2.5)
    with col2:
        std_growth_5_10y = st.number_input("Std Growth 5-10y (%)", value=3.0)
        std_equity_premium = st.number_input("Std Equity Premium (%)", value=0.5)
        std_reinv_5_10y = st.number_input("Std Reinv 5-10y (%)", value=5.0)

    st.header("Simulation Parameters")
    n_simulations = st.number_input("Number of Simulations", value=10000, step=1000)

    submitted = st.form_submit_button("Run Monte Carlo Simulation")

# --- 3. EXECUTION ---
if submitted:
    params = {
        'company_name': company_name,
        'currency': target_currency, # Using the target currency from retrieval
        'current_price': current_price,
        'operating_income_base': operating_income_base,
        'shares_outstanding': shares_outstanding,
        'cash': cash,
        'debt': debt,
        'growth_rate_5y': growth_rate_5y / 100,
        'growth_rate_5_10y': growth_rate_5_10y / 100,
        'risk_free_rate': risk_free_rate / 100,
        'equity_risk_premium': equity_risk_premium / 100,
        'WACC': WACC / 100,
        'reinvestment_rate_5y': reinvestment_rate_5y / 100,
        'reinvestment_rate_5_10y': reinvestment_rate_5_10y / 100,
        'std_growth_5y': std_growth_5y / 100,
        'std_growth_5_10y': std_growth_5_10y / 100,
        'std_risk_free': std_risk_free / 100,
        'std_equity_premium': std_equity_premium / 100,
        'std_WACC': std_WACC / 100,
        'std_reinv_5y': std_reinv_5y / 100,
        'std_reinv_5_10y': std_reinv_5_10y / 100,
        'n_simulations': int(n_simulations)
    }
    
    with st.spinner("Running Monte Carlo simulation..."):
        # Fix NameError: variables are defined here before being used in tabs
        fig_es, fig_dist, fig_sens, summary = run_monte_carlo_simulation(params)
        
        st.success(f"Simulation for {company_name} completed!")

        tab1, tab2 = st.tabs(["Results", "Summary"])
        
        with tab1:
            st.pyplot(fig_es)
            buf_es = io.BytesIO()
            fig_es.savefig(buf_es, format="png")
            st.download_button(label="Download Results Plot", data=buf_es.getvalue(), 
                               file_name=f"{company_name}_results.png", mime="image/png")

        with tab2:
            col1_dist, col2_summary = st.columns([2, 1])
            with col1_dist:
                st.pyplot(fig_dist)
            with col2_summary:
                st.markdown("""<style>.summary-text { font-size: 0.9em; }</style>""", unsafe_allow_html=True)
                st.markdown("<h3 style='text-align: center;'>Valuation Summary</h3>", unsafe_allow_html=True)
                # Output exactly as requested in your original summary structure
                st.markdown(f"**Company:** {summary['company_name']}  \n**Date:** {summary['date']}  \n**---**")
                
                s_col1, s_col2 = st.columns(2)
                with s_col1:
                    st.markdown(f"""<div class="summary-text">
                        <p><strong>Current Price:</strong> {summary['current_price']}<br>
                        <strong>Mean Value:</strong> {summary['mean_value']}<br>
                        <strong>Upside:</strong> {summary['upside_potential']}</p>
                        <p><strong>Probabilities:</strong><br>Overvalued: {summary['prob_overvalued']}<br>Undervalued: {summary['prob_undervalued']}</p>
                    </div>""", unsafe_allow_html=True)
                with s_col2:
                    st.markdown(f"""<div class="summary-text">
                        <p><strong>Risk Metrics:</strong><br>VaR 95%: {summary['VaR 95%']}<br>Std Dev: {summary['Std. Deviation']}</p>
                    </div>""", unsafe_allow_html=True)

        plt.close('all')
