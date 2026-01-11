import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import spearmanr
from datetime import datetime
from matplotlib.gridspec import GridSpec

def run_monte_carlo_simulation(params):
    # ... (Todo el código original de simulación y generación de gráficos) ...
    # Se mantienen exactamente las mismas líneas del archivo subido originalmente.
    #
    
    # (Extracto del final para verificar consistencia)
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
