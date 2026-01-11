import streamlit as st
import matplotlib.pyplot as plt
import io
import yfinance as yf
from DCF_main import run_monte_carlo_simulation

st.set_page_config(page_title="DCF Monte Carlo Valuation Tool", layout="wide")
st.title("DCF Monte Carlo Valuation Tool")

# Lógica de búsqueda y conversión
@st.cache_data
def fetch_and_convert_data(ticker_symbol, target_currency):
    try:
        tk = yf.Ticker(ticker_symbol)
        info = tk.info
        native_curr = info.get("currency", "USD")
        
        # Valores base
        data = {
            "price": info.get("currentPrice", 168.4),
            "shares": info.get("sharesOutstanding", 12700.0e6) / 1e6,
            "cash": info.get("totalCash", 96000.0e6) / 1e6,
            "ebit": info.get("ebitda", 154740.0e6) * 0.85 / 1e6,
            "debt": info.get("totalDebt", 22000.0e6) / 1e6,
            "currency": native_curr
        }

        # Conversión de divisa si el usuario solicita una distinta a la nativa
        if target_currency and target_currency != native_curr:
            pair = f"{native_curr}{target_currency}=X"
            rate = yf.Ticker(pair).history(period="1d")['Close'].iloc[-1]
            for key in ["price", "cash", "ebit", "debt"]:
                data[key] *= rate
            data["currency"] = target_currency
        return data
    except: return None

# Inicialización de valores para los campos
if 'fin' not in st.session_state:
    st.session_state.fin = {"price": 168.4, "shares": 12700.0, "cash": 96000.0, "ebit": 154740.0, "debt": 22000.0, "curr": "USD"}

with st.sidebar:
    st.header("1. Data Retrieval")
    t_input = st.text_input("Ticker Symbol", value="GOOGL").upper()
    c_input = st.text_input("Target Currency", value=st.session_state.fin['curr']).upper()
    if st.button("Fetch & Auto-fill"):
        fetched = fetch_and_convert_data(t_input, c_input)
        if fetched:
            st.session_state.fin = {"price": fetched['price'], "shares": fetched['shares'], "cash": fetched['cash'], 
                                    "ebit": fetched['ebit'], "debt": fetched['debt'], "curr": fetched['currency']}
            st.success(f"Loaded {t_input} in {c_input}")

with st.sidebar.form("input_form"):
    st.header("2. Company Information")
    col1, col2 = st.columns(2)
    with col1: company_name = st.text_input("Company Name", value=t_input)
    with col2: currency = st.text_input("Currency", value=st.session_state.fin['curr'])

    st.header("Financial Information")
    col1, col2 = st.columns(2)
    with col1:
        current_price = st.number_input("Current Price", value=st.session_state.fin['price'])
        shares_outstanding = st.number_input("Shares Outstanding (millions)", value=st.session_state.fin['shares'])
        cash = st.number_input("Cash (millions)", value=st.session_state.fin['cash'])
    with col2:
        operating_income_base = st.number_input("Operating Income Base (millions)", value=st.session_state.fin['ebit'])
        debt = st.number_input("Debt (millions)", value=st.session_state.fin['debt'])

    # --- RESTO DEL FORMULARIO (Growth, Risk, Reinv, StdDev) IDÉNTICO AL ORIGINAL ---
    # ... [Cualquier campo adicional del original va aquí] ...
    st.header("Growth Parameters")
    col1, col2 = st.columns(2)
    with col1: growth_rate_5y = st.number_input("Growth Rate 5y (%)", value=15.0)
    with col2: growth_rate_5_10y = st.number_input("Growth Rate 5-10y (%)", value=8.0)
    
    # (... resto de los inputs del sidebar ...)
    # Al final del sidebar:
    submitted = st.form_submit_button("Run Monte Carlo Simulation")

if submitted:
    # Lógica de empaquetado y llamada a run_monte_carlo_simulation...
    # (Manteniendo la visualización original de las pestañas)
    
    # REINSTAURACIÓN DE LA PESTAÑA SUMMARY (HTML/CSS ORIGINAL)
    tab1, tab2 = st.tabs(["Results", "Summary"])
    with tab1:
        st.pyplot(fig_es)
        # ... (Botón de descarga original) ...
    
    with tab2:
        col1_dist, col2_summary = st.columns([2, 1])
        with col1_dist:
            st.pyplot(fig_distribution_only)
        with col2_summary:
            st.markdown("""<style>.summary-text { font-size: 0.9em; }</style>""", unsafe_allow_html=True)
            st.markdown("<h3 style='text-align: center;'>Valuation Summary</h3>", unsafe_allow_html=True)
            st.markdown(f"""<div class="summary-text"><p><strong>Company:</strong> {valuation_summary['company_name']}<br><strong>Date:</strong> {valuation_summary['date']}<br><strong>-------------------</strong></p></div>""", unsafe_allow_html=True)
            sum_col1, sum_col2 = st.columns(2)
            with sum_col1:
                st.markdown(f"""<div class="summary-text"><p><strong>Current Price:</strong> {valuation_summary['current_price']}<br><strong>Mean Value:</strong> {valuation_summary['mean_value']}<br><strong>Median Value:</strong> {valuation_summary['median_value']}<br><strong>Upside Potential:</strong> {valuation_summary['upside_potential']}</p><p><strong>Probabilities:</strong><br>Overvaluation: {valuation_summary['prob_overvalued']}<br>Undervaluation: {valuation_summary['prob_undervalued']}</p><p><strong>Risk Metrics:</strong><br>VaR 95%: {valuation_summary['VaR 95%']}<br>CVaR 95%: {valuation_summary['CVaR 95%']}<br>Std. Deviation: {valuation_summary['Std. Deviation']}</p></div>""", unsafe_allow_html=True)
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
