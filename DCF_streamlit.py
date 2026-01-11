import streamlit as st
import matplotlib.pyplot as plt
import io
import yfinance as yf
from DCF_main import run_monte_carlo_simulation

st.set_page_config(page_title="DCF Monte Carlo Valuation Tool", layout="wide")
st.title("DCF Monte Carlo Valuation Tool")

# Función de obtención de datos con conversión de moneda integrada
@st.cache_data
def fetch_financial_data(ticker_symbol, target_curr):
    try:
        tk = yf.Ticker(ticker_symbol)
        info = tk.info
        native_curr = info.get("currency", "USD")
        
        # Datos base en moneda nativa
        data = {
            "price": info.get("currentPrice", 0.0),
            "shares": info.get("sharesOutstanding", 0.0) / 1e6,
            "cash": info.get("totalCash", 0.0) / 1e6,
            "ebit": info.get("ebitda", 0.0) * 0.85 / 1e6, # Estimación conservadora de EBIT
            "debt": info.get("totalDebt", 0.0) / 1e6,
            "native_curr": native_curr
        }

        # Conversión automática si la moneda objetivo es distinta
        if target_curr and target_curr != native_curr:
            pair = f"{native_curr}{target_curr}=X"
            rate_data = yf.Ticker(pair).history(period="1d")
            if not rate_data.empty:
                rate = rate_data['Close'].iloc[-1]
                for key in ["price", "cash", "ebit", "debt"]:
                    data[key] *= rate
        return data
    except Exception as e:
        st.sidebar.error(f"Error fetching data: {e}")
        return None

# Persistencia de datos en la sesión para evitar pérdida al recargar
if 'fin_data' not in st.session_state:
    st.session_state.fin_data = {"price": 168.4, "shares": 12700.0, "cash": 96000.0, "ebit": 154740.0, "debt": 22000.0, "curr": "USD"}

with st.sidebar:
    st.header("1. Data Retrieval")
    t_input = st.text_input("Ticker Symbol", value="GOOGL").upper()
    # Este es ahora el único campo de moneda
    c_input = st.text_input("Target Currency", value=st.session_state.fin_data['curr']).upper()
    
    if st.button("Fetch & Auto-fill"):
        fetched = fetch_financial_data(t_input, c_input)
        if fetched:
            st.session_state.fin_data = {
                "price": fetched['price'], "shares": fetched['shares'], 
                "cash": fetched['cash'], "ebit": fetched['ebit'], 
                "debt": fetched['debt'], "curr": c_input
            }
            st.success(f"Loaded data for {t_input} in {c_input}")

# Formulario de entrada de parámetros
with st.sidebar.form("input_form"):
    st.header("2. Simulation Parameters")
    
    # Sección Company Info (Moneda eliminada como input manual)
    company_name = st.text_input("Company Name", value=t_input)
    # La moneda se pasa internamente desde c_input
    
    st.subheader("Financials")
    col1, col2 = st.columns(2)
    with col1:
        current_price = st.number_input("Current Price", value=st.session_state.fin_data['price'])
        shares_outstanding = st.number_input("Shares Outstanding (M)", value=st.session_state.fin_data['shares'])
    with col2:
        cash = st.number_input("Cash (M)", value=st.session_state.fin_data['cash'])
        debt = st.number_input("Debt (M)", value=st.session_state.fin_data['debt'])
    
    operating_income_base = st.number_input("Operating Income Base (M)", value=st.session_state.fin_data['ebit'])

    # --- Los campos de Growth, Risk y Reinvestment permanecen iguales a tu original ---
    st.subheader("Growth & Risk")
    growth_rate_5y = st.number_input("Growth Rate 5y (%)", value=15.0) / 100
    wacc = st.number_input("WACC (%)", value=9.6) / 100
    # ... (Añadir aquí el resto de tus inputs de std dev, etc. siguiendo tu formato original)
    
    # Asegúrate de incluir n_simulations
    n_simulations = st.number_input("Simulations", value=10000)

    submitted = st.form_submit_button("Run Monte Carlo Simulation")

# Ejecución y Visualización
if submitted:
    # Preparar parámetros para el archivo DCF_main
    params = {
        'company_name': company_name,
        'currency': c_input, # Tomado directamente del campo de búsqueda
        'current_price': current_price,
        'operating_income_base': operating_income_base,
        'shares_outstanding': shares_outstanding,
        'cash': cash,
        'debt': debt,
        'growth_rate_5y': growth_rate_5y,
        'growth_rate_5_10y': 0.08, # Ajustar según tus inputs
        'risk_free_rate': 0.045, 
        'equity_risk_premium': 0.0513,
        'WACC': wacc,
        'reinvestment_rate_5y': 0.5,
        'reinvestment_rate_5_10y': 0.5,
        'std_growth_5y': 0.02,
        'std_growth_5_10y': 0.03,
        'std_risk_free': 0.005,
        'std_equity_premium': 0.005,
        'std_WACC': 0.005,
        'std_reinv_5y': 0.025,
        'std_reinv_5_10y': 0.05,
        'n_simulations': int(n_simulations)
    }

    try:
        with st.spinner("Calculating..."):
            # Aquí es donde se definen las variables. Si la función falla, saltará al except.
            fig_es, fig_dist, fig_sens, summary = run_monte_carlo_simulation(params)
            
            tab1, tab2 = st.tabs(["Results", "Summary"])
            
            with tab1:
                st.pyplot(fig_es)
                
            with tab2:
                # ESTRUCTURA EXACTA DE TU PESTAÑA SUMMARY ORIGINAL
                col_plot, col_txt = st.columns([2, 1])
                with col_plot:
                    st.pyplot(fig_dist)
                
                with col_txt:
                    st.markdown("""<style>.summary-text { font-size: 0.9em; }</style>""", unsafe_allow_html=True)
                    st.markdown("<h3 style='text-align: center;'>Valuation Summary</h3>", unsafe_allow_html=True)
                    st.markdown(f"**Company:** {summary['company_name']}  \n**Date:** {summary['date']}  \n**---**")
                    
                    s_col1, s_col2 = st.columns(2)
                    with s_col1:
                        st.markdown(f"""<div class="summary-text">
                            <p><strong>Current Price:</strong> {summary['current_price']}<br>
                            <strong>Mean Value:</strong> {summary['mean_value']}<br>
                            <strong>Upside:</strong> {summary['upside_potential']}</p>
                            <p><strong>Risk:</strong><br>VaR 95%: {summary['VaR 95%']}<br>
                            Std Dev: {summary['Std. Deviation']}</p>
                        </div>""", unsafe_allow_html=True)
                    with s_col2:
                        st.markdown(f"""<div class="summary-text">
                            <p><strong>Parameters:</strong><br>
                            WACC: {summary['Variable Parameters']['WACC']}<br>
                            Growth: {summary['Variable Parameters']['Growth 5y']}</p>
                        </div>""", unsafe_allow_html=True)
            
            # Limpieza de memoria
            plt.close('all')
            
    except Exception as e:
        st.error(f"Error during simulation: {e}")
