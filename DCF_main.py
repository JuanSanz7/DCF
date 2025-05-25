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

    np.random.seed(42)
    params_simulated = {
        'growth_5y': [],
        'growth_5_10y': [],
        'risk_free': [],
        'equity_premium': [],
        'WACC': [],
        'reinv_5y': [],
        'reinv_5_10y': [],
        'value_per_share': []
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
        operating_incomes = []
        for year in range(1, 6):
            operating_income *= (1 + growth_rate_5y_sim)
            operating_incomes.append(operating_income)
            FCF = operating_income * (1 - reinv_rate_5y_sim)
            FCFs.append(FCF)
        for year in range(6, 11):
            operating_income *= (1 + growth_rate_5_10_sim)
            operating_incomes.append(operating_income)
            FCF = operating_income * (1 - reinv_rate_5_10y_sim)
            FCFs.append(FCF)
        operating_income_terminal = operating_income * (1 + terminal_growth)
        FCF_terminal = operating_income_terminal * (1 - reinvestment_rate_terminal)
        terminal_value = FCF_terminal / (terminal_WACC - terminal_growth)
        fcf_projections.append(FCFs)
        discount_factors = [(1 + WACC_sim) ** i for i in range(1, 11)]
        PV_FCF = sum([f / d for f, d in zip(FCFs, discount_factors)])
        PV_terminal = terminal_value / ((1 + WACC_sim) ** 10)
        EV = PV_FCF + PV_terminal
        market_value = EV + cash - debt
        value_per_share = market_value / shares_outstanding
        results.append(value_per_share)
        params_simulated['value_per_share'].append(value_per_share)
    results = np.array(results)
    mean_value = np.mean(results)
    median_value = np.median(results)
    std_value = np.std(results)
    ci_lower = np.percentile(results, 2.5)
    ci_upper = np.percentile(results, 97.5)
    var_95 = np.percentile(results, 5)
    cvar_95 = np.mean(results[results < var_95])
    prob_overvalued = np.mean(results < current_price) * 100
    prob_undervalued = np.mean(results > current_price) * 100
    upside_potential = ((mean_value - current_price) / current_price) * 100
    df_params = pd.DataFrame(params_simulated)
    sensitivities = {}
    for param in df_params.columns[:-1]:
        correlation = spearmanr(df_params[param], df_params['value_per_share'])[0]
        std_norm = (df_params[param] - df_params[param].mean()) / df_params[param].std()
        coef = np.polyfit(std_norm, df_params['value_per_share'], 1)[0]
        sensitivities[param] = {'correlation': correlation, 'impact': coef}

    # Create the original combined 2x2 figure (fig_es)
    fig_es, axs = plt.subplots(2, 2, figsize=(15, 10))
    plt.style.use('seaborn-v0_8-darkgrid')

    # Plot 1: Intrinsic Value Distribution
    ax = axs[0, 0]
    ax.hist(results, bins=50, density=True, alpha=0.7, color='skyblue', edgecolor='black')
    ax.axvspan(mean_value - 3*std_value, mean_value - 2*std_value, color='red', alpha=0.1, label='±3σ')
    ax.axvspan(mean_value + 2*std_value, mean_value + 3*std_value, color='red', alpha=0.1)
    ax.axvspan(mean_value - 2*std_value, mean_value - std_value, color='orange', alpha=0.1, label='±2σ')
    ax.axvspan(mean_value + std_value, mean_value + 2*std_value, color='orange', alpha=0.1)
    ax.axvspan(mean_value - std_value, mean_value + std_value, color='green', alpha=0.1, label='±1σ')
    ax.axvline(mean_value, color='red', linestyle='--', label='Mean')
    ax.axvline(current_price, color='purple', linestyle='-', label='Current Price')
    ax.set_title(f'{company_name} - Intrinsic Value Distribution')
    ax.set_xlabel(f'Intrinsic Value per Share ({currency})')
    ax.set_ylabel('Density')
    ax.legend()

    # Plot 2: FCF Projection
    ax = axs[1, 0]
    fcf_mean = np.mean(fcf_projections, axis=0)
    fcf_std = np.std(fcf_projections, axis=0)
    years = range(1, 11)
    ax.fill_between(years, 
                    fcf_mean - 3*fcf_std,
                    fcf_mean + 3*fcf_std,
                    color='red',
                    alpha=0.1,
                    label='±3σ')
    ax.fill_between(years, 
                    fcf_mean - 2*fcf_std,
                    fcf_mean + 2*fcf_std,
                    color='orange',
                    alpha=0.1,
                    label='±2σ')
    ax.fill_between(years, 
                    fcf_mean - fcf_std,
                    fcf_mean + fcf_std,
                    color='green',
                    alpha=0.1,
                    label='±1σ')
    ax.plot(years, fcf_mean, marker='o', color='blue', label='Average FCF')
    ax.set_title(f'{company_name} - Free Cash Flow Projection')
    ax.set_xlabel('Year')
    ax.set_ylabel(f'FCF (Millions {currency})')
    ax.legend()
    ax.grid(True)

    # Plot 3: Sensitivity Analysis (Tornado plot) within fig_es
    ax = axs[1, 1]
    sensitivity_data = pd.DataFrame.from_dict(sensitivities, orient='index')
    sensitivity_data = sensitivity_data.sort_values('impact', ascending=True)
    ax.barh(range(len(sensitivity_data)), sensitivity_data['impact'], align='center')
    ax.set_yticks(range(len(sensitivity_data)))
    ax.set_yticklabels(sensitivity_data.index)
    ax.set_title(f'{company_name} - Sensitivity Analysis')
    ax.set_xlabel(f'Impact on Value per Share ({currency}/σ)')

    # Matplotlib-rendered Valuation Summary within fig_es
    axs[0, 1].axis('off')
    title = (
        f"VALUATION SUMMARY - {company_name}\n"
        f"Date: {current_date}\n"
        f"-------------------"
    )
    left_column = (
        f"Current Price: {current_price:.2f} {currency}\n"
        f"Mean Value: {mean_value:.2f} {currency}\n"
        f"Median Value: {median_value:.2f} {currency}\n"
        f"Upside Potential: {upside_potential:.1f}%\n\n"
        f"Probabilities:\n"
        f"Overvaluation: {prob_overvalued:.1f}%\n"
        f"Undervaluation: {prob_undervalued:.1f}%\n\n"
        f"Risk Metrics:\n"
        f"VaR 95%: {var_95:.2f} {currency}\n"
        f"CVaR 95%: {cvar_95:.2f} {currency}\n"
        f"Std. Deviation: {std_value:.2f} {currency}"
    )
    right_column = (
        f"Variable Parameters:\n"
        f"Growth 5y: {growth_rate_5y*100:.1f}% (±{std_growth_5y*100:.1f}%)\n"
        f"Growth 5-10y: {growth_rate_5_10y*100:.1f}% (±{std_growth_5_10y*100:.1f}%)\n"
        f"WACC: {WACC*100:.1f}% (±{std_WACC*100:.1f}%)\n"
        f"Risk Premium: {equity_risk_premium*100:.1f}% (±{std_equity_premium*100:.1f}%)\n"
        f"Risk Free Rate: {risk_free_rate*100:.1f}% (±{std_risk_free*100:.1f}%)\n"
        f"Reinvestment 5y: {reinvestment_rate_5y*100:.1f}% (±{std_reinv_5y*100:.1f}%)\n"
        f"Reinvestment 5-10y: {reinvestment_rate_5_10y*100:.1f}% (±{std_reinv_5_10y*100:.1f}%)\n"
        f"\nTerminal Value Params:\n"
        f"Term. Growth = RFR\n"
        f"Term. WACC = RFR + ERP\n"
        f"Term. Reinv Rate = TG / TWACC"
    )
    left_lines = left_column.split('\n')
    right_lines = right_column.split('\n')
    max_lines = max(len(left_lines), len(right_lines))
    left_lines.extend([''] * (max_lines - len(left_lines)))
    right_lines.extend([''] * (max_lines - len(right_lines)))
    combined_lines = []
    for left, right in zip(left_lines, right_lines):
        combined_lines.append(f"{left:<35} {right:<35}")
    summary_text = title + '\n\n' + '\n'.join(combined_lines)
    axs[0, 1].text(0.5, 0.5, summary_text, fontsize=10, fontfamily='monospace', 
             horizontalalignment='center', verticalalignment='center',
             bbox=dict(facecolor='white', alpha=0.8))

    plt.tight_layout()

    # Create a separate figure for Intrinsic Value Distribution only
    fig_distribution_only, ax_dist_only = plt.subplots(figsize=(10, 6))
    plt.style.use('seaborn-v0_8-darkgrid')
    ax_dist_only.hist(results, bins=50, density=True, alpha=0.7, color='skyblue', edgecolor='black')
    ax_dist_only.axvspan(mean_value - 3*std_value, mean_value - 2*std_value, color='red', alpha=0.1, label='±3σ')
    ax_dist_only.axvspan(mean_value + 2*std_value, mean_value + 3*std_value, color='red', alpha=0.1)
    ax_dist_only.axvspan(mean_value - 2*std_value, mean_value - std_value, color='orange', alpha=0.1, label='±2σ')
    ax_dist_only.axvspan(mean_value + std_value, mean_value + 2*std_value, color='orange', alpha=0.1)
    ax_dist_only.axvspan(mean_value - std_value, mean_value + std_value, color='green', alpha=0.1, label='±1σ')
    ax_dist_only.axvline(mean_value, color='red', linestyle='--', label='Mean')
    ax_dist_only.axvline(current_price, color='purple', linestyle='-', label='Current Price')
    ax_dist_only.set_title(f'{company_name} - Intrinsic Value Distribution')
    ax_dist_only.set_xlabel(f'Intrinsic Value per Share ({currency})')
    ax_dist_only.set_ylabel('Density')
    ax_dist_only.legend()
    plt.tight_layout()

    # Create a separate figure for Sensitivity Analysis only
    fig_sensitivity, ax_sens_only = plt.subplots(figsize=(10, 6))
    sensitivity_data = pd.DataFrame.from_dict(sensitivities, orient='index')
    sensitivity_data = sensitivity_data.sort_values('impact', ascending=True)
    ax_sens_only.barh(range(len(sensitivity_data)), sensitivity_data['impact'], align='center')
    ax_sens_only.set_yticks(range(len(sensitivity_data)))
    ax_sens_only.set_yticklabels(sensitivity_data.index)
    ax_sens_only.set_title(f'{company_name} - Sensitivity Analysis')
    ax_sens_only.set_xlabel(f'Impact on Value per Share ({currency}/σ)')
    plt.tight_layout()

    # Create valuation summary dictionary
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
            'Term. Growth': 'RFR',
            'Term. WACC': 'RFR + ERP',
            'Term. Reinv Rate': 'TG / TWACC'
        }
    }

    return fig_es, fig_distribution_only, fig_sensitivity, valuation_summary 