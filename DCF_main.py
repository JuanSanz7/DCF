import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import spearmanr
from datetime import datetime
from matplotlib.gridspec import GridSpec

def run_monte_carlo_simulation(params):
    # --- UNPACK PARAMETERS (TODOS LOS ORIGINALES) ---
    company_name = params['company_name']
    currency = params.get('currency', 'USD') # Captura la moneda del input
    current_price = params['current_price']
    operating_income_base = params['operating_income_base']
    shares_outstanding = params['shares_outstanding']
    cash = params['cash']
    debt = params['debt']
    growth_rate_5y = params['growth_rate_5y']
    growth_rate_5_10y = params['growth_rate_5_10y']
    risk_free_rate = params['risk_free_rate']
    equity_risk_premium = params['equity_risk_premium']
    WACC = params['WACC']
    reinvestment_rate_5y = params['reinvestment_rate_5y']
    reinvestment_rate_5_10y = params['reinvestment_rate_5_10y']
    std_growth_5y = params['std_growth_5y']
    std_growth_5_10y = params['std_growth_5_10y']
    std_risk_free = params['std_risk_free']
    std_equity_premium = params['std_equity_premium']
    std_WACC = params['std_WACC']
    std_reinv_5y = params['std_reinv_5y']
    std_reinv_5_10y = params['std_reinv_5_10y']
    n_simulations = params['n_simulations']
    current_date = datetime.now().strftime("%Y-%m-%d")

    # --- SIMULATION LOGIC (INTEGRA SIN CAMBIOS) ---
    np.random.seed(42)
    params_simulated = {
        'growth_5y': [], 'growth_5_10y': [], 'risk_free': [],
        'equity_premium': [], 'WACC': [], 'reinv_5y': [],
        'reinv_5_10y': [], 'value_per_share': []
    }
    results = []
    fcf_projections = []

    for _ in range(n_simulations):
        growth_rate_5y_sim = np.random.normal(growth_rate_5y, std_growth_5y)
        growth_rate_5_10_sim = np.random.normal(growth_rate_5_10y, std_growth_5_10y)
        risk_free_rate_sim = np.random.normal(risk_free_rate, std_risk_free)
        equity_risk_premium_sim = np.random.normal(equity_risk_premium, std_equity_premium)
        WACC_sim = np.random.normal(WACC, std_WACC)
        reinv_rate_5y_sim = np.random.normal(reinvestment_rate_5y, std_reinv_5y)
        reinv_rate_5_10y_sim = np.random.normal(reinvestment_rate_5_10y, std_reinv_5_10y)
        
        params_simulated['growth_5y'].append(growth_rate_5y_sim)
        params_simulated['growth_5_10y'].append(growth_rate_5_10_sim)
        params_simulated['risk_free'].append(risk_free_rate_sim)
        params_simulated['equity_premium'].append(equity_risk_premium_sim)
        params_simulated['WACC'].append(WACC_sim)
        params_simulated['reinv_5y'].append(reinv_rate_5y_sim)
        params_simulated['reinv_5_10y'].append(reinv_rate_5_10y_sim)

        terminal_WACC = risk_free_rate_sim + equity_risk_premium_sim
        terminal_growth = risk_free_rate_sim
        reinvestment_rate_terminal = risk_free_rate_sim / (risk_free_rate_sim + equity_risk_premium_sim)

        operating_income = operating_income_base
        FCFs = []
        for year in range(1, 6):
            operating_income *= (1 + growth_rate_5y_sim)
            FCFs.append(operating_income * (1 - reinv_rate_5y_sim))
        for year in range(6, 11):
            operating_income *= (1 + growth_rate_5_10_sim)
            FCFs.append(operating_income * (1 - reinv_rate_5_10y_sim))

        PV_FCF = sum([f / ((1 + WACC_sim) ** i) for i, f in enumerate(FCFs, 1)])
        terminal_value = (FCFs[-1] * (1 + terminal_growth)) / (terminal_WACC - terminal_growth)
        PV_terminal = terminal_value / ((1 + WACC_sim) ** 10)
        
        value_per_share = (PV_FCF + PV_terminal + cash - debt) / shares_outstanding
        results.append(value_per_share)
        params_simulated['value_per_share'].append(value_per_share)
        fcf_projections.append(FCFs)

    results = np.array(results)
    mean_value = np.mean(results)
    std_value = np.std(results)
    var_95 = np.percentile(results, 5)
    cvar_95 = np.mean(results[results < var_95])
    prob_overvalued = np.mean(results < current_price) * 100
    prob_undervalued = np.mean(results > current_price) * 100
    upside_potential = ((mean_value - current_price) / current_price) * 100

    # --- SENSITIVITY CALCULATION ---
    df_params = pd.DataFrame(params_simulated)
    sensitivities = {}
    for param in df_params.columns[:-1]:
        std_norm = (df_params[param] - df_params[param].mean()) / df_params[param].std()
        coef = np.polyfit(std_norm, df_params['value_per_share'], 1)[0]
        sensitivities[param] = {'impact': coef}

    # --- PLOTS (USANDO EL CAMPO CURRENCY) ---
    plt.style.use('seaborn-v0_8-darkgrid')
    fig_es, axs = plt.subplots(2, 2, figsize=(15, 10))
    
    # Intrinsic Value Dist
    axs[0, 0].hist(results, bins=50, density=True, alpha=0.7, color='skyblue', edgecolor='black')
    axs[0, 0].set_title(f'{company_name} - Intrinsic Value Distribution')
    axs[0, 0].set_xlabel(f'Value per Share ({currency})')
    axs[0, 0].axvline(current_price, color='purple', label='Current Price')
    axs[0, 0].legend()

    # FCF Projection
    fcf_mean = np.mean(fcf_projections, axis=0)
    axs[1, 0].plot(range(1, 11), fcf_mean, marker='o')
    axs[1, 0].set_title(f'Average FCF Projection ({currency})')

    # Sensitivity
    sensitivity_data = pd.DataFrame.from_dict(sensitivities, orient='index').sort_values('impact')
    axs[1, 1].barh(sensitivity_data.index, sensitivity_data['impact'])
    axs[1, 1].set_title('Sensitivity Analysis')

    # Valuation Summary Table (Rendered in Matplotlib)
    axs[0, 1].axis('off')
    summary_txt = f"VALUATION: {company_name}\nPrice: {current_price:.2f} {currency}\nMean: {mean_value:.2f} {currency}\nUpside: {upside_potential:.1f}%"
    axs[0, 1].text(0.5, 0.5, summary_txt, ha='center', va='center', bbox=dict(facecolor='white', alpha=0.5))

    plt.tight_layout()

    # Figures para las pestañas individuales
    fig_distribution_only, _ = plt.subplots(figsize=(10, 6))
    plt.hist(results, bins=50, color='skyblue', edgecolor='black')
    plt.title(f"Intrinsic Value ({currency})")

    fig_sensitivity, _ = plt.subplots(figsize=(10, 6))
    plt.barh(sensitivity_data.index, sensitivity_data['impact'])
    plt.title("Sensitivity Analysis")

    # --- DICTIONARY OUTPUT ---
    valuation_summary = {
        'company_name': company_name,
        'date': current_date,
        'current_price': f"{current_price:.2f} {currency}",
        'mean_value': f"{mean_value:.2f} {currency}",
        'median_value': f"{np.median(results):.2f} {currency}",
        'upside_potential': f"{upside_potential:.1f}%",
        'prob_overvalued': f"{prob_overvalued:.1f}%",
        'prob_undervalued': f"{prob_undervalued:.1f}%",
        'VaR 95%': f"{var_95:.2f} {currency}",
        'CVaR 95%': f"{cvar_95:.2f} {currency}",
        'Std. Deviation': f"{std_value:.2f} {currency}",
        'Variable Parameters': {
            'Growth 5y': f"{growth_rate_5y*100:.1f}%",
            'WACC': f"{WACC*100:.1f}%",
            # ... otros parámetros ...
        },
        'Terminal Value Params': {'Term. Growth': 'RFR'}
    }

    return fig_es, fig_distribution_only, fig_sensitivity, valuation_summary
