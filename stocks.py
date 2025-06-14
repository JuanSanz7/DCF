# TEST COMMENT - Please ignore. This is to test file edit functionality.
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np
import logging
from functools import lru_cache
import time
from typing import Dict, List, Optional
import os
import smtplib
from email.message import EmailMessage
from configparser import ConfigParser
from email.utils import make_msgid
from IPython.display import display, HTML
import matplotlib.dates as mdates

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('stock_analysis.log'),
        logging.StreamHandler()
    ]
)

custom_eps_data = {
    "ASML": {2024: 19.3, 2023: 20.6, 2022: 16.1, 2021: 15.0, 2020: 8.9, 2019: 6.1, 2018: 6.0, 2017: 5.0, 2016: 3.8},
    "META": {2024: 23.8, 2023: 14.9, 2022: 8.6, 2021: 14.3, 2020: 10.5, 2019: 6.6, 2018: 5.6, 2017: 3.6, 2016: 2.3, 2015: 1.2},
    "MSFT": {2024: 11.9, 2023: 9.8, 2022: 9.8, 2021: 8.2, 2020: 5.8, 2019: 5.1, 2018: 2.1, 2017: 3.2, 2016: 2.6, 2015: 1.5},
    "GOOGL": {2024: 8.0, 2023: 5.8, 2022: 4.6, 2021: 5.7, 2020: 3.0, 2019: 2.5, 2018: 2.2, 2017: 1.9, 2016: 1.6, 2015: 1.3},
    "CI": {2024: 23.2, 2023: 23.0, 2022: 16.1, 2021: 16.8, 2020: 13.0, 2019: 15.1, 2018: 12.5, 2017: 9.5, 2016: 7.8, 2015: 6.9},
    "TSM": {2024: 6.9, 2023: 5.35, 2022: 6.27, 2021: 4.2, 2020: 3.77, 2019: 2.82, 2018: 2.48, 2017: 2.25, 2016: 2.0, 2015: 1.78},
    "JD": {2024: 3.75, 2023: 2.14, 2022: 0.94, 2021: -0.35, 2020: 4.62, 2019: 1.20, 2018: 0.10, 2017: 0.10, 2016: -0.36, 2015: -1.07},
    "V": {2024: 9.5, 2023: 8.6, 2022: 7.5, 2021: 5.9, 2020: 4.9, 2019: 5.3, 2018: 4.3, 2017: 3.5, 2016: 2.3, 2015: 2.1},
    "BABA": {2024: 7.5, 2023: 4.9, 2022: 4.6, 2021: 3.9, 2020: 8.8, 2019: 8.6, 2018: 5.3, 2017: 4.0, 2016: 3.1, 2015: 2.2},
    "LDO.MI": {2024: 1.90, 2023: 1.71, 2022: 1.58, 2021: 1.32, 2020: 1.25, 2019: 1.28, 2018: 1.22, 2017: 1.18, 2016: 1.13, 2015: 1.09},
    "LVMHF": {2024: 26.0, 2023: 30.4, 2022: 29.7, 2021: 24.1, 2020: 16.6, 2019: 14.3, 2018: 12.7, 2017: 11.2, 2016: 8.7, 2015: 8.0},
    "VID.MC": {2024: 8.8, 2023: 7.3, 2022: 4.7, 2021: 4.5, 2020: 5.3, 2019: 5.6, 2018: 4.7, 2017: 3.6, 2016: 2.8, 2015: 2.4},
    "ROG.SW": {2024: 18.8, 2023: 18.8, 2022: 21.0, 2021: 20.9, 2020: 19.8, 2019: 20.9, 2018: 18.6, 2017: 15.1, 2016: 14.5, 2015: 13.7},
    "TEP.PA": {2024: 8.8, 2023: 10.2, 2022: 10.8, 2021: 9.7, 2020: 6.0, 2019: 7.0, 2018: 5.4, 2017: 5.4, 2016: 3.7, 2015: 3.5}
}

# Currency conversion rates (as of latest data)
CURRENCY_RATES = {
    "TWD": 0.032,  # 1 TWD = 0.032 USD
    "CNY": 0.14,   # 1 CNY = 0.14 USD
}

class StockAnalyzer:
    def __init__(self, tickers: List[str]):
        self.tickers = tickers
        self.setup_plot_style()
        self.html_report = """<html><head><meta charset='utf-8'><title>Stock Analysis Report</title></head><body>"""
        self.html_report += f"<h1>Stock Analysis Report</h1><p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>"
        # Initialize ttm_eps_data and annual_eps_plot_data here to ensure they always exist
        self.ttm_eps_data = {'value': np.nan, 'date': None}
        self.annual_eps_plot_data = pd.Series() # Initialize as an empty Series
        
    def setup_plot_style(self):
        """Set up consistent plot styling"""
        plt.style.use('seaborn-v0_8')
        plt.rcParams['figure.figsize'] = [12, 6]
        plt.rcParams['font.size'] = 10
        
    def validate_dataframe(self, df: pd.DataFrame, required_columns: List[str]) -> bool:
        """Validate DataFrame structure and check for NaN values in critical columns"""
        if not isinstance(df, pd.DataFrame) or df.empty:
            logging.error("DataFrame is not valid or is empty.")
            return False
        
        for col in required_columns:
            if col not in df.columns:
                logging.error(f"Required column '{col}' missing from DataFrame.")
                return False
            if df[col].isnull().any():
                logging.warning(f"Column '{col}' contains NaN values.")
                # Depending on strictness, this could be a return False
        return True

    @lru_cache(maxsize=100)
    def get_stock_data(self, ticker_symbol: str, max_retries: int = 3) -> Optional[yf.Ticker]:
        """Get stock data with retry logic and caching"""
        for attempt in range(max_retries):
            try:
                stock = yf.Ticker(ticker_symbol)
                # Test if we can access the info
                _ = stock.info
                return stock
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logging.warning(f"Attempt {attempt + 1} failed for {ticker_symbol}. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logging.error(f"Failed to get data for {ticker_symbol} after {max_retries} attempts: {str(e)}")
                    return None
        return None

    def style_dataframe(self, df: pd.DataFrame):
        """Apply consistent styling to DataFrames"""
        return df.style.set_table_styles([
            {'selector': 'th', 'props': [('background-color', 'lightblue'), ('color', 'black'), ('text-align', 'center')]},
            {'selector': 'td', 'props': [('text-align', 'center')]}
        ])

    def style_dataframe_html(self, df: pd.DataFrame, show_index: bool = False) -> str:
        """Return styled DataFrame as HTML string with validation"""
        if not isinstance(df, pd.DataFrame):
            raise StockAnalyzerError("Input must be a pandas DataFrame")
        
        try:
            return df.style.set_table_styles([
                {'selector': 'th', 'props': [('background-color', 'lightblue'), ('color', 'black'), ('text-align', 'center'), ('border', '1px solid black')]},
                {'selector': 'td', 'props': [('text-align', 'center'), ('border', '1px solid black')]}
            ]).to_html(index=show_index)
        except Exception as e:
            logging.error(f"Error creating HTML from DataFrame: {str(e)}")
            return df.to_html(index=show_index)  # Return basic HTML if styling fails

    def _prepare_historical_data(self, stock: yf.Ticker, hist: pd.DataFrame) -> pd.DataFrame:
        """Prepares historical data with Diluted EPS and P/E Ratio."""
        try:
            # Validate input DataFrame
            required_columns = ['Close']
            if not self.validate_dataframe(hist, required_columns):
                raise StockAnalyzerError("Invalid historical data structure")

            # Check if custom EPS data exists for the current ticker
            if stock.ticker in custom_eps_data:
                logging.info(f"Using custom EPS data for {stock.ticker}")
                eps_values = custom_eps_data[stock.ticker]
                # Generate dates for the custom EPS data, using July 2nd of each year
                eps_dates = [datetime(year, 7, 2) for year in sorted(eps_values.keys())]
                custom_eps_series = pd.Series([eps_values[year] for year in sorted(eps_values.keys())], index=pd.to_datetime(eps_dates).tz_localize(None))

                # Reindex custom_eps_series to align with hist's daily index
                combined_eps = custom_eps_series.reindex(hist.index)
                combined_eps = combined_eps.bfill().ffill() # Ensure all NaNs are filled, including leading ones

                self.annual_eps_plot_data = custom_eps_series.copy() # Store for direct plotting (original annual points)
                logging.debug(f"DEBUG: annual_eps_plot_data after custom data processing in _prepare_historical_data: {self.annual_eps_plot_data}")

            # This block will now calculate TTM EPS for ALL tickers, regardless of custom annual data
            # It ensures self.ttm_eps_data always holds the latest *true* TTM from Yahoo
            ttm_eps = np.nan
            ttm_date = None
            try:
                if 'Diluted EPS' in stock.quarterly_financials.index and not stock.quarterly_financials.empty:
                    quarterly_diluted_eps = stock.quarterly_financials.loc['Diluted EPS']
                    # Ensure quarterly_diluted_eps index is datetime and timezone-naive
                    quarterly_diluted_eps.index = pd.to_datetime(quarterly_diluted_eps.index, errors='coerce').dropna()
                    quarterly_diluted_eps.index = quarterly_diluted_eps.index.tz_localize(None)
                    quarterly_diluted_eps = quarterly_diluted_eps.sort_index(ascending=False)

                    if len(quarterly_diluted_eps) >= 4:
                        ttm_eps = quarterly_diluted_eps.head(4).sum()
                        # Use the latest date from the quarterly EPS for the TTM date
                        ttm_date = quarterly_diluted_eps.index[0]
                        
                        # Convert TTM EPS to USD for specific stocks
                        if stock.ticker == "TSM":
                            ttm_eps *= CURRENCY_RATES["TWD"]
                        elif stock.ticker in ["JD", "BABA"]:
                            ttm_eps *= CURRENCY_RATES["CNY"]
                    else:
                        logging.warning(f"Less than 4 quarterly Diluted EPS values available for {stock.ticker}. Cannot calculate TTM EPS.")
            except Exception as e:
                logging.error(f"Error calculating TTM EPS for {stock.ticker}: {str(e)}")

            self.ttm_eps_data = {'value': ttm_eps, 'date': ttm_date}

            # If no custom data, or if custom data doesn't cover all years,
            # we need to combine with Yahoo's annual/quarterly EPS for comprehensive plotting
            if stock.ticker not in custom_eps_data:
                # Original logic for fetching EPS from yfinance if no custom data is provided
                try:
                    annual_income_stmt = stock.income_stmt
                    quarterly_income_stmt = stock.quarterly_financials
                    
                    if annual_income_stmt is None or annual_income_stmt.empty:
                        logging.warning(f"No annual income statement data available for {stock.ticker}")
                    if quarterly_income_stmt is None or quarterly_income_stmt.empty:
                        logging.warning(f"No quarterly income statement data available for {stock.ticker}")
                except Exception as e:
                    logging.error(f"Error fetching financial statements for {stock.ticker}: {str(e)}")
                    annual_income_stmt = pd.DataFrame()
                    quarterly_income_stmt = pd.DataFrame()

                # Extract Diluted EPS as a Series, then convert its index to datetime with errors='coerce'
                try:
                    annual_eps = annual_income_stmt.loc['Diluted EPS'].dropna() if 'Diluted EPS' in annual_income_stmt.index else pd.Series()
                    annual_eps.index = pd.to_datetime(annual_eps.index, errors='coerce').dropna()
                    annual_eps.index = annual_eps.index.tz_localize(None)
                    annual_eps = annual_eps.sort_index()

                    quarterly_eps = quarterly_income_stmt.loc['Diluted EPS'].dropna() if 'Diluted EPS' in quarterly_income_stmt.index else pd.Series()
                    quarterly_eps.index = pd.to_datetime(quarterly_eps.index, errors='coerce').dropna()
                    quarterly_eps.index = quarterly_eps.index.tz_localize(None)
                    quarterly_eps = quarterly_eps.sort_index()

                    combined_eps = pd.concat([annual_eps, quarterly_eps]).sort_index().drop_duplicates(keep='last')

                except Exception as e:
                    logging.error(f"Error processing EPS data for {stock.ticker}: {str(e)}")
                    combined_eps = pd.Series(index=hist.index, dtype=float)

                # Ensure combined_eps index is timezone-naive
                if combined_eps.index.tz is not None:
                    combined_eps.index = combined_eps.index.tz_localize(None)

                # Adjust EPS dates to July 2nd for consistent plotting
                if not combined_eps.empty:
                    combined_eps.index = combined_eps.index.map(lambda x: x.replace(month=7, day=2))

                self.annual_eps_plot_data = combined_eps.copy() # Store for direct plotting
                logging.debug(f"DEBUG: annual_eps_plot_data after non-custom data processing in _prepare_historical_data: {self.annual_eps_plot_data}")

            # Drop potential duplicate dates from hist before reindexing
            hist = hist[~hist.index.duplicated(keep='first')]

            # Simplify hist_reindexed creation, as hist should already have a clean index
            hist_reindexed = hist.copy()

            # Ensure combined_eps is aligned to hist_reindexed index right before merge and is a DataFrame
            combined_eps_df = combined_eps.to_frame(name='Diluted EPS')
            combined_eps_df = combined_eps_df.reindex(hist_reindexed.index)

            hist_reindexed = hist_reindexed.merge(combined_eps_df, left_index=True, right_index=True, how='left')
            # The Diluted EPS column in hist_reindexed now contains NaNs for dates before the first provided EPS and between annual points.

            # Calculate P/E Ratio
            hist_reindexed['P/E Ratio'] = hist_reindexed['Close'] / hist_reindexed['Diluted EPS']

            # Ensure columns exist and fill with NaN if they couldn't be computed
            if 'Diluted EPS' not in hist_reindexed.columns:
                hist_reindexed['Diluted EPS'] = np.nan
            if 'P/E Ratio' not in hist_reindexed.columns:
                hist_reindexed['P/E Ratio'] = np.nan

            # Ensure no duplicate indices in the final enriched history
            hist_enriched = hist_reindexed[~hist_reindexed.index.duplicated(keep='first')]
            # Apply ffill() to hist_enriched for Diluted EPS after all merges
            hist_enriched['Diluted EPS'] = hist_enriched['Diluted EPS'].ffill()

            # Recalculate P/E Ratio after final ffill to ensure it aligns with filled EPS
            hist_enriched['P/E Ratio'] = hist_enriched['Close'] / hist_enriched['Diluted EPS']

            self.hist_enriched_for_display = hist_enriched

            logging.info(f"DEBUG: hist_enriched Diluted EPS and P/E Ratio head for {stock.info.get('shortName', stock.ticker)}:\n{hist_enriched[['Diluted EPS', 'P/E Ratio']].head()}")
            logging.info(f"DEBUG: hist_enriched info for {stock.info.get('shortName', stock.ticker)}:")
            hist_enriched.info()

            return hist_enriched
        except Exception as e:
            logging.error(f"Error preparing historical data for {stock.info.get('shortName', stock.ticker)}: {str(e)}")
            return hist

    def analyze_stock(self, ticker_symbol: str):
        try:
            logging.info(f"Analyzing {ticker_symbol}")
            stock = self.get_stock_data(ticker_symbol)
            if stock is None:
                return
            short_name = stock.info.get('shortName', ticker_symbol)
            # Fetch historical data for a specific 10-year period aligned with user-provided EPS
            end_date = datetime.now()
            start_date = end_date.replace(year=end_date.year - 10)
            hist = stock.history(start=start_date, end=end_date)
            # Ensure hist is timezone-naive immediately after fetching
            hist.index = hist.index.tz_localize(None) if hist.index.tz is not None else hist.index
            # Ensure hist has a unique index immediately after fetching
            hist = hist[~hist.index.duplicated(keep='first')]
            
            hist = self._prepare_historical_data(stock, hist) # Enrich hist with EPS and P/E
            
            # HTML output
            self.html_report += f"<h2>{short_name} ({ticker_symbol})</h2>"
            self.html_report += self.display_financial_metrics(stock, hist, short_name) # Add financial metrics and EPS/PE plot
        except Exception as e:
            logging.error(f"Error analyzing {ticker_symbol}: {str(e)}")

    def display_financial_metrics(self, stock: yf.Ticker, hist: pd.DataFrame, short_name: str) -> str:
        """Display financial metrics with enhanced error handling and validation"""
        html_content = ""

        try:
            # Key Metrics
            current_price = stock.info.get('currentPrice', 0)
            ttm_eps = self.ttm_eps_data['value'] if hasattr(self, 'ttm_eps_data') else None
            current_pe = current_price / ttm_eps if ttm_eps and ttm_eps != 0 else None
            forward_eps = stock.info.get('forwardEps', None)
            forward_pe = current_price / forward_eps if forward_eps and forward_eps != 0 else None

            metrics = {
                'Market Cap': f"{stock.info.get('marketCap', np.nan):,.2f}" if stock.info.get('marketCap') else 'N/A',
                'P/E Ratio': f"{current_pe:.2f}" if current_pe else 'N/A',
                'Forward P/E': f"{forward_pe:.2f}" if forward_pe else 'N/A',
                'Beta': f"{stock.info.get('beta', np.nan):.2f}" if stock.info.get('beta') else 'N/A'
            }
            metrics_df = pd.DataFrame(list(metrics.items()), columns=['Metric', 'Value']).reset_index(drop=True)
            html_content += "<h3>Key Metrics</h3>" + self.style_dataframe_html(metrics_df, show_index=False)

            # Company Summary
            summary_data = {
                'shortName': stock.info.get('shortName', 'N/A'),
                'industry': stock.info.get('industry', 'N/A'),
                'sector': stock.info.get('sector', 'N/A'),
                'beta': f"{stock.info.get('beta', np.nan):.2f}" if stock.info.get('beta') else 'N/A'
            }
            summary_df = pd.DataFrame(list(summary_data.items()), columns=['Parameter', 'Value']).transpose()
            summary_df.columns = summary_df.iloc[0]
            summary_df = summary_df[1:]
            html_content += "<h3>Summary</h3>" + self.style_dataframe_html(summary_df, show_index=False)

            # Dividends
            html_content += self._display_dividends(stock)

            # Holders
            html_content += self._display_holders(stock)

            # Valuation
            html_content += self._display_valuation(stock)

            # Targets
            html_content += self._display_targets(stock)

            # Recommendations
            html_content += self._display_recommendations(stock)

            # Earnings Calendar
            html_content += self._display_earnings_calendar(stock)

            # Income Statement
            html_content += self._display_income_statement(stock)

            # Balance Sheet
            html_content += self._display_balance_sheet(stock)

            # Cash Flow
            html_content += self._display_cash_flow(stock)

            # Profitability
            html_content += self._display_profitability(stock)

            # EPS and P/E Plots
            html_content += self._generate_eps_pe_plots(stock, hist, short_name)

            return html_content

        except Exception as e:
            logging.error(f"Error displaying financial metrics for {short_name}: {str(e)}")
            return f"<p>Error displaying financial metrics: {str(e)}</p>"

    def _display_dividends(self, stock: yf.Ticker) -> str:
        """Generate HTML for Dividends section"""
        try:
            info = stock.info
            if not info:
                return "<p>Dividend data not available.</p>"
            
            data = {
                "Annual Dividend Yield (%)": f"{info.get('dividendYield', np.nan) :.2f}" if pd.notnull(info.get('dividendYield')) else 'N/A',
                "5-Year Average Dividend Yield (%)": f"{info.get('fiveYearAvgDividendYield', np.nan) :.2f}" if pd.notnull(info.get('fiveYearAvgDividendYield')) else 'N/A',
                "10-Year Annual Dividend Growth (%)": f"{info.get('tenYrAvgAnnualIncreaseInDividends', np.nan) / 100:.2f}" if pd.notnull(info.get('tenYrAvgAnnualIncreaseInDividends')) else 'N/A',
                "Payout Ratio (%)": f"{info.get('payoutRatio', np.nan) :.2f}" if pd.notnull(info.get('payoutRatio')) else 'N/A'
            }
            df = pd.DataFrame(data, index=[0])
            
            return HTML(f"<h3>Dividends</h3>").data + self.style_dataframe_html(df, show_index=False)
        except Exception as e:
            logging.error(f"Error displaying dividends for {stock.ticker}: {str(e)}")
            return f"<p>Error retrieving dividend data: {str(e)}</p>"

    def _display_holders(self, stock: yf.Ticker) -> str:
        """Generate HTML for Major Holders information"""
        try:
            major_holders = stock.major_holders
            if major_holders is None:
                return "<p>Major holders data not available.</p>"
            
            # If major_holders is a Series, convert it to a DataFrame for consistent processing
            if isinstance(major_holders, pd.Series):
                major_holders_df = major_holders.to_frame().T
            elif isinstance(major_holders, pd.DataFrame):
                major_holders_df = major_holders
            else:
                return "<p>Major holders data in unexpected format.</p>"

            if major_holders_df.empty:
                return "<p>Major holders data not available.</p>"
            
            # Attempt to reset index and set column names more robustly
            # Check if major_holders_df has a MultiIndex, if so, flatten it or reset it
            if isinstance(major_holders_df.index, pd.MultiIndex):
                major_holders_df = major_holders_df.reset_index(level=0, drop=True)
            
            # Ensure it has 2 columns before proceeding, if not, try to reshape
            if major_holders_df.shape[1] != 2:
                if major_holders_df.shape[0] == 2 and major_holders_df.shape[1] > 0: # Handle cases like a single row with multiple columns
                    major_holders_df = major_holders_df.transpose() # Transpose if it's two rows, but columns represent metrics
                elif major_holders_df.shape[1] == 1: # If it's a single column DataFrame
                    major_holders_df = major_holders_df.reset_index()
                else:
                    logging.warning(f"Unexpected major_holders DataFrame shape for {stock.ticker}: {major_holders_df.shape}. Expected 2 columns or convertible. Skipping display.")
                    return "<p>Major holders data available, but in unexpected format or shape for display.</p>"
            
            if major_holders_df.shape[1] != 2:
                logging.warning(f"Major holders DataFrame still not in 2 columns after reshaping attempts for {stock.ticker}. Final shape: {major_holders_df.shape}. Skipping display.")
                return "<p>Major holders data available, but could not be formatted for display.</p>"

            major_holders_df.columns = ['Metric', 'Value']
            major_holders_df.set_index('Metric', inplace=True)
            major_holders_df = major_holders_df.transpose()

            # Rename columns to match the desired output
            major_holders_df = major_holders_df.rename(columns={
                '% Held by Insiders': 'Held by insiders (%)',
                '% Held by Institutions': 'Held by institutions (%)',
                'Shares Outstanding': 'Shares Outstanding (M)'  # Assuming this needs to be in Millions
            })
            
            # Convert 'Shares Outstanding (M)' to millions if it's a large number
            if 'Shares Outstanding (M)' in major_holders_df.columns:
                try:
                    major_holders_df['Shares Outstanding (M)'] = pd.to_numeric(major_holders_df['Shares Outstanding (M)'].astype(str).str.replace(',', '').str.replace('%', ''), errors='coerce') / 1_000_000
                    major_holders_df['Shares Outstanding (M)'] = major_holders_df['Shares Outstanding (M)'].apply(lambda x: f"{x:,.2f}" if pd.notnull(x) else 'N/A')
                except Exception as e:
                    logging.warning(f"Error converting Shares Outstanding (M) for {stock.ticker}: {e}. Keeping original format.")
            
            # Format percentage columns
            for col in ['Held by insiders (%)', 'Held by institutions (%)']:
                if col in major_holders_df.columns:
                    # Remove '%' before converting to float
                    major_holders_df[col] = major_holders_df[col].astype(str).str.replace('%', '').astype(float)
                    major_holders_df[col] = major_holders_df[col].apply(lambda x: f"{x * 100:.2f}" if pd.notnull(x) else 'N/A')

            return HTML(f"<h3>Holders</h3>").data + self.style_dataframe_html(major_holders_df, show_index=False)
        except Exception as e:
            logging.error(f"Error displaying major holders for {stock.ticker}: {str(e)}")
            return f"<p>Error retrieving major holders data: {str(e)}</p>"

    def _display_valuation(self, stock: yf.Ticker) -> str:
        """Generate HTML for Valuation Measures"""
        try:
            info = stock.info
            if not info:
                return "<p>Valuation data not available.</p>"
            
            trailing_pe = info.get('trailingPE', np.nan)
            forward_pe = info.get('forwardPE', np.nan)

            data = {
                'trailingPE': f"{trailing_pe:.2f}" if pd.notnull(trailing_pe) else 'N/A',
                'forwardPE': f"{forward_pe:.2f}" if pd.notnull(forward_pe) else 'N/A',
            }
            df = pd.DataFrame(data, index=[0])

            return HTML(f"<h3>Valuation</h3>").data + self.style_dataframe_html(df, show_index=False)
        except Exception as e:
            logging.error(f"Error displaying valuation for {stock.ticker}: {str(e)}")
            return f"<p>Error retrieving valuation data: {str(e)}</p>"

    def _display_targets(self, stock: yf.Ticker) -> str:
        """Generate HTML for Analyst Price Targets"""
        try:
            info = stock.info
            if not info:
                return "<p>Analyst target data not available.</p>"
            
            target_mean_price = info.get('targetMeanPrice', np.nan)
            target_high_price = info.get('targetHighPrice', np.nan)
            target_median_price = info.get('targetMedianPrice', np.nan)
            current_price = info.get('currentPrice', np.nan)
            recommendation_mean = info.get('recommendationMean', np.nan)
            recommendation_key = info.get('recommendationKey', 'N/A')

            data = {
                'targetMeanPrice': f"{target_mean_price:.2f}" if pd.notnull(target_mean_price) else 'N/A',
                'targetHighPrice': f"{target_high_price:.2f}" if pd.notnull(target_high_price) else 'N/A',
                'targetMedianPrice': f"{target_median_price:.2f}" if pd.notnull(target_median_price) else 'N/A',
                'currentPrice': f"{current_price:.2f}" if pd.notnull(current_price) else 'N/A',
                'recommendationMean': f"{recommendation_mean:.2f}" if pd.notnull(recommendation_mean) else 'N/A',
                'recommendationKey': recommendation_key
            }
            df = pd.DataFrame(list(data.items()), columns=['Metric', 'Value'])
            
            return HTML(f"<h3>Targets</h3>").data + self.style_dataframe_html(df, show_index=False)
        except Exception as e:
            logging.error(f"Error displaying analyst targets for {stock.ticker}: {str(e)}")
            return f"<p>Error retrieving analyst targets data: {str(e)}</p>"

    def _display_recommendations(self, stock: yf.Ticker) -> str:
        """Generate HTML for Analyst Recommendations"""
        try:
            recommendations = stock.recommendations
            if recommendations is None or recommendations.empty:
                return "<p>Analyst recommendations data not available.</p>"
            
            # Use only the latest recommendation for each period
            recommendations_df = recommendations.groupby('period').last().reset_index()

            # Select and reorder columns as seen in the image
            cols = ['period', 'strongBuy', 'buy', 'hold', 'sell', 'strongSell']
            recommendations_df = recommendations_df[cols]
            
            return HTML(f"<h3>Recommendations</h3>").data + self.style_dataframe_html(recommendations_df, show_index=False)
        except Exception as e:
            logging.error(f"Error displaying recommendations for {stock.ticker}: {str(e)}")
            return f"<p>Error retrieving recommendations data: {str(e)}</p>"

    def _display_earnings_calendar(self, stock: yf.Ticker) -> str:
        """Generate HTML for Earnings Calendar"""
        try:
            # Initialize empty DataFrame for combined data
            combined_df = pd.DataFrame(columns=['Earnings Date', 'EPS Estimate', 'Reported EPS', 'Surprise (%)'])
            
            # Get future earnings data from calendar
            calendar = stock.calendar
            logging.info(f"Calendar data type: {type(calendar)}")
            logging.info(f"Calendar data: {calendar}")
            
            if calendar is not None:
                # Handle both DataFrame and dict formats
                if isinstance(calendar, pd.DataFrame) and not calendar.empty:
                    future_date = calendar.index[0] if not calendar.empty else None
                    future_eps = calendar['Earnings Average'].iloc[0] if 'Earnings Average' in calendar.columns else None
                elif isinstance(calendar, dict):
                    # Extract date and EPS from dictionary format
                    earnings_date = calendar.get('Earnings Date')
                    earnings_avg = calendar.get('Earnings Average')
                    
                    if isinstance(earnings_date, list) and len(earnings_date) > 0:
                        future_date = pd.to_datetime(earnings_date[0])
                    else:
                        future_date = None
                        
                    if isinstance(earnings_avg, list) and len(earnings_avg) > 0:
                        future_eps = earnings_avg[0]
                    else:
                        future_eps = None
                else:
                    future_date = None
                    future_eps = None
                
                if future_date is not None:
                    future_row = pd.DataFrame({
                        'Earnings Date': [future_date.strftime('%Y-%m-%d')],
                        'EPS Estimate': [f"{future_eps:.2f}" if pd.notnull(future_eps) else 'N/A'],
                        'Reported EPS': ['N/A'],  # Future earnings haven't been reported yet
                        'Surprise (%)': ['N/A']   # No surprise for future earnings
                    })
                    combined_df = pd.concat([future_row, combined_df], ignore_index=True)
            
            # Get historical earnings data
            earnings_history = stock.earnings_history
            logging.info(f"Earnings history type: {type(earnings_history)}")
            logging.info(f"Earnings history data: {earnings_history}")
            
            if earnings_history is not None and not earnings_history.empty:
                # Ensure the index is named 'Date' and convert to datetime
                if earnings_history.index.name is None:
                    earnings_history.index.name = 'Date'
                
                earnings_history.index = pd.to_datetime(earnings_history.index, errors='coerce').dropna().tz_localize(None)
                earnings_history = earnings_history.sort_index(ascending=False)  # Show most recent first
                
                # Select and rename columns
                relevant_cols = {
                    'epsEstimate': 'EPS Estimate',
                    'epsActual': 'Reported EPS',
                    'surprisePercent': 'Surprise (%)'
                }
                
                # Filter for only existing relevant columns before renaming
                cols_to_select = [col for col in relevant_cols.keys() if col in earnings_history.columns]
                hist_df = earnings_history[cols_to_select].rename(columns=relevant_cols)
                
                # Add 'Earnings Date' from the index
                hist_df.insert(0, 'Earnings Date', hist_df.index.strftime('%Y-%m-%d'))
                
                # Format numerical values
                for col in ['EPS Estimate', 'Reported EPS']:
                    if col in hist_df.columns:
                        hist_df[col] = hist_df[col].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else 'N/A')
                
                if 'Surprise (%)' in hist_df.columns:
                    hist_df['Surprise (%)'] = hist_df['Surprise (%)'].apply(
                        lambda x: f"{x * 100:.2f}" if pd.notnull(x) else 'N/A'
                    )
                
                # Combine with future data
                combined_df = pd.concat([combined_df, hist_df], ignore_index=True)
            
            if combined_df.empty:
                return "<p>Earnings calendar data not available.</p>"
            
            return HTML(f"<h3>Earnings Calendar</h3>").data + self.style_dataframe_html(combined_df, show_index=False)
            
        except Exception as e:
            logging.error(f"Error displaying earnings calendar for {stock.ticker}: {str(e)}")
            return f"<p>Error retrieving earnings calendar data: {str(e)}</p>"

    def _display_income_statement(self, stock: yf.Ticker) -> str:
        """Generate HTML for Income Statement"""
        try:
            income_stmt = stock.income_stmt
            quarterly_income_stmt = stock.quarterly_financials

            if income_stmt is None or income_stmt.empty:
                return "<p>Income Statement data not available.</p>"
            
            fields_of_interest = [
                'Total Revenue',
                'Research And Development',
                'EBITDA',
                'Operating Income',
                'Net Income',
                'Diluted EPS'
            ]
            
            # Calculate TTM for relevant fields from quarterly data
            ttm_values = {}
            for field in fields_of_interest:
                if field in quarterly_income_stmt.index:
                    field_values = pd.to_numeric(quarterly_income_stmt.loc[field][:4], errors='coerce')
                    if field_values.count() == 4:
                        ttm_values[field] = field_values.sum()
                    else:
                        ttm_values[field] = np.nan
                else:
                    ttm_values[field] = np.nan

            ttm_df_transposed = pd.DataFrame(ttm_values, index=["TTM"]).transpose() / 1_000_000
            ttm_df_transposed = ttm_df_transposed.apply(lambda col: col.map(lambda x: f"{x:,.2f}" if isinstance(x, (int, float)) and not np.isnan(x) else 'N/A')) # Changed applymap to apply with map

            filtered_data = {f: income_stmt.loc[f] if f in income_stmt.index else np.nan for f in fields_of_interest}
            filtered_annual_income_statement = pd.DataFrame(filtered_data) / 1_000_000
            filtered_annual_income_statement = filtered_annual_income_statement.apply(lambda col: col.map(lambda x: f"{x:,.2f}" if isinstance(x, (int, float)) and not np.isnan(x) else 'N/A')) # Changed applymap to apply with map
            filtered_annual_income_statement = filtered_annual_income_statement.transpose()
            
            final_income_statement = pd.concat([ttm_df_transposed, filtered_annual_income_statement], axis=1)
            final_income_statement.columns = final_income_statement.columns.astype(str)
            final_income_statement.columns.values[0] = 'TTM'

            return HTML(f"<h3>Income Statement (in Millions)</h3>").data + self.style_dataframe_html(final_income_statement)
        except Exception as e:
            logging.error(f"Error displaying income statement for {stock.ticker}: {str(e)}")
            return f"<p>Error retrieving income statement data: {str(e)}</p>"

    def _display_balance_sheet(self, stock: yf.Ticker) -> str:
        """Generate HTML for Balance Sheet"""
        try:
            balance = stock.balance_sheet
            if balance is None or balance.empty:
                return "<p>Balance Sheet data not available.</p>"
            
            filtered_balance = balance.loc[['Cash And Cash Equivalents', 'Total Assets', 'Long Term Debt And Capital Lease Obligation', 'Total Debt', 'Total Liabilities Net Minority Interest', 'Stockholders Equity']] / 1_000_000
            filtered_balance.columns = filtered_balance.columns.astype(str)
            filtered_balance = filtered_balance.apply(lambda col: col.map(lambda x: f"{x:,.2f}" if isinstance(x, (int, float)) and not np.isnan(x) else 'N/A')) # Changed applymap to apply with map

            return HTML(f"<h3>Balance (in Millions)</h3>").data + self.style_dataframe_html(filtered_balance)
        except Exception as e:
            logging.error(f"Error displaying balance sheet for {stock.ticker}: {str(e)}")
            return f"<p>Error retrieving balance sheet data: {str(e)}</p>"

    def _display_cash_flow(self, stock: yf.Ticker) -> str:
        """Generate HTML for Cash Flow Statement"""
        try:
            cashflow = stock.cashflow
            cashflow_qtr = stock.quarterly_cashflow

            if cashflow is None or cashflow.empty:
                return "<p>Cash Flow data not available.</p>"
            
            fields_of_interest = ['Net Income From Continuing Operations', 'Depreciation And Amortization', 'Stock Based Compensation', 'Operating Gains Losses', 'Change In Working Capital', 'Operating Cash Flow', 'Capital Expenditure', 'Net PPE Purchase And Sale', 'Net Business Purchase And Sale', 'Investing Cash Flow', 'Financing Cash Flow', 'Free Cash Flow']
            
            ttm_values = {}
            for field in fields_of_interest:
                if field in cashflow_qtr.index:
                    field_values = pd.to_numeric(cashflow_qtr.loc[field][:4], errors='coerce')
                    if field_values.count() == 4:
                        ttm_values[field] = field_values.sum()
                    else:
                        ttm_values[field] = np.nan
                else:
                    ttm_values[field] = np.nan
            
            ttm_df_transposed = pd.DataFrame(ttm_values, index=["TTM"]).transpose() / 1_000_000
            ttm_df_transposed = ttm_df_transposed.apply(lambda col: col.map(lambda x: f"{x:,.2f}" if isinstance(x, (int, float)) and not np.isnan(x) else 'N/A')) # Changed applymap to apply with map

            filtered_cashflow = pd.DataFrame(index=fields_of_interest, columns=cashflow.columns)
            for field in fields_of_interest:
                if field in cashflow.index:
                    filtered_cashflow.loc[field] = cashflow.loc[field] / 1_000_000
                else:
                    filtered_cashflow.loc[field] = np.nan

            filtered_cashflow = filtered_cashflow.apply(lambda col: col.map(lambda x: f"{x:,.2f}" if isinstance(x, (int, float)) and not np.isnan(x) else 'N/A')) # Changed applymap to apply with map

            final_cashflow = pd.concat([ttm_df_transposed, filtered_cashflow], axis=1)
            final_cashflow.columns = final_cashflow.columns.astype(str)
            final_cashflow.columns.values[0] = 'TTM'

            return HTML(f"<h3>Cash Flow (in Millions)</h3>").data + self.style_dataframe_html(final_cashflow)
        except Exception as e:
            logging.error(f"Error displaying cash flow for {stock.ticker}: {str(e)}")
            return f"<p>Error retrieving cash flow data: {str(e)}</p>"

    def _display_profitability(self, stock: yf.Ticker) -> str:
        """Generate HTML for Profitability metrics"""
        try:
            info = stock.info
            if not info:
                return "<p>Profitability data not available.</p>"
            
            data = {
                "Profit Margin (%)": f"{info.get('profitMargins', np.nan) * 100:.2f}" if pd.notnull(info.get('profitMargins')) else 'N/A',
                "Operating Margin (%)": f"{info.get('operatingMargins', np.nan) * 100:.2f}" if pd.notnull(info.get('operatingMargins')) else 'N/A',
            }
            df = pd.DataFrame(data, index=[0])

            return HTML(f"<h3>Profitability</h3>").data + self.style_dataframe_html(df, show_index=False)
        except Exception as e:
            logging.error(f"Error displaying profitability for {stock.ticker}: {str(e)}")
            return f"<p>Error retrieving profitability data: {str(e)}</p>"

    def _generate_eps_pe_plots(self, stock: yf.Ticker, hist: pd.DataFrame, short_name: str) -> str:
        """Generate EPS and P/E ratio plots with error handling"""
        plot_html = "" # Initialize html_content
        try:
            if not isinstance(hist, pd.DataFrame) or hist.empty:
                raise StockAnalyzerError("Invalid historical data for plotting")

            # Check if Diluted EPS data is available before plotting
            # For tickers with custom EPS, use the stored annual EPS data directly for precise plotting
            if stock.ticker in custom_eps_data:
                # Use the stored annual EPS data; its index already has the correct dates (July 2nd)
                annual_eps_for_plot = self.annual_eps_plot_data.copy()
                # Ensure only one point per year by dropping duplicates, keeping the latest if any
                annual_eps_for_plot = annual_eps_for_plot[~annual_eps_for_plot.index.duplicated(keep='last')]

            elif 'Diluted EPS' in stock.income_stmt.index and not stock.income_stmt.loc['Diluted EPS'].isnull().all():
                # For other tickers, extract annual/quarterly EPS directly for plotting, not the ffill'd daily data
                annual_eps_raw = stock.income_stmt.loc['Diluted EPS'].dropna() if 'Diluted EPS' in stock.income_stmt.index else pd.Series()
                annual_eps_raw.index = pd.to_datetime(annual_eps_raw.index, errors='coerce').dropna()
                annual_eps_raw.index = annual_eps_raw.index.tz_localize(None)
                annual_eps_raw = annual_eps_raw.sort_index()

                quarterly_eps_raw = stock.quarterly_financials.loc['Diluted EPS'].dropna() if 'Diluted EPS' in stock.quarterly_financials.index else pd.Series()
                quarterly_eps_raw.index = pd.to_datetime(quarterly_eps_raw.index, errors='coerce').dropna()
                quarterly_eps_raw.index = quarterly_eps_raw.index.tz_localize(None)
                quarterly_eps_raw = quarterly_eps_raw.sort_index()

                combined_eps_raw = pd.concat([annual_eps_raw, quarterly_eps_raw]).sort_index().drop_duplicates(keep='last')
                
                # Adjust EPS dates to July 2nd for consistent plotting
                if not combined_eps_raw.empty:
                    combined_eps_raw.index = combined_eps_raw.index.map(lambda x: x.replace(month=7, day=2))
                
                annual_eps_for_plot = combined_eps_raw.copy()
                annual_eps_for_plot = annual_eps_for_plot[~annual_eps_for_plot.index.duplicated(keep='last')] # Ensure unique points per year
            else:
                logging.warning(f"Diluted EPS data not available for {stock.info.get('shortName', stock.ticker)}. Skipping EPS plot.")
                annual_eps_for_plot = pd.Series() # Empty Series

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(28, 7))
            color_eps = 'tab:red'
            ax1.set_xlabel('Date')
            ax1.set_ylabel('EPS', color=color_eps)
            
            if not annual_eps_for_plot.empty:
                logging.debug(f"DEBUG: annual_eps_for_plot before TTM addition in _generate_eps_pe_plots: {annual_eps_for_plot}")
                current_year = datetime.now().year
                # Only add TTM EPS for the current year if it's not already in custom/annual data
                if current_year not in annual_eps_for_plot.index.year and not np.isnan(self.ttm_eps_data['value']) and self.ttm_eps_data['date'] is not None:
                    current_year_date = datetime(current_year, 7, 2) # Align to July 2nd
                    ttm_series = pd.Series([self.ttm_eps_data['value']], index=[current_year_date])
                    annual_eps_for_plot = pd.concat([annual_eps_for_plot, ttm_series]).sort_index().drop_duplicates(keep='last')

                # Plot with markers and a line connecting the annual points
                ax1.plot(annual_eps_for_plot.index, annual_eps_for_plot, marker='o', linestyle='-', color=color_eps)

                # Generate tick locations for January 1st of each year represented in the data
                years_in_data = annual_eps_for_plot.index.year.unique().sort_values()
                yearly_ticks = [datetime(year, 1, 1) for year in years_in_data]

                ax1.set_xticks(yearly_ticks)
                ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
                # Ensure labels are centered visually
                for label in ax1.get_xticklabels():
                    label.set_horizontalalignment('center')

                # Set x-axis limits to include some padding on both sides
                padding_days = 180 # Roughly half a year on each side
                start_date = hist.index.min() - pd.Timedelta(days=padding_days)
                end_date = hist.index.max() + pd.Timedelta(days=padding_days)
                ax1.set_xlim(start_date, end_date)
            else:
                ax1.text(0.5, 0.5, 'Diluted EPS data not available', horizontalalignment='center', verticalalignment='center', transform=ax1.transAxes, fontsize=12, color='red')

            ax1.tick_params(axis='y', labelcolor=color_eps)
            
            color_price = 'tab:blue'
            ax3 = ax1.twinx()
            ax3.set_ylabel('Stock Price', color=color_price)
            ax3.plot(hist.index, hist['Close'], color=color_price, label='Stock Price', linewidth=2.0)
            ax3.tick_params(axis='y', labelcolor=color_price)
            ax1.grid(True)
            
            ax2.set_title(f'{short_name} P/E Ratio Over Time')
            ax2.set_xlabel('Date')
            ax2.set_ylabel('P/E Ratio')
            
            # Use the daily P/E Ratio from hist for plotting
            if 'P/E Ratio' in hist.columns and not hist['P/E Ratio'].empty and not hist['P/E Ratio'].isnull().all():
                ax2.plot(hist.index, hist['P/E Ratio'], color='tab:orange', label='P/E Ratio')
                ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m')) # Format as Year-Month
                ax2.set_xlim(hist.index.min(), hist.index.max()) # Set limits to match price data range
            else:
                ax2.text(0.5, 0.5, 'P/E Ratio data not available', horizontalalignment='center', verticalalignment='center', transform=ax2.transAxes, fontsize=12, color='red')

            ax2.grid(True)
            fig.suptitle(f'{short_name} Financial Metrics Over Last 10 Years')
            fig.tight_layout()
            fig.subplots_adjust(top=0.88)
            # fig.autofmt_xdate() # Auto-format to prevent labels from overlapping - Removed to allow manual control of label alignment
            
            # Save plot to a BytesIO object and embed as base64 in HTML
            import io
            import base64
            buf = io.BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight')
            buf.seek(0)
            image_base64 = base64.b64encode(buf.read()).decode('utf-8')
            plt.close(fig)
            plot_html = f"<img src='data:image/png;base64,{image_base64}' alt='{short_name} Financial Metrics Plot'>"

            return plot_html
        except Exception as e:
            logging.error(f"Error generating plots for {short_name}: {str(e)}")
            return f"<p>Error generating financial metrics plots: {str(e)}</p>"

    def run_analysis(self):
        """Run analysis for all tickers with error handling"""
        try:
            if not self.tickers:
                raise StockAnalyzerError("No tickers to analyze")

            for ticker in self.tickers:
                try:
                    self.analyze_stock(ticker)
                except Exception as e:
                    logging.error(f"Error analyzing {ticker}: {str(e)}")
                    continue

            # Save report
            try:
                self.save_html_report()
            except Exception as e:
                logging.error(f"Error saving HTML report: {str(e)}")

        except Exception as e:
            logging.error(f"Error in run_analysis: {str(e)}")

    def save_html_report(self):
        """Save HTML report with error handling"""
        try:
            self.html_report += "</body></html>"
            
            # Create output directory if it doesn't exist
            output_dir = "stock_analysis_output"
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate filename with current date
            current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_filename = f"stock_report_{current_date}.html"
            report_path = os.path.join(output_dir, report_filename)
            
            # Clean up old reports (keep only the last 5)
            old_reports = sorted([f for f in os.listdir(output_dir) if f.startswith("stock_report_") and f.endswith(".html")])
            if len(old_reports) > 5:
                for old_report in old_reports[:-5]:  # Keep the 5 most recent reports
                    try:
                        os.remove(os.path.join(output_dir, old_report))
                    except Exception as e:
                        logging.warning(f"Could not remove old report {old_report}: {str(e)}")
            
            # Save new report
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(self.html_report)
            
            logging.info(f"Report saved to {report_path}")
            
            # Store the path for email attachment
            self.html_path = report_path
            
        except Exception as e:
            logging.error(f"Error saving HTML report: {str(e)}")
            raise

    def send_email_with_attachment(self):
        try:
            config = ConfigParser()
            config.read(os.path.expanduser('~/config.ini'))
            password = config.get('email', 'password')
            send_from = 'j.sanz.cristobal@gmail.com'
            send_to = 'j.sanz.cristobal@gmail.com'
            subject = f'Stocks Report - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
            body = 'Please find attached the latest stocks report.'
            msg = EmailMessage()
            msg['Subject'] = subject
            msg['From'] = send_from
            msg['To'] = send_to
            msg.set_content(body)
            msg.add_alternative(self.html_report, subtype='html')
            with open(self.html_path, 'rb') as f:
                file_data = f.read()
                file_name = os.path.basename(f.name)
            msg.add_attachment(file_data, maintype='application', subtype='octet-stream', filename=file_name)
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(send_from, password)
                server.send_message(msg)
            logging.info(f"Email sent to {send_to}")
        except Exception as e:
            logging.error(f"Error sending email: {str(e)}")

def main():
    # Define your list of stock tickers
    tickers = list(custom_eps_data.keys())
    output_dir = "stock_analysis_output"
    os.makedirs(output_dir, exist_ok=True)
    analyzer = StockAnalyzer(tickers)
    analyzer.run_analysis()
    # Send the report by email
    analyzer.send_email_with_attachment()

if __name__ == "__main__":
    main() 