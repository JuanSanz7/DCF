import streamlit as st
import matplotlib.pyplot as plt
import io
from DCF_main import run_monte_carlo_simulation

st.set_page_config(page_title="DCF Monte Carlo Valuation Tool", layout="wide")
st.title("DCF Monte Carlo Valuation Tool")

with st.sidebar.form("input_form"):
    st.header("Company Information")
    col1, col2 = st.columns(2)
    with col1:
        company_name = st.text_input("Company Name", value="JD.com")
    with col2:
        currency = st.text_input("Currency", value="USD")

    st.header("Financial Information")
    col1, col2 = st.columns(2)
    with col1:
        current_price = st.number_input("Current Price", value=33.55)
        shares_outstanding = st.number_input("Shares Outstanding (millions)", value=1524.0)
        cash = st.number_input("Cash (millions)", value=27000.0)
    with col2:
        operating_income_base = st.number_input("Operating Income Base (millions)", value=6610.0)
        debt = st.number_input("Debt (millions)", value=12000.0)

    st.header("Growth Parameters")
    col1, col2 = st.columns(2)
    with col1:
        growth_rate_5y = st.number_input("Growth Rate 5y (%)", value=9.0)
    with col2:
        growth_rate_5_10y = st.number_input("Growth Rate 5-10y (%)", value=7.0)

    st.header("Risk Parameters")
    col1, col2 = st.columns(2)
    with col1:
        risk_free_rate = st.number_input("Risk Free Rate (%)", value=4.44)
        equity_risk_premium = st.number_input("Equity Risk Premium (%)", value=5.3)
    with col2:
        WACC = st.number_input("WACC (%)", value=9.0)

    st.header("Reinvestment Rates")
    col1, col2 = st.columns(2)
    with col1:
        reinvestment_rate_5y = st.number_input("Reinvestment Rate 5y (%)", value=35.0)
    with col2:
        reinvestment_rate_5_10y = st.number_input("Reinvestment Rate 5-10y (%)", value=40.0)

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
    col1, col2 = st.columns(2)
    with col1:
        n_simulations = st.number_input("Number of Simulations", value=10000, step=1000)
    with col2:
        pass

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
        fig_es, fig_distribution_only, fig_sensitivity, valuation_summary = run_monte_carlo_simulation(params)
        st.success(f"Monte Carlo simulation for {company_name} completed successfully!")

        tab1, tab2 = st.tabs(["Results", "Summary"])
        
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

            with col2_summary:
                st.header("Valuation Summary")
                st.write(f"**Company:** {valuation_summary['company_name']}")
                st.write(f"**Date:** {valuation_summary['date']}")
                st.write("**-------------------**")
                st.write(f"**Current Price:** {valuation_summary['current_price']}")
                st.write(f"**Mean Value:** {valuation_summary['mean_value']}")
                st.write(f"**Median Value:** {valuation_summary['median_value']}")
                st.write(f"**Upside Potential:** {valuation_summary['upside_potential']}")

                st.subheader("Probabilities")
                st.write(f"**Overvaluation:** {valuation_summary['prob_overvalued']}")
                st.write(f"**Undervaluation:** {valuation_summary['prob_undervalued']}")

                st.subheader("Risk Metrics")
                st.write(f"**VaR 95%:** {valuation_summary['VaR 95%']}")
                st.write(f"**CVaR 95%:** {valuation_summary['CVaR 95%']}")
                st.write(f"**Std. Deviation:** {valuation_summary['Std. Deviation']}")

                st.subheader("Variable Parameters")
                for param, value in valuation_summary['Variable Parameters'].items():
                    st.write(f"**{param}:** {value}")

                st.subheader("Terminal Value Parameters")
                for param, value in valuation_summary['Terminal Value Params'].items():
                    st.write(f"**{param}:** {value}")

        # Close the plot figures to free up memory
        plt.close(fig_es)
        plt.close(fig_distribution_only)
        plt.close(fig_sensitivity) 