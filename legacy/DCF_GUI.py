import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sys
import os
from datetime import datetime
import subprocess
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import importlib.util

# Import the simulation + Google Sheets/Excel import functions from DCF_main.py
spec = importlib.util.spec_from_file_location("DCF_main", os.path.join(os.path.dirname(os.path.abspath(__file__)), "DCF_main.py"))
DCF_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(DCF_main)

class MonteCarloGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Monte Carlo Valuation Tool")
        self.root.geometry("1300x900")
        main_frame = ttk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        # Left panel (inputs) with scrollable frame
        left_panel_container = ttk.Frame(main_frame)
        left_panel_container.pack(side="left", fill="y", padx=5, pady=5)
        left_canvas = tk.Canvas(left_panel_container, width=420, height=850)
        left_scrollbar = ttk.Scrollbar(left_panel_container, orient="vertical", command=left_canvas.yview)
        self.left_scrollable_frame = ttk.Frame(left_canvas)
        self.left_scrollable_frame.bind(
            "<Configure>",
            lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all"))
        )
        left_canvas.create_window((0, 0), window=self.left_scrollable_frame, anchor="nw")
        left_canvas.configure(yscrollcommand=left_scrollbar.set)
        left_canvas.pack(side="left", fill="y", expand=False)
        left_scrollbar.pack(side="right", fill="y")
        self.create_import_fields(self.left_scrollable_frame)
        self.create_input_fields(self.left_scrollable_frame)
        run_button = ttk.Button(self.left_scrollable_frame, text="Run Monte Carlo Simulation", command=self.run_simulation)
        run_button.pack(pady=20)
        # Right panel (plot + summary)
        self.right_panel = ttk.Frame(main_frame)
        self.right_panel.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        self.notebook = ttk.Notebook(self.right_panel)
        self.notebook.pack(fill="both", expand=True)
        self.plot_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.plot_frame, text="Results")
        self.summary_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.summary_frame, text="Valuation Summary")
        self.summary_text = tk.Text(self.summary_frame, wrap="word", font=("Consolas", 10))
        self.summary_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.summary_text.insert("1.0", "Run a simulation to see the valuation summary here.")
        self.summary_text.config(state="disabled")
        self.canvas_plot = None

    def create_import_fields(self, parent):
        # Google Sheets / Excel template import
        import_frame = ttk.LabelFrame(parent, text="Import from Google Sheets / Excel Template")
        import_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(import_frame, text="Google Sheets link (or ID):").grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=(5, 0))
        self.gsheet_url = ttk.Entry(import_frame, width=42)
        self.gsheet_url.grid(row=1, column=0, columnspan=2, padx=5, pady=(0, 5), sticky="we")

        ttk.Label(import_frame, text="Tab name (company):").grid(row=2, column=0, sticky="w", padx=5)
        self.gsheet_tab = ttk.Entry(import_frame, width=20)
        self.gsheet_tab.grid(row=2, column=1, padx=5, pady=2, sticky="we")

        btn_frame = ttk.Frame(import_frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=5)
        ttk.Button(btn_frame, text="Fetch from Google Sheet", command=self.fetch_from_sheet).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="Fetch from Excel file...", command=self.fetch_from_excel).pack(side="left", padx=3)

        self.import_status = ttk.Label(import_frame, text="", foreground="#1a7a1a", wraplength=380, justify="left")
        self.import_status.grid(row=4, column=0, columnspan=2, sticky="w", padx=5, pady=(0, 5))

    def _apply_fetched_values(self, data, source_label):
        """Pushes a dict of fetched values (from DCF_main._grid_to_app_values)
        into the corresponding Entry widgets, mirroring the Streamlit app."""
        field_to_widget = {
            "price": self.current_price, "shares": self.shares_outstanding, "cash": self.cash,
            "debt": self.debt, "ebit": self.operating_income_base,
            "growth_rate_5y": self.growth_rate_5y, "growth_rate_5_10y": self.growth_rate_5_10y,
            "risk_free_rate": self.risk_free_rate, "equity_risk_premium": self.equity_risk_premium,
            "WACC": self.WACC, "reinvestment_rate_5y": self.reinvestment_rate_5y,
            "reinvestment_rate_5_10y": self.reinvestment_rate_5_10y,
        }
        for key, widget in field_to_widget.items():
            if key in data:
                widget.delete(0, tk.END)
                widget.insert(0, f"{data[key]:.4f}" if key not in ("price", "shares", "cash", "debt", "ebit") else f"{data[key]:.2f}")
        tab_name = self.gsheet_tab.get().strip()
        if tab_name:
            self.company_name.delete(0, tk.END)
            self.company_name.insert(0, tab_name)
        missing = data.get("_missing_fields", [])
        if missing:
            self.import_status.config(
                foreground="#b36b00",
                text=f"⚠️ Imported from {source_label}, but couldn't read: {', '.join(missing)}. Check tab name / layout."
            )
        else:
            self.import_status.config(foreground="#1a7a1a", text=f"✅ All fields imported from {source_label}.")

    def fetch_from_sheet(self):
        url = self.gsheet_url.get().strip()
        tab = self.gsheet_tab.get().strip()
        if not url or not tab:
            messagebox.showerror("Error", "Please enter both the Google Sheets link and the tab name.")
            return
        try:
            data = DCF_main.fetch_from_google_sheet(url, tab)
            self._apply_fetched_values(data, f"tab '{tab}'")
        except Exception as e:
            messagebox.showerror(
                "Error",
                f"Could not read tab '{tab}': {e}\n\nTip: the sheet must be shared as "
                "'Anyone with the link can view'. For a private sheet, use 'Fetch from Excel file...' instead."
            )

    def fetch_from_excel(self):
        tab = self.gsheet_tab.get().strip()
        if not tab:
            messagebox.showerror("Error", "Please enter the tab name (company) to read first.")
            return
        path = filedialog.askopenfilename(title="Select DCF template workbook", filetypes=[("Excel files", "*.xlsx")])
        if not path:
            return
        try:
            data = DCF_main.fetch_from_excel_template(path, tab)
            self._apply_fetched_values(data, f"'{os.path.basename(path)}' / '{tab}'")
        except Exception as e:
            messagebox.showerror("Error", f"Could not read tab '{tab}' from {os.path.basename(path)}: {e}")

    def create_input_fields(self, parent):
        # Company Name and Currency
        company_name_frame = ttk.LabelFrame(parent, text="Company Information")
        company_name_frame.pack(fill="x", padx=5, pady=5)
        ttk.Label(company_name_frame, text="Company Name:").grid(row=0, column=0, padx=5, pady=5)
        self.company_name = ttk.Entry(company_name_frame)
        self.company_name.insert(0, "JD.com")
        self.company_name.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(company_name_frame, text="Currency:").grid(row=1, column=0, padx=5, pady=5)
        self.currency = ttk.Entry(company_name_frame)
        self.currency.insert(0, "USD")
        self.currency.grid(row=1, column=1, padx=5, pady=5)
        
        # Company Information
        company_frame = ttk.LabelFrame(parent, text="Financial Information")
        company_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(company_frame, text="Current Price (USD):").grid(row=0, column=0, padx=5, pady=5)
        self.current_price = ttk.Entry(company_frame)
        self.current_price.insert(0, "33.55")
        self.current_price.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(company_frame, text="Operating Income Base (millions):").grid(row=1, column=0, padx=5, pady=5)
        self.operating_income_base = ttk.Entry(company_frame)
        self.operating_income_base.insert(0, "6610.00")
        self.operating_income_base.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(company_frame, text="Shares Outstanding (millions):").grid(row=2, column=0, padx=5, pady=5)
        self.shares_outstanding = ttk.Entry(company_frame)
        self.shares_outstanding.insert(0, "1524")
        self.shares_outstanding.grid(row=2, column=1, padx=5, pady=5)
        
        ttk.Label(company_frame, text="Cash (millions):").grid(row=3, column=0, padx=5, pady=5)
        self.cash = ttk.Entry(company_frame)
        self.cash.insert(0, "27000")
        self.cash.grid(row=3, column=1, padx=5, pady=5)
        
        ttk.Label(company_frame, text="Debt (millions):").grid(row=4, column=0, padx=5, pady=5)
        self.debt = ttk.Entry(company_frame)
        self.debt.insert(0, "12000")
        self.debt.grid(row=4, column=1, padx=5, pady=5)
        
        # Growth Parameters
        growth_frame = ttk.LabelFrame(parent, text="Growth Parameters")
        growth_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(growth_frame, text="Growth Rate 5y (%):").grid(row=0, column=0, padx=5, pady=5)
        self.growth_rate_5y = ttk.Entry(growth_frame)
        self.growth_rate_5y.insert(0, "9.0")
        self.growth_rate_5y.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(growth_frame, text="Growth Rate 5-10y (%):").grid(row=1, column=0, padx=5, pady=5)
        self.growth_rate_5_10y = ttk.Entry(growth_frame)
        self.growth_rate_5_10y.insert(0, "7.0")
        self.growth_rate_5_10y.grid(row=1, column=1, padx=5, pady=5)
        
        # Risk Parameters
        risk_frame = ttk.LabelFrame(parent, text="Risk Parameters")
        risk_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(risk_frame, text="Risk Free Rate (%):").grid(row=0, column=0, padx=5, pady=5)
        self.risk_free_rate = ttk.Entry(risk_frame)
        self.risk_free_rate.insert(0, "4.44")
        self.risk_free_rate.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(risk_frame, text="Equity Risk Premium (%):").grid(row=1, column=0, padx=5, pady=5)
        self.equity_risk_premium = ttk.Entry(risk_frame)
        self.equity_risk_premium.insert(0, "5.3")
        self.equity_risk_premium.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(risk_frame, text="WACC (%):").grid(row=2, column=0, padx=5, pady=5)
        self.WACC = ttk.Entry(risk_frame)
        self.WACC.insert(0, "9.0")
        self.WACC.grid(row=2, column=1, padx=5, pady=5)
        
        # Reinvestment Rates
        reinv_frame = ttk.LabelFrame(parent, text="Reinvestment Rates")
        reinv_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(reinv_frame, text="Reinvestment Rate 5y (%):").grid(row=0, column=0, padx=5, pady=5)
        self.reinvestment_rate_5y = ttk.Entry(reinv_frame)
        self.reinvestment_rate_5y.insert(0, "35.0")
        self.reinvestment_rate_5y.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(reinv_frame, text="Reinvestment Rate 5-10y (%):").grid(row=1, column=0, padx=5, pady=5)
        self.reinvestment_rate_5_10y = ttk.Entry(reinv_frame)
        self.reinvestment_rate_5_10y.insert(0, "40.0")
        self.reinvestment_rate_5_10y.grid(row=1, column=1, padx=5, pady=5)
        
        # Standard Deviations
        std_frame = ttk.LabelFrame(parent, text="Standard Deviations")
        std_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(std_frame, text="Std Growth 5y (%):").grid(row=0, column=0, padx=5, pady=5)
        self.std_growth_5y = ttk.Entry(std_frame)
        self.std_growth_5y.insert(0, "2.0")
        self.std_growth_5y.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(std_frame, text="Std Growth 5-10y (%):").grid(row=1, column=0, padx=5, pady=5)
        self.std_growth_5_10y = ttk.Entry(std_frame)
        self.std_growth_5_10y.insert(0, "3.0")
        self.std_growth_5_10y.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(std_frame, text="Std Risk Free (%):").grid(row=2, column=0, padx=5, pady=5)
        self.std_risk_free = ttk.Entry(std_frame)
        self.std_risk_free.insert(0, "0.5")
        self.std_risk_free.grid(row=2, column=1, padx=5, pady=5)
        
        ttk.Label(std_frame, text="Std Equity Premium (%):").grid(row=3, column=0, padx=5, pady=5)
        self.std_equity_premium = ttk.Entry(std_frame)
        self.std_equity_premium.insert(0, "0.5")
        self.std_equity_premium.grid(row=3, column=1, padx=5, pady=5)
        
        ttk.Label(std_frame, text="Std WACC (%):").grid(row=4, column=0, padx=5, pady=5)
        self.std_WACC = ttk.Entry(std_frame)
        self.std_WACC.insert(0, "0.5")
        self.std_WACC.grid(row=4, column=1, padx=5, pady=5)
        
        ttk.Label(std_frame, text="Std Reinv 5y (%):").grid(row=5, column=0, padx=5, pady=5)
        self.std_reinv_5y = ttk.Entry(std_frame)
        self.std_reinv_5y.insert(0, "2.5")
        self.std_reinv_5y.grid(row=5, column=1, padx=5, pady=5)
        
        ttk.Label(std_frame, text="Std Reinv 5-10y (%):").grid(row=6, column=0, padx=5, pady=5)
        self.std_reinv_5_10y = ttk.Entry(std_frame)
        self.std_reinv_5_10y.insert(0, "5.0")
        self.std_reinv_5_10y.grid(row=6, column=1, padx=5, pady=5)
        
        # Simulation Parameters
        sim_frame = ttk.LabelFrame(parent, text="Simulation Parameters")
        sim_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(sim_frame, text="Number of Simulations:").grid(row=0, column=0, padx=5, pady=5)
        self.n_simulations = ttk.Entry(sim_frame)
        self.n_simulations.insert(0, "10000")
        self.n_simulations.grid(row=0, column=1, padx=5, pady=5)
        
    def run_simulation(self):
        try:
            company_name = self.company_name.get().strip()
            currency = self.currency.get().strip()
            if not company_name:
                messagebox.showerror("Error", "Please enter a company name")
                return
            if not currency:
                messagebox.showerror("Error", "Please enter a currency")
                return
            params = {
                'company_name': company_name,
                'currency': currency,
                'current_price': float(self.current_price.get()),
                'operating_income_base': float(self.operating_income_base.get()),
                'shares_outstanding': float(self.shares_outstanding.get()),
                'cash': float(self.cash.get()),
                'debt': float(self.debt.get()),
                'growth_rate_5y': float(self.growth_rate_5y.get()) / 100,
                'growth_rate_5_10y': float(self.growth_rate_5_10y.get()) / 100,
                'risk_free_rate': float(self.risk_free_rate.get()) / 100,
                'equity_risk_premium': float(self.equity_risk_premium.get()) / 100,
                'WACC': float(self.WACC.get()) / 100,
                'reinvestment_rate_5y': float(self.reinvestment_rate_5y.get()) / 100,
                'reinvestment_rate_5_10y': float(self.reinvestment_rate_5_10y.get()) / 100,
                'std_growth_5y': float(self.std_growth_5y.get()) / 100,
                'std_growth_5_10y': float(self.std_growth_5_10y.get()) / 100,
                'std_risk_free': float(self.std_risk_free.get()) / 100,
                'std_equity_premium': float(self.std_equity_premium.get()) / 100,
                'std_WACC': float(self.std_WACC.get()) / 100,
                'std_reinv_5y': float(self.std_reinv_5y.get()) / 100,
                'std_reinv_5_10y': float(self.std_reinv_5_10y.get()) / 100,
                'n_simulations': int(self.n_simulations.get())
            }
            fig_es, fig_distribution_only, fig_sensitivity, valuation_summary = DCF_main.run_monte_carlo_simulation(params)
            fig_es.set_size_inches(10, 7)
            fig_es.tight_layout()
            for widget in self.plot_frame.winfo_children():
                widget.destroy()
            self.canvas_plot = FigureCanvasTkAgg(fig_es, master=self.plot_frame)
            self.canvas_plot.draw()
            self.canvas_plot.get_tk_widget().pack(fill="both", expand=True)
            self._display_summary(valuation_summary)
            messagebox.showinfo("Success", f"Monte Carlo simulation for {company_name} completed successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {str(e)}")
            print(f"Error details: {str(e)}")

    def _display_summary(self, valuation_summary):
        lines = [
            f"VALUATION SUMMARY - {valuation_summary['company_name']}",
            f"Date: {valuation_summary['date']}",
            "-" * 40,
            f"Current Price:      {valuation_summary['current_price']}",
            f"Mean Value:         {valuation_summary['mean_value']}",
            f"Median Value:       {valuation_summary['median_value']}",
            f"Upside Potential:   {valuation_summary['upside_potential']}",
            "",
            "Probabilities:",
            f"  Overvaluation:    {valuation_summary['prob_overvalued']}",
            f"  Undervaluation:   {valuation_summary['prob_undervalued']}",
            "",
            "Risk Metrics:",
            f"  VaR 95%:          {valuation_summary['VaR 95%']}",
            f"  CVaR 95%:         {valuation_summary['CVaR 95%']}",
            f"  Std. Deviation:   {valuation_summary['Std. Deviation']}",
            "",
            "Variable Parameters:",
        ]
        for k, v in valuation_summary["Variable Parameters"].items():
            lines.append(f"  {k}: {v}")
        lines.append("")
        lines.append("Terminal Value Params:")
        for k, v in valuation_summary["Terminal Value Params"].items():
            lines.append(f"  {k}: {v}")

        self.summary_text.config(state="normal")
        self.summary_text.delete("1.0", tk.END)
        self.summary_text.insert("1.0", "\n".join(lines))
        self.summary_text.config(state="disabled")

if __name__ == "__main__":
    root = tk.Tk()
    app = MonteCarloGUI(root)
    root.mainloop()
