import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import spearmanr
from datetime import datetime
from matplotlib.gridspec import GridSpec # Import GridSpec

def run_monte_carlo_simulation(params):
    # Unpack parameters
    company_name = params['company_name']
    currency = params.get('currency', 'USD')
    current_price = params['current_price']
    nopat_base = params['nopat_base'] # CAMBIO: Antes operating_income_base
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
    
    n_simulations = params.get('n_simulations', 10000)
    current_date = datetime.now().strftime("%Y-%m-%d")

    intrinsic_values = []
    param_samples = [] # To store samples for sensitivity analysis

    for _ in range(n_simulations):
        # Sample parameters from normal distributions
        g1 = np.random.normal(growth_rate_5y, std_growth_5y)
        g2 = np.random.normal(growth_rate_5_10y, std_growth_5_10y)
        rf = np.random.normal(risk_free_rate, std_risk_free)
        erp = np.random.normal(equity_risk_premium, std_equity_premium)
        w = np.random.normal(WACC, std_WACC)
        ri1 = np.random.normal(reinvestment_rate_5y, std_reinv_5y)
        ri2 = np.random.normal(reinvestment_rate_5_10y, std_reinv_5_10y)

        # Terminal growth and WACC assumptions
        g_terminal = rf
        w_terminal = rf + erp
        ri_terminal = g_terminal / w_terminal if w_terminal > g_terminal else 0.8

        pv_fcf = 0
        current_nopat = nopat_base # CAMBIO: Iniciamos con NOPAT

        # Stage 1: Years 1-5
        for i in range(5):
            current_nopat *= (1 + g1)
            # CAMBIO: Eliminada la resta de impuestos interna fcf = nopat * (1 - tax)
            fcf = current_nopat * (1 - ri1)
            pv_fcf += fcf / ((1 + w) ** (i + 1))

        # Stage 2: Years 6-10
        for i in range(5, 10):
            current_nopat *= (1 + g2)
            fcf = current_nopat * (1 - ri2)
            pv_fcf += fcf / ((1 + w) ** (i + 1))

        # Terminal Value
        terminal_nopat = current_nopat * (1 + g_terminal)
        terminal_fcf = terminal_nopat * (1 - ri_terminal)
        tv = terminal_fcf / (w_terminal - g_terminal)
        pv_tv = tv / ((1 + w) ** 10)

        # Equity Value
        equity_value = pv_fcf + pv_tv + cash - debt
        value_per_share = equity_value / shares_outstanding
        intrinsic_values.append(value_per_share)
        
        # Store samples for sensitivity
        param_samples.append([g1, g2, w, ri1, ri2, rf, erp])

    intrinsic_values = np.array(intrinsic_values)
    param_samples = np.array(param_samples)

    # Statistics
    mean_value = np.mean(intrinsic_values)
    median_value = np.median(intrinsic_values)
    std_value = np.std(intrinsic_values)
    upside_potential = (mean_value / current_price - 1) * 100
    prob_undervalued = np.mean(intrinsic_values > current_price) * 100
    prob_overvalued = 100 - prob_undervalued
    
    # Risk Metrics
    var_95 = np.percentile(intrinsic_values, 5)
    cvar_95 = intrinsic_values[intrinsic_values <= var_95].mean()

    # --- TODO EL CÓDIGO DE VISUALIZACIÓN ORIGINAL SIGUE IGUAL ---
    fig_es = plt.figure(figsize=(15, 12))
    gs = GridSpec(3, 2, figure=fig_es)
    
    ax1 = fig_es.add_subplot(gs[0, :])
    ax1.hist(intrinsic_values, bins=100, color='skyblue', edgecolor='black', alpha=0.7)
    ax1.axvline(current_price, color='red', linestyle='--', linewidth=2, label=f'Current Price: {current_price}')
    ax1.axvline(mean_value, color='green', linestyle='-', linewidth=2, label=f'Mean: {mean_value:.2f}')
    ax1.set_title(f"Monte Carlo Simulation: {company_name}", fontsize=14, fontweight='bold')
    ax1.set_xlabel("Intrinsic Value per Share")
    ax1.set_ylabel("Frequency")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2 = fig_es.add_subplot(gs[1, 0])
    param_names = ['Growth 1-5y', 'Growth 6-10y', 'WACC', 'Reinv 1-5y', 'Reinv 6-10y', 'RF Rate', 'ERP']
    correlations = [spearmanr(intrinsic_values, param_samples[:, i])[0] for i in range(len(param_names))]
    ax2.barh(param_names, correlations, color='salmon')
    ax2.set_title("Sensitivity Analysis (Spearman Correlation)")
    ax2.set_xlabel("Correlation with Intrinsic Value")
    ax2.set_xlim(-1, 1)
    ax2.grid(True, alpha=0.3)

    ax3 = fig_es.add_subplot(gs[1, 1])
    sorted_vals = np.sort(intrinsic_values)
    y_vals = np.linspace(0, 1, len(sorted_vals))
    ax3.plot(sorted_vals, y_vals, color='blue', linewidth=2)
    ax3.axhline(0.5, color='gray', linestyle='--')
    ax3.axvline(median_value, color='green', linestyle=':', label=f'Median: {median_value:.2f}')
    ax3.set_title("Cumulative Distribution Function (CDF)")
    ax3.set_xlabel("Intrinsic Value")
    ax3.set_ylabel("Probability")
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    ax4 = fig_es.add_subplot(gs[2, :])
    ax4.axis('off')
    summary_text = (
        f"Valuation Summary for {company_name} ({current_date})\n"
        f"Mean Intrinsic Value: {mean_value:.2f} {currency} | Median: {median_value:.2f} {currency}\n"
        f"Current Price: {current_price:.2f} {currency} | Upside/Downside: {upside_potential:.1f}%\n"
        f"Probability Undervalued: {prob_undervalued:.1f}% | Overvalued: {prob_overvalued:.1f}%\n"
        f"95% Value at Risk (VaR): {var_95:.2f} {currency} | 95% CVaR: {cvar_95:.2f} {currency}"
    )
    ax4.text(0.5, 0.5, summary_text, ha='center', va='center', fontsize=12, fontweight='bold',
             bbox=dict(boxstyle="round,pad=1", fc="lightgray", alpha=0.3))

    # Definimos las figuras adicionales para compatibilidad
    fig_distribution_only = plt.figure()
    plt.hist(intrinsic_values, bins=50)
    plt.close(fig_distribution_only)
    fig_sensitivity = plt.figure()
    plt.barh(param_names, correlations)
    plt.close(fig_sensitivity)

    valuation_summary = {
        'company_name': company_name,
        'date': current_date,
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
            'Growth 5y': f"{growth_rate_5y*100:.1f}% (±{std_growth_5y*100:.1f}%)",
            'Growth 5-10y': f"{growth_rate_5_10y*100:.1f}% (±{std_growth_5_10y*100:.1f}%)",
            'WACC': f"{WACC*100:.1f}% (±{std_WACC*100:.1f}%)",
            'Risk Premium': f"{equity_risk_premium*100:.1f}% (±{std_equity_premium*100:.1f}%)",
            'Risk Free Rate': f"{risk_free_rate*100:.1f}% (±{std_risk_free*100:.1f}%)",
            'Reinvestment 5y': f"{reinvestment_rate_5y*100:.1f}% (±{std_reinv_5y*100:.1f}%)",
            'Reinvestment 5-10y': f"{reinvestment_rate_5_10y*100:.1f}% (±{std_reinv_5_10y*100:.1f}%)"
        },
        'Terminal Value Params': {
            'Term. Growth': f"{risk_free_rate*100:.1f}%",
            'Term. WACC': f"{(risk_free_rate+equity_risk_premium)*100:.1f}%",
            'Term. Reinv Rate': f"{(risk_free_rate/(risk_free_rate+equity_risk_premium))*100:.1f}%"
        }
    }

    return fig_es, fig_distribution_only, fig_sensitivity, valuation_summary
