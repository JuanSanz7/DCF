import streamlit as st
import matplotlib.pyplot as plt
import io
import yfinance as yf
from DCF_main import run_monte_carlo_simulation

st.set_page_config(page_title="DCF Monte Carlo Valuation Tool", layout="wide")
st.title("DCF Monte Carlo Valuation Tool")

# Lógica de búsqueda
@st.cache_data
def fetch_financial_data(ticker, target_curr):
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

if 'vals' not in st.session_state:
    st.session_state.vals = {"price": 168.4, "shares": 12700.0, "cash": 96000.0, "ebit": 154740.0, "debt": 22000.0, "curr": "USD"}

with st.sidebar:
    st.header("Search")
    t_search = st.text_input("Ticker", value="GOOGL").upper()
    # Este campo reemplaza al original de Currency
    target_currency = st.text_input("Target Currency", value=st.session_state.vals['curr']).upper()
    if st.button("Fetch Data"):
        res = fetch_financial_data(t_search, target_currency)
        if res: 
            st.session_state.vals.update(res)
            st.session_state.vals['curr'] = target_currency

with st.sidebar.form("input_form"):
    st.header("Company Information")
    company_name = st.text_input("Company Name", value=t_search)
    # EL CAMPO CURRENCY SE HA ELIMINADO DE AQUÍ PORQUE SE USA target_currency

    st.header("Financial Information")
    col1, col2 = st.columns(2)
    with col1:
        current_price = st.number_input("Current Price", value=st.session_state.vals['price'])
        shares_outstanding = st.number_input("Shares Outstanding (millions)", value=st.session_state.vals['shares'])
        cash = st.number_input("Cash (millions)", value=st.session_state.vals['cash'])
    with col2:
        operating_income_base = st.number_input("Operating Income Base (millions)", value=st.session_state.vals['ebit'])
        debt = st.number_input("Debt (millions)", value=st.session_state.vals['debt'])

    # TODOS LOS PARÁMETROS ORIGINALES RESTAURADOS
    st.header("Growth Parameters")
    growth_rate_5
