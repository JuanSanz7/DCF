# Value field: DCF Monte Carlo

A personal intrinsic-valuation workbench. You set the inputs of a Damodaran-style FCFF model, give each uncertain input a probability distribution (with an advisor that suggests one), simulate tens of thousands of futures, and see the whole field of plausible values against the market price. Every run is saved to a register with its complete inputs, so you can follow a company's valuation over time and see what changed.

Everything is open source and free: Python (FastAPI, NumPy, SciPy, SQLAlchemy), React with Vite, Tailwind and Apache ECharts, and SQLite. There are no paid services or subscriptions.

## Using it

Open the app's link in any browser, create an account, and start valuing. Each account has its own private register, so you can share the link with friends: they create their own accounts and see only their own valuations.

### Putting it online (once, from the browser, free)

The app runs as a free [Render](https://render.com) web service built from this repository, and the register lives in a free [Neon](https://neon.tech) Postgres database, so it survives restarts. Every push redeploys automatically.

1. **Database.** In Neon, open your project → **Connect**, and copy the connection string (`postgresql://…`).
2. **Render.** Sign up at render.com with your GitHub account and allow it to see this repository. Then choose **New → Blueprint**, pick the repository, and paste the connection string into `DCF_DATABASE_URL`. `DCF_INVITE_CODE` is optional: if you set it, people need that code to create an account. Click **Apply**.
3. After the first build (about 5–10 minutes) the app is at `https://value-field.onrender.com` (or the address Render shows). Share that link.

Free Render services sleep after 15 minutes without visitors; the next visit wakes them in about a minute. The data is safe in Neon either way. The free instance has 512 MB of memory, so runs are capped at 200,000 paths there.

### Running it on your own computer (optional)

With Python 3.10+ and Node 18+: `./run.sh` (macOS/Linux) or `run.bat` (Windows), or `docker compose up --build`. It opens http://127.0.0.1:8000.

### Bringing in v1 valuations

In the old Streamlit app, download the ZIP from "Export / Import Analyses", then upload it in House assumptions → "Bring in valuations from the first version". v1 kept only rounded results, so these runs appear in each company's history but can't be reopened in the workspace.

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

## Configuration

| Variable | Meaning |
| --- | --- |
| `DCF_DATABASE_URL` | Postgres connection string (Neon, Supabase…) or any SQLAlchemy URL. Without it a SQLite file is used, which free hosts wipe on restart (the app shows a warning). |
| `DCF_INVITE_CODE` | If set, new accounts need this code |
| `DCF_SIGNUP` | `closed` stops new sign-ups entirely |
| `DCF_DATA_DIR` | Folder for the SQLite file when no database URL is set (default `~/.dcfmc`) |
| `DCF_SECRET` | Signs session cookies; generated and stored in the database if not set |

## Development

```bash
cd backend && pip install -e .[dev] && pytest -q      # 86 tests: engine, parser, importers, API, accounts, register
python -m dcfmc serve                                  # API on :8000, docs at /api/docs
cd frontend && npm install && npm run dev              # UI on :5173, proxied to the API
```

```
backend/dcfmc/core    parameters, distributions, advisor, inputs, engine, stats, validation
backend/dcfmc/io      number parser, template reader, Google Sheets / Excel, Yahoo Finance, Excel report
backend/dcfmc/store   register (SQLAlchemy: SQLite or Postgres), user accounts, legacy importer
backend/dcfmc/api     FastAPI app (JSON API + static UI)
frontend/src          React app: register, company history, workspace, settings
deploy/               Hugging Face deployment script (run by .github/workflows/deploy.yml)
legacy/               v1 Streamlit / Tkinter code, kept for reference
```
