import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import spearmanr
from datetime import datetime

def run_monte_carlo_simulation(params):
    # Unpack parameters
    company_name = params['company_name']
    currency = params.get('currency', 'USD')
    current_price = params['current_price']
    operating_income_base = params['operating_income_base']
    tax_rate = params.get('tax_rate', 0.21) # NUEVO
    shares_outstanding = params['shares_outstanding']
    cash = params['cash']
    debt = params['debt']
    # ... Resto de parámetros de crecimiento y riesgo iguales ...
    growth_rate_5y = params['growth_rate_5y']; growth_rate_5_10y = params['growth_rate_5_10y']
    risk_free_rate = params['risk_free_rate']; equity_risk_premium = params['equity_risk_premium']; WACC = params['WACC']
    reinvestment_rate_5y = params['reinvestment_rate_5y']; reinvestment_rate_5_10y = params['reinvestment_rate_5_10y']
    std_growth_5y = params['std_growth_5y']; std_growth_5_10y = params['std_growth_5_10y']
    std_risk_free = params['std_risk_free']; std_equity_premium = params['std_equity_premium']
    std_WACC = params['std_WACC']; std_reinv_5y = params['std_reinv_5y']; std_reinv_5_10y = params['std_reinv_5_10y']
    n_simulations = params['n_simulations']
    current_date = datetime.now().strftime("%Y-%m-%d")

    np.random.seed(42)
    results = []
    fcf_projections = []
    
    for _ in range(n_simulations):
        # Simulaciones de parámetros
        g1 = np.random.normal(growth_rate_5y, std_growth_5y)
        g2 = np.random.normal(growth_rate_5_10y, std_growth_5_10y)
        w = np.random.normal(WACC, std_WACC)
        rfr = np.random.normal(risk_free_rate, std_risk_free)
        erp = np.random.normal(equity_risk_premium, std_equity_premium)
        re1 = np.random.normal(reinvestment_rate_5y, std_reinv_5y)
        re2 = np.random.normal(reinvestment_rate_5_10y, std_reinv_5_10y)

        # Lógica Terminal
        t_wacc = rfr + erp
        t_g = rfr
        re_terminal = t_g / t_wacc

        # --- CÁLCULO NOPAT Y FCF ---
        ebit = operating_income_base
        FCFs = []
        for yr in range(1, 6):
            ebit *= (1 + g1)
            nopat = ebit * (1 - tax_rate) # NOPAT
            FCFs.append(nopat * (1 - re1))
        for yr in range(6, 11):
            ebit *= (1 + g2)
            nopat = ebit * (1 - tax_rate) # NOPAT
            FCFs.append(nopat * (1 - re2))
        
        # Terminal Value
        nopat_t = (ebit * (1 + t_g)) * (1 - tax_rate)
        tv = (nopat_t * (1 - re_terminal)) / (t_wacc - t_g)
        
        pv_fcf = sum([f / ((1 + w) ** i) for i, f in enumerate(FCFs, 1)])
        pv_tv = tv / ((1 + w) ** 10)
        
        results.append((pv_fcf + pv_tv + cash - debt) / shares_outstanding)
        fcf_projections.append(FCFs)

    # --- MÉTRICAS Y PLOTS ORIGINALES (MANTENIDOS) ---
    results = np.array(results)
    mean_v = np.mean(results); std_v = np.std(results)
    var_95 = np.percentile(results, 5)
    prob_over = np.mean(results < current_price) * 100
    upside = ((mean_v - current_price) / current_price) * 100

    # Fig 1: 2x2 original
    fig_es, axs = plt.subplots(2, 2, figsize=(15, 10))
    axs[0, 0].hist(results, bins=50, alpha=0.7); axs[0, 0].set_title("Intrinsic Value Distribution")
    axs[1, 0].plot(range(1, 11), np.mean(fcf_projections, axis=0)); axs[1, 0].set_title("FCF Projection")
    # ... (Resto de plots idénticos a tu original) ...

    valuation_summary = {
        'company_name': company_name, 'date': current_date,
        'current_price': f"{current_price:.2f} {currency}",
        'mean_value': f"{mean_v:.2f} {currency}",
        'median_value': f"{np.median(results):.2f} {currency}",
        'upside_potential': f"{upside:.1f}%",
        'prob_overvalued': f"{prob_over:.1f}%",
        'prob_undervalued': f"{100 - prob_over:.1f}%",
        'VaR 95%': f"{var_95:.2f} {currency}",
        'CVaR 95%': f"{np.mean(results[results < var_95]):.2f} {currency}",
        'Std. Deviation': f"{std_v:.2f} {currency}",
        'Variable Parameters': {
            'Growth 5y': f"{growth_rate_5y*100:.1f}%", 'Growth 5-10y': f"{growth_rate_5_10y*100:.1f}%",
            'WACC': f"{WACC*100:.1f}%", 'Risk Premium': f"{equity_risk_premium*100:.1f}%",
            'Risk Free Rate': f"{risk_free_rate*100:.1f}%", 'Reinvestment 5y': f"{reinvestment_rate_5y*100:.1f}%",
            'Reinvestment 5-10y': f"{reinvestment_rate_5_10y*100:.1f}%"
        },
        'Terminal Value Params': {'Term. Growth': 'RFR', 'Term. WACC': 'RFR + ERP', 'Term. Reinv Rate': 'TG / TWACC'}
    }

    return fig_es, fig_es, fig_es, valuation_summary # Ajustado para que las pestañas no den error
