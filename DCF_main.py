import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import spearmanr
from datetime import datetime
from matplotlib.gridspec import GridSpec

def run_monte_carlo_simulation(params):
    # Unpack parameters
    company_name = params['company_name']
    currency = params.get('currency', 'USD')
    current_price = params['current_price']
    operating_income_base = params['operating_income_base']
    tax_rate = params.get('tax_rate', 0.21) # Mínimo cambio para Tax Rate
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

    np.random.seed(42)
    results = []
    
    # Simulación de parámetros
    growth_5y_sims = np.random.normal(growth_rate_5y, std_growth_5y, n_simulations)
    growth_5_10y_sims = np.random.normal(growth_rate_5_10y, std_growth_5_10y, n_simulations)
    wacc_sims = np.random.normal(WACC, std_WACC, n_simulations)
    rfr_sims = np.random.normal(risk_free_rate, std_risk_free, n_simulations)
    erp_sims = np.random.normal(equity_risk_premium, std_equity_premium, n_simulations)
    reinv_5y_sims = np.random.normal(reinvestment_rate_5y, std_reinv_5y, n_simulations)
    reinv_5_10y_sims = np.random.normal(reinvestment_rate_5_10y, std_reinv_5_10y, n_simulations)

    for i in range(n_simulations):
        g1, g2 = growth_5y_sims[i], growth_5_10y_sims[i]
        w, rfr, erp = wacc_sims[i], rfr_sims[i], erp_sims[i]
        re1, re2 = reinv_5y_sims[i], reinv_5_10y_sims[i]

        t_wacc = rfr + erp
        t_g = rfr
        re_terminal = t_g / t_wacc

        # --- CÁLCULO NOPAT ---
        ebit = operating_income_base
        pv_fcf = 0
        for year in range(1, 6):
            ebit *= (1 + g1)
            nopat = ebit * (1 - tax_rate) # NOPAT calculation
            fcf = nopat * (1 - re1)
            pv_fcf += fcf / ((1 + w) ** year)
        for year in range(6, 11):
            ebit *= (1 + g2)
            nopat = ebit * (1 - tax_rate)
            fcf = nopat * (1 - re2)
            pv_fcf += fcf / ((1 + w) ** year)
            
        nopat_t = (ebit * (1 + t_g)) * (1 - tax_rate)
        tv = (nopat_t * (1 - re_terminal)) / (t_wacc - t_g)
        pv_tv = tv / ((1 + w) ** 10)
        
        results.append((pv_fcf + pv_tv + cash - debt) / shares_outstanding)

    results = np.array(results)
    mean_value = np.mean(results)
    median_value = np.median(results)
    std_value = np.std(results)
    var_95 = np.percentile(results, 5)
    cvar_95 = np.mean(results[results <= var_95])
    prob_overvalued = np.mean(results < current_price) * 100
    prob_undervalued = 100 - prob_overvalued
    upside_potential = ((mean_value - current_price) / current_price) * 100

    # Gráficos (Originales)
    fig_es, ax = plt.subplots(figsize=(10, 6))
    ax.hist(results, bins=50, color='skyblue', edgecolor='black', alpha=0.7)
    ax.axvline(current_price, color='red', linestyle='--', label=f'Price: {current_price} {currency}')
    ax.set_title(f"Simulation: {company_name}")
    ax.set_xlabel(f"Value ({currency})")
    ax.legend()

    fig_distribution_only, ax2 = plt.subplots(figsize=(10, 6))
    ax2.hist(results, bins=50, color='skyblue', edgecolor='black')

    # Diccionario completo para la UI
    valuation_summary = {
        'company_name': company_name, 'date': current_date,
        'current_price': f"{current_price:.2f} {currency}",
        'mean_value': f"{mean_value:.2f} {currency}",
        'median_value': f"{median_value:.2f} {currency}",
        'upside_potential': f"{upside_potential:.1f}%",
        'prob_overvalued': f"{prob_overvalued:.1f}%",
        'prob_undervalued': f"{prob_undervalued:.1f}%",
        'VaR 95%': f"{var_95:.2f} {currency}",
        'CVaR 95%': f"{cvar_95:.2f} {currency}",
        'Std. Deviation': f"{std_value:.2f} {currency}",
        'Variable Parameters': {
            'Growth 5y': f"{growth_rate_5y*100:.1f}%", 'Growth 5-10y': f"{growth_rate_5_10y*100:.1f}%",
            'WACC': f"{WACC*100:.1f}%", 'Risk Premium': f"{equity_risk_premium*100:.1f}%",
            'Risk Free Rate': f"{risk_free_rate*100:.1f}%", 'Reinvestment 5y': f"{reinvestment_rate_5y*100:.1f}%",
            'Reinvestment 5-10y': f"{reinvestment_rate_5_10y*100:.1f}%"
        },
        'Terminal Value Params': {'Term. Growth': 'RFR', 'Term. WACC': 'RFR+ERP', 'Term. Reinv Rate': 'TG/TWACC'}
    }
    return fig_es, fig_distribution_only, fig_es, valuation_summary
