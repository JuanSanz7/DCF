import streamlit as st
import matplotlib.pyplot as plt
from DCF_main import run_monte_carlo_simulation

st.set_page_config(page_title="DCF Monte Carlo Valuation Tool", layout="wide")
st.title("DCF Monte Carlo Valuation Tool")

with st.form("input_form"):
    st.header("Company Information")
    company_name = st.text_input("Company Name", value="JD.com")
    currency = st.text_input("Currency", value="USD")

    st.header("Financial Information")
    current_price = st.number_input("Current Price", value=33.55)
    operating_income_base = st.number_input("Operating Income Base (millions)", value=6610.0)
    shares_outstanding = st.number_input("Shares Outstanding (millions)", value=1524.0)
    cash = st.number_input("Cash (millions)", value=27000.0)
    debt = st.number_input("Debt (millions)", value=12000.0)

    st.header("Growth Parameters")
    growth_rate_5y = st.number_input("Growth Rate 5y (%)", value=9.0)
    growth_rate_5_10y = st.number_input("Growth Rate 5-10y (%)", value=7.0)

    st.header("Risk Parameters")
    risk_free_rate = st.number_input("Risk Free Rate (%)", value=4.44)
    equity_risk_premium = st.number_input("Equity Risk Premium (%)", value=5.3)
    WACC = st.number_input("WACC (%)", value=9.0)

    st.header("Reinvestment Rates")
    reinvestment_rate_5y = st.number_input("Reinvestment Rate 5y (%)", value=35.0)
    reinvestment_rate_5_10y = st.number_input("Reinvestment Rate 5-10y (%)", value=40.0)

    st.header("Standard Deviations")
    std_growth_5y = st.number_input("Std Growth 5y (%)", value=2.0)
    std_growth_5_10y = st.number_input("Std Growth 5-10y (%)", value=3.0)
    std_risk_free = st.number_input("Std Risk Free (%)", value=0.5)
    std_equity_premium = st.number_input("Std Equity Premium (%)", value=0.5)
    std_WACC = st.number_input("Std WACC (%)", value=0.5)
    std_reinv_5y = st.number_input("Std Reinv 5y (%)", value=2.5)
    std_reinv_5_10y = st.number_input("Std Reinv 5-10y (%)", value=5.0)

    st.header("Simulation Parameters")
    n_simulations = st.number_input("Number of Simulations", value=10000, step=1000)

    submitted = st.form_submit_button("Run Monte Carlo Simulation")

if submitted:
    params = {
        'company_name': company_name,
        'currency': currency,
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
        fig_es, _ = run_monte_carlo_simulation(params)
        st.success(f"Monte Carlo simulation for {company_name} completed successfully!")
        st.pyplot(fig_es) 