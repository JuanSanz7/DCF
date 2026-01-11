import streamlit as st
import matplotlib.pyplot as plt
import io
import yfinance as yf # CAMBIO: Nuevo import
from DCF_main import run_monte_carlo_simulation

st.set_page_config(page_title="DCF Monte Carlo Valuation Tool", layout="wide")
st.title("DCF Monte Carlo Valuation Tool")

# CAMBIO: Función para autocompletar datos financieros
@st.cache_data
def fetch_stock_financials(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        return {
            "price": info.get("currentPrice", 0.0),
            "shares": info.get("sharesOutstanding", 0.0) / 1e6,
            "cash": info.get("totalCash", 0.0) / 1e6,
            "debt": info.get("totalDebt", 0.0) / 1e6,
            "ebit": info.get("ebitda", 0.0) * 0.8 / 1e6, # Estimación EBIT si no hay directo
            "currency": info.get("currency", "USD")
        }
    except:
        return None

with st.sidebar.form("input_form"):
    st.header("Company Information")
    col1, col2 = st.columns(2)
    with col1:
        company_name = st.text_input("Ticker Symbol", value="GOOGL").upper() # Usamos ticker para buscar
    with col2:
        fetch_online = st.form_submit_button("Fetch Online Data") # Botón para disparar búsqueda

    # Lógica de autocompletado si se pulsa el botón o por defecto
    scraped = fetch_stock_financials(company_name) if fetch_online else None

    st.header("Financial Information")
    col1, col2 = st.columns(2)
    with col1:
        current_price = st.number_input("Current Price", value=scraped['price'] if scraped else 168.4)
        shares_outstanding = st.number_input("Shares Outstanding (millions)", value=scraped['shares'] if scraped else 12700.00)
        cash = st.number_input("Cash (millions)", value=scraped['cash'] if scraped else 96000.00)
        currency = st.text_input("Currency", value=scraped['currency'] if scraped else "USD")
    with col2:
        # CAMBIO: Introducimos Operating Income y Tax Rate
        operating_income = st.number_input("Operating Income (millions)", value=scraped['ebit'] if scraped else 154740.00)
        tax_rate = st.number_input("Tax Rate (%)", value=21.0)
        debt = st.number_input("Debt (millions)", value=scraped['debt'] if scraped else 22000.00)

    # Cálculo dinámico de NOPAT
    nopat_calculated = operating_income * (1 - (tax_rate / 100))
    st.info(f"**Calculated NOPAT: {nopat_calculated:,.2f} {currency}**")

    st.header("Growth Parameters")
    col1, col2 = st.columns(2)
    with col1:
        growth_rate_5y = st.slider("Growth Rate 1-5y (%)", 0.0, 50.0, 12.0) / 100
        growth_rate_5_10y = st.slider("Growth Rate 5-10y (%)", 0.0, 50.0, 8.0) / 100
        WACC = st.slider("WACC (%)", 5.0, 20.0, 9.0) / 100
    with col2:
        reinvestment_rate_5y = st.slider("Reinv. Rate 1-5y (%)", 0.0, 100.0, 20.0) / 100
        reinvestment_rate_5_10y = st.slider("Reinv. Rate 5-10y (%)", 0.0, 100.0, 15.0) / 100
        n_simulations = st.number_input("Simulations", value=10000)

    # Botón principal de ejecución
    submit_button = st.form_submit_button("Run Full Valuation Simulation")

if submit_button:
    params = {
        'company_name': company_name,
        'currency': currency,
        'current_price': current_price,
        'nopat_base': nopat_calculated, # CAMBIO: Enviamos NOPAT
        'shares_outstanding': shares_outstanding,
        'cash': cash,
        'debt': debt,
        'growth_rate_5y': growth_rate_5y,
        'growth_rate_5_10y': growth_rate_5_10y,
        'risk_free_rate': 0.04,
        'equity_risk_premium': 0.05,
        'WACC': WACC,
        'reinvestment_rate_5y': reinvestment_rate_5y,
        'reinvestment_rate_5_10y': reinvestment_rate_5_10y,
        'std_growth_5y': 0.02,
        'std_growth_5_10y': 0.01,
        'std_risk_free': 0.005,
        'std_equity_premium': 0.01,
        'std_WACC': 0.01,
        'std_reinv_5y': 0.05,
        'std_reinv_5_10y': 0.05,
        'n_simulations': n_simulations
    }

    # Execute simulation
    fig_es, fig_distribution_only, fig_sensitivity, valuation_summary = run_monte_carlo_simulation(params)

    # --- TODO TU CÓDIGO DE VISUALIZACIÓN DE MÉTRICAS Y HTML ORIGINAL SIGUE IGUAL ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Mean Intrinsic Value", valuation_summary['mean_value'])
    col2.metric("Upside Potential", valuation_summary['upside_potential'])
    col3.metric("Prob. Undervalued", valuation_summary['prob_undervalued'])

    st.pyplot(fig_es)

    # Summary Report (HTML de tu script original)
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

    plt.close(fig_es)
