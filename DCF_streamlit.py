import streamlit as st
import matplotlib.pyplot as plt
import io
import yfinance as yf
from DCF_main import run_monte_carlo_simulation

st.set_page_config(page_title="DCF Monte Carlo Valuation Tool", layout="wide")
st.title("DCF Monte Carlo Valuation Tool")

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

    fig_es, fig_dist, fig_sens, valuation_summary = run_monte_carlo_simulation(params)

    # --- RENDERIZADO DE TABS ---
    tab1, tab2 = st.tabs(["Results", "Summary"])
    with tab1:
        st.pyplot(fig_es)
    with tab2:
        col_dist, col_sum = st.columns([2, 1])
        with col_dist:
            st.pyplot(fig_dist)
        with col_sum:
            st.markdown(f"### Valuation: {valuation_summary['company_name']}")
            st.write(f"**Mean Value:** {valuation_summary['mean_value']}")
            st.write(f"**Upside:** {valuation_summary['upside_potential']}")
            st.write(f"**Prob. Undervalued:** {valuation_summary['prob_undervalued']}")
            st.markdown("---")
            st.json(valuation_summary['Variable Parameters']) # Para no perder ningún dato

    plt.close('all')
