# Value field: DCF Monte Carlo

A personal intrinsic-valuation workbench. You set the inputs of a Damodaran-style FCFF model, give each uncertain input a probability distribution (with an advisor that suggests one), simulate tens of thousands of futures, and see the whole field of plausible values against the market price. Every run is saved to a register with its complete inputs, so you can follow a company's valuation over time and see what changed.

Everything is open source and free: Python (FastAPI, NumPy, SciPy, SQLAlchemy), React with Vite, Tailwind and Apache ECharts, and SQLite. There are no paid services or subscriptions.

## Quick start

**Local (recommended).** You need Python 3.10+ and Node 18+.

```bash
./run.sh          # macOS / Linux
run.bat           # Windows
```

This builds the UI once, installs the backend and opens http://127.0.0.1:8000. The register is stored in `~/.dcfmc/valuations.db` (change it with `DCF_DATA_DIR`).

**Docker.**

```bash
docker compose up --build    # register kept in ./data
```

**Migrating from v1 (Streamlit).** Old runs saved in `saved_analyses/`, or unzipped from v1's "Export ZIP", can be imported with:

```bash
python -m dcfmc import-legacy path/to/saved_analyses
```

v1 kept only rounded strings, so these runs appear in the history with their results but can't be reopened in the workspace.

## How to use it

1. **Load data.** In the workspace, choose *Load data*:
   * **Google Sheet:** paste the link, list the tabs and pick the company. The sheet must be shared as "Anyone with the link: Viewer". The workbook is read as .xlsx, so numbers arrive typed (no locale guessing) and cell notes are read. A note containing `RANGO: 70% - 110%` becomes a suggested PERT distribution for that input.
   * **Excel file:** the same template as an uploaded workbook, for private sheets.
   * **Yahoo Finance:** price, TTM operating income (with R&D capitalised when it is material), effective tax rate, cash, debt, minorities and share count, each with its source and date.

   After an import from the template, the app checks that its base case reproduces the sheet's intrinsic value and tells you if it doesn't.
2. **Review the base case.** It recalculates as you type, with warnings for inconsistent inputs: the implied ROIC (g / reinvestment), terminal growth above Rf, a distribution not centred on its base value, draws that would be clipped, and so on.
3. **Describe uncertainty.** Click the shape next to any input. The advisor ranks a few distributions for that input, explains why, and previews each one.
4. **Run.** You get the probability that value exceeds price, the percentiles, and five views:
   * The **value field**: the full distribution against the price.
   * The **driver map**: a heat map of every simulated combination of two drivers.
   * **What moves value**: a tornado chart plus rank correlations.
   * **Cumulative**, **Cash flows** (fan chart), **Base case** (year-by-year table and equity bridge) and **Diagnostics** (convergence, dropped paths, clipped draws).
5. **Save to the register.** The company page charts every run (P10–P90 and median) over the price path, and can compare any two runs input by input. Each run can be exported as an Excel report.

## The model

All rates are decimals and money is in millions of the valuation currency. Every path is computed in one vectorised pass, and the deterministic base case runs through the same code, so the two never disagree.

```
NOPAT_0 = EBIT_0 (1 - t)                        no tax on losses unless enabled
NOPAT_t = NOPAT_{t-1} (1 + g_t)
FCFF_t  = NOPAT_t (1 - RR_t)                    RR_t = g_t / ROIC_t in ROIC-linked mode
TV_N    = NOPAT_N (1 + g_T)(1 - g_T/ROIC_T) / (WACC_T - g_T)     Gordon / Rf-linked
        = multiple x EBIT_N                                       exit multiple
EV      = sum FCFF_t / DF_t + TV_N / DF_N
Equity  = EV + cash + non-operating assets - debt - minorities - leases - pensions - options
```

| Choice | Options |
| --- | --- |
| Explicit period | Stage 1 and stage 2 lengths (default 5 + 5). Stage 2 uses its own inputs or fades linearly to terminal values. |
| Reinvestment | A direct rate per stage, or ROIC-linked (RR = g / ROIC, so every path stays internally consistent). |
| Discount rate | Direct WACC, or build-up from Rf, beta, ERP (plus a revenue-weighted country risk premium), the default spread and D/(D+E). |
| Terminal growth | g = Rf (Damodaran's cap), Gordon with its own g, or an exit EV/EBIT multiple. |
| Terminal WACC | A mature firm (Rf + β_T × ERP with optional terminal debt; β_T = 1 and no debt reproduce your template), a direct value, or the same as the explicit period. |
| Terminal ROIC | Equal to WACC (no excess returns), WACC + spread, or an absolute value. |
| Other | WACC fade over stage 2, mid-year discounting, probability of failure with distress proceeds (discrete risk). |

The engine is tested against your templates: the ASML example in the template gives 766.148 and the Alphabet tab gives 241.975 to the cent, in both direct and build-up WACC modes.

### Distributions

The available shapes are fixed, normal, truncated normal, shifted lognormal (floor or cap, so it can be right- or left-skewed), triangular, PERT, uniform, Student-t (fat tails), discrete and empirical (your own data). All of them are sampled through their inverse CDF, so correlations can be imposed between any mix of shapes with a Gaussian copula. Draws outside an input's logical bounds are clipped and reported. Paths whose terminal WACC is too close to terminal growth are dropped and counted, never allowed to blow up the mean.

The advisor follows Damodaran's simulation workflow: start from an expected-value base case; simulate only the few drivers that matter; choose shapes from history, then cross-sectional data, then a reasoned distribution; ask whether each input is discrete or continuous, symmetric or skewed, thin- or fat-tailed; model the correlations you know; and don't double-count risk. Sources are linked in the app ([Investment Valuation ch. 33](https://pages.stern.nyu.edu/~adamodar/pdfiles/val3ed/c33.pdf), [DCF Myth 3.2](https://aswathdamodaran.blogspot.com/2016/05/dcf-myth-32-if-you-don-look-its-not.html)).

## Hosting it for free

* **Your own computer:** `./run.sh`. The simplest option, and your data stays local.
* **Always on, free:** any small VM with Docker (for example Oracle Cloud's Always Free tier) running `docker compose up -d`, with `DCF_APP_PASSWORD` set and HTTPS in front (for example Caddy).
* **Free PaaS** (Render, Koyeb, Hugging Face Spaces with Docker): these usually wipe the disk on restart, so point `DCF_DATABASE_URL` at a free Postgres (for example Neon or Supabase free tier) and `pip install psycopg[binary]`.

| Variable | Meaning |
| --- | --- |
| `DCF_DATA_DIR` | Folder for the SQLite register (default `~/.dcfmc`) |
| `DCF_DATABASE_URL` | Any SQLAlchemy URL; overrides the SQLite file |
| `DCF_APP_PASSWORD` | Require a password (recommended when exposed to the internet) |
| `DCF_SECRET` | Signs the session cookie; set it to keep sessions across restarts |
| `DCF_STATIC_DIR` | Location of the built UI (set by the run scripts and Docker) |

## Development

```bash
cd backend && pip install -e .[dev] && pytest -q      # 80+ tests: engine, parser, importers, API, register
python -m dcfmc serve                                  # API on :8000, docs at /api/docs
cd frontend && npm install && npm run dev              # UI on :5173, proxied to the API
```

```
backend/dcfmc/core    parameters, distributions, advisor, inputs, engine, stats, validation
backend/dcfmc/io      number parser, template reader, Google Sheets / Excel, Yahoo Finance, Excel report
backend/dcfmc/store   SQLite register (SQLAlchemy), legacy importer
backend/dcfmc/api     FastAPI app (JSON API + static UI)
frontend/src          React app: register, company history, workspace, settings
legacy/               v1 Streamlit / Tkinter code, kept for reference
```
