# Discounted Cash Flow (DCF) Monte Carlo Simulator

This repository contains a small Python application for performing Monte‑Carlo–based discounted cash flow analysis. It provides both a desktop interface using Tkinter and a web interface built with Streamlit.

## Repository Contents

- **`DCF_main.py`** – Core simulation logic. Defines `run_monte_carlo_simulation` which returns plots and a summary dictionary.
- **`DCF_GUI.py`** – Tkinter desktop interface that collects user inputs and displays results.
- **`DCF_streamlit.py`** – Streamlit web app version of the interface.
- **`.devcontainer/`** – Dev container configuration to run the Streamlit app automatically.
- **`requirements.txt`** – Python dependencies.

There were previously no README or tests in the project; this file documents the structure and usage.

## Core Simulation (`DCF_main.py`)

`run_monte_carlo_simulation` performs the DCF workflow. Parameters are passed as a dictionary, random values are drawn for growth rates and discount rates, and free cash flows are discounted. The function generates three Matplotlib figures and a valuation summary:

```python
fig_es, fig_distribution_only, fig_sensitivity, valuation_summary = run_monte_carlo_simulation(params)
```

The summary includes company name, date, value per share, and other statistics. All interfaces import this function.

## Desktop GUI (`DCF_GUI.py`)

The Tkinter application creates an extensive input form and embeds the main plot. It dynamically imports `DCF_main.py` and calls `run_monte_carlo_simulation` when the user presses the **Run Monte Carlo Simulation** button. The resulting figure appears inside the window.

## Streamlit App (`DCF_streamlit.py`)

The Streamlit interface mirrors the Tkinter inputs on the web. The dev container launches it automatically with:

```
streamlit run DCF_streamlit.py --server.enableCORS false --server.enableXsrfProtection false
```

After running the simulation, it renders the figures and a markdown valuation summary.

## Dev Container

`.devcontainer/devcontainer.json` sets up the environment, installs dependencies, and exposes port 8501. The app starts when you attach to the container, enabling immediate web usage.

## Learning Pointers

- **Understand the DCF computation** – Explore `run_monte_carlo_simulation` and how random variations drive the cash flow model.
- **Experiment with the interfaces** – The same simulation powers both the desktop and web versions.
- **Consider adding documentation** – This README now provides a starting point, but additional examples or screenshots could improve onboarding.
- **Potential improvements** – Unit tests or linting would help maintain the code as it grows.

## Running Tests

Currently the project does not provide any automated tests. Running `pytest` will report `no tests ran`.


