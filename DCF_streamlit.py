import streamlit as st
import matplotlib.pyplot as plt
import io
import yfinance as yf # Nuevo import
from DCF_main import run_monte_carlo_simulation

st.set_page_config(page_title="DCF Monte Carlo Valuation Tool", layout="wide")
st.title("DCF Monte Carlo Valuation Tool")

@st.cache_data
def get_financials(ticker):
    try:
        tk = yf.Ticker(ticker)
        info = tk.info
        return {
            "p": info.get("currentPrice", 168.4),
            "s": info.get("sharesOutstanding", 12700.0e6) / 1e6,
            "c": info.get("totalCash", 96000.0e6) / 1e6,
            "d": info.get("totalDebt", 22000.0e6) / 1e6,
            "e": info.get("ebitda", 154740.0e6) * 0.85 / 1e6, # EBIT estimado
            "curr": info.get("currency", "USD")
        }
    except: return None

with st.sidebar.form("input_form"):
    st.header("Search & Auto-fill")
    ticker_input = st.text_input("Ticker Symbol", value="GOOGL").upper()
    fetch_btn = st.form_submit_button("Fetch Online Data")
    
    s = get_financials(ticker_input) if fetch_btn else None

    st.header("Financial Information")
    col1, col2 = st.columns(2)
    with col1:
        current_price = st.number_input("Current Price", value=s['p'] if s else 168.4)
        shares_outstanding = st.number_input("Shares Outstanding (millions)", value=s['s'] if s else 12700.0)
        cash = st.number_input("Cash (millions)", value=s['c'] if s else 96000.0)
        currency = st.text_input("Currency", value=s['curr'] if s else "USD")
    with col2:
        # EBIT y Tax Rate para calcular NOPAT
        ebit = st.number_input("Operating Income (EBIT) (millions)", value=s['e'] if s else 154740.0)
        tax_rate = st.number_input("Tax Rate (%)", value=21.0)
        debt = st.number_input("Debt (millions)", value=s['d'] if s else 22000.0)

    # Cálculo de NOPAT
    nopat_calculated = ebit * (1 - (tax_rate / 100))
    st.info(f"**NOPAT calculado para simulación: {nopat_calculated:,.2f} {currency}**")

    # --- RESTO DE PARÁMETROS EXACTAMENTE IGUAL AL ORIGINAL ---
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

    n_simulations = st.number_input("Number of Simulations", value=10000, step=1000)
    submitted = st.form_submit_button("Run Monte Carlo Simulation")

if submitted:
    params = {
        'company_name': ticker_input, 'currency': currency, 'current_price': current_price,
        'nopat_base': nopat_calculated, 'shares_outstanding': shares_outstanding,
        'cash': cash, 'debt': debt, 'growth_rate_5y': growth_rate_5y / 100,
        'growth_rate_5_10y': growth_rate_5_10y / 100, 'risk_free_rate': risk_free_rate / 100,
        'equity_risk_premium': equity_risk_premium / 100, 'WACC': WACC / 100,
        'reinvestment_rate_5y': reinvestment_rate_5y / 100, 'reinvestment_rate_5_10y': reinvestment_rate_5_10y / 100,
        'std_growth_5y': std_growth_5y / 100, 'std_growth_5_10y': std_growth_5_10y / 100,
        'std_risk_free': std_risk_free / 100, 'std_equity_premium': std_equity_premium / 100,
        'std_WACC': std_WACC / 100, 'std_reinv_5y': std_reinv_5y / 100, 'std_reinv_5_10y': std_reinv_5_10y / 100,
        'n_simulations': int(n_simulations)
    }
    
    # --- TODO EL BLOQUE DE VISUALIZACIÓN Streamlit SIGUE IGUAL ---
    with st.spinner("Running simulation..."):
        fig_es, _, _, valuation_summary = run_monte_carlo_simulation(params)
        st.pyplot(fig_es)
        
        # El resto de tabs y resúmenes HTML originales de tu archivo...
