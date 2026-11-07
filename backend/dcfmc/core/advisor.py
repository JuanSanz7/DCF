"""Distribution advisor: suggests a shape and parameters for each input.

The logic follows the simulation workflow Damodaran describes (Investment
Valuation 3rd ed., ch. 33, and his 2016 "DCF Myth 3.2" post): start from the
base case, simulate only the few drivers that matter, choose the shape from
history, cross-sectional data or a reasoned statistical distribution, respect
bounds, keep the expected value anchored on the base case, and model the
correlations you know about.
"""
from __future__ import annotations

import math

import numpy as np

from .parameters import PARAMETERS

SOURCES = [
    {"title": "Damodaran, Investment Valuation (3rd ed.), ch. 33: Probabilistic Approaches",
     "url": "https://pages.stern.nyu.edu/~adamodar/pdfiles/val3ed/c33.pdf"},
    {"title": "Damodaran, DCF Myth 3.2: If you don't look, it's not there (2016)",
     "url": "https://aswathdamodaran.blogspot.com/2016/05/dcf-myth-32-if-you-don-look-its-not.html"},
    {"title": "Damodaran, Simulation in Valuation (slides)",
     "url": "https://pages.stern.nyu.edu/~adamodar/pdfiles/blog/Simulation.pdf"},
]

PRINCIPLES = [
    "Start from a base case built on expected values, not conservative ones; the simulated "
    "distribution should be centred on it.",
    "Simulate only the few inputs that move value (check the tornado); keep the rest fixed.",
    "Pick shapes from data first: the company's history, then the cross-section of peers, then "
    "a reasoned statistical distribution.",
    "Ask three questions for each input: discrete or continuous? symmetric or skewed? "
    "thin or fat tails? Then respect the logical bounds.",
    "Model the correlations you know (growth and margins, rates and risk premiums); "
    "independent draws can make the spread too narrow or too wide.",
    "Discount at the risk-adjusted rate and don't penalise the value spread again: that "
    "double counts risk. Use the spread to size your margin of safety.",
]


def _r(x: float, nd: int = 6) -> float:
    return float(round(x, nd))


def _sugg(dist: dict, title: str, why: str, recommended: bool = False) -> dict:
    return {"dist": dist, "title": title, "rationale": why, "recommended": recommended}


def suggest(key: str, base: float | None, low: float | None = None, high: float | None = None,
            history: list[float] | None = None, context: dict | None = None) -> dict:
    """Return ranked suggestions for one parameter."""
    spec = PARAMETERS[key]
    ctx = context or {}
    out: list[dict] = []
    vary = spec.stochastic_by_default
    hmin = spec.hard_min if spec.hard_min is not None else -math.inf
    hmax = spec.hard_max if spec.hard_max is not None else math.inf

    def clamp(x):
        return min(max(x, hmin), hmax)

    if base is None:
        return {"key": key, "vary": vary, "suggestions": [], "note": "Set a base value first."}

    # 1) Data you supplied wins.
    if history and len(history) >= 3:
        h = np.asarray(history, dtype=float)
        out.append(_sugg({"kind": "empirical", "values": h.tolist(), "smooth": True},
                         "Empirical from your data",
                         f"Resamples the {h.size} observations you provided, keeping their own "
                         "shape and skew. Assumes the past is representative of the future "
                         "(no structural break).", recommended=h.size >= 10))
        mu, sd = float(h.mean()), float(h.std(ddof=1))
        if sd > 0:
            out.append(_sugg({"kind": "normal", "mean": _r(base), "sd": _r(sd)},
                             "Normal with the data's volatility, centred on your base",
                             f"Uses the historical standard deviation ({sd:.4g}) but keeps the "
                             "expected value at your base case, as Damodaran recommends."))

    # 2) A researched range (e.g. 'RANGO: a - b' in the sheet notes).
    if low is not None and high is not None and low < high:
        lo, hi = min(low, base), max(high, base)
        skew = (hi - base) - (base - lo)
        shape = "right-skewed" if skew > 0.15 * (hi - lo) else "left-skewed" if skew < -0.15 * (hi - lo) else "roughly symmetric"
        out.append(_sugg({"kind": "pert", "low": _r(lo), "mode": _r(base), "high": _r(hi), "lam": 4},
                         "PERT on your researched range",
                         f"Your range is {shape} around the base case. PERT keeps every draw "
                         "inside it and puts most weight near the most likely value; a "
                         "smoother, less tail-heavy cousin of the triangular.",
                         recommended=not out or not out[0]["recommended"]))
        out.append(_sugg({"kind": "triangular", "low": _r(lo), "mode": _r(base), "high": _r(hi)},
                         "Triangular on your range",
                         "Same bounds with more weight in the tails than PERT. Damodaran used a "
                         "triangular for Apple's operating margin."))

    cat = spec.category
    b = base
    if cat == "growth":
        s = max(0.25 * abs(b), 0.02)
        floor = clamp(b - 2.0 * s)
        out.append(_sugg({"kind": "lognormal", "mean": _r(b), "sd": _r(s), "bound": _r(floor), "side": "lower"},
                         "Lognormal with a floor (right skew)",
                         "Growth is usually positively skewed: modest outcomes are common, a "
                         "breakout is rare but possible, and the downside has a floor. Damodaran "
                         "used a lognormal for Apple's revenue growth.", recommended=not out))
        out.append(_sugg({"kind": "truncnormal", "mean": _r(b), "sd": _r(s), "low": _r(clamp(b - 3 * s)), "high": _r(clamp(b + 3 * s))},
                         "Truncated normal (symmetric)",
                         "If you have no view on skew. Truncation stops impossible tails."))
    elif cat == "reinvestment":
        s = max(0.12 * abs(b), 0.05)
        out.append(_sugg({"kind": "truncnormal", "mean": _r(b), "sd": _r(s), "low": _r(max(0.0, b - 3 * s)), "high": _r(min(1.5, b + 3 * s))},
                         "Truncated normal within [0, 150%]",
                         "Reinvestment has a floor (maintenance) and a ceiling (funding). Better: "
                         "switch to ROIC mode so reinvestment follows growth on every path.",
                         recommended=not out))
        out.append(_sugg({"kind": "pert", "low": _r(max(0.0, b - 2.5 * s)), "mode": _r(b), "high": _r(min(1.5, b + 2.5 * s)), "lam": 4},
                         "PERT within a plausible band", "Bounded and peaked at your base case."))
    elif cat == "roic":
        s = max(0.25 * b, 0.02)
        out.append(_sugg({"kind": "lognormal", "mean": _r(b), "sd": _r(s), "bound": 0.0, "side": "lower"},
                         "Lognormal (positive, right-skewed)",
                         "Returns on capital are positive and right-skewed: a few businesses earn "
                         "very high returns, most converge toward the cost of capital.",
                         recommended=not out))
    elif cat == "risk_free":
        out.append(_sugg({"kind": "truncnormal", "mean": _r(b), "sd": 0.005, "low": _r(max(-0.01, b - 0.025)), "high": _r(b + 0.025)},
                         "Truncated normal, sd 0.5 pp",
                         "Long-term yields move by fractions of a percentage point over the months "
                         "a valuation is used. Because Rf drives the WACC, the terminal growth and "
                         "the terminal WACC at the same time, the effects partly offset.",
                         recommended=not out))
    elif cat == "erp":
        out.append(_sugg({"kind": "truncnormal", "mean": _r(b), "sd": 0.005, "low": _r(max(0.02, b - 0.02)), "high": _r(b + 0.03)},
                         "Truncated normal, sd 0.5 pp, floor 2%",
                         "Damodaran's monthly implied ERP for the S&P 500 changes slowly and stays "
                         "well above zero; the floor protects the terminal value, whose "
                         "denominator is roughly ERP in the Rf-linked method.", recommended=not out))
    elif cat == "beta":
        out.append(_sugg({"kind": "truncnormal", "mean": _r(b), "sd": 0.12, "low": _r(max(0.3, b - 0.5)), "high": _r(b + 0.6)},
                         "Truncated normal, sd ~0.12",
                         "Regression betas have standard errors of 0.1-0.3; bottom-up betas "
                         "(averaged across many firms) are more precise, so ~0.1 is a fair spread.",
                         recommended=not out))
    elif cat == "tax":
        marginal = ctx.get("marginal_tax", 0.25)
        hi = max(b + 0.02, marginal)
        out.append(_sugg({"kind": "pert", "low": _r(max(0.0, b - 0.03)), "mode": _r(b), "high": _r(hi), "lam": 4},
                         "PERT skewed toward the marginal rate",
                         "Effective rates tend to drift up to the statutory (marginal) rate as "
                         "deferrals and incentives expire, so the risk is skewed upward.",
                         recommended=not out))
    elif cat == "operating_base":
        s = 0.05 * abs(b)
        out.append(_sugg({"kind": "normal", "mean": _r(b, 2), "sd": _r(s, 2)},
                         "Normal, sd 5% of base",
                         "Captures uncertainty about 'normalised' earnings (one-offs, R&D "
                         "capitalisation). Keep fixed if the base is clean.", recommended=False))
    elif cat == "wacc":
        out.append(_sugg({"kind": "truncnormal", "mean": _r(b), "sd": 0.0075, "low": _r(max(0.02, b - 0.03)), "high": _r(b + 0.03)},
                         "Truncated normal, sd 0.75 pp",
                         "Prefer the build-up mode: simulating Rf, ERP and beta keeps the explicit "
                         "and terminal discount rates consistent.", recommended=not out))
    elif cat == "terminal_growth":
        out.append(_sugg({"kind": "fixed"}, "Keep fixed (or use the Rf-linked method)",
                         "Damodaran caps stable growth at the risk-free rate. Linking g to Rf keeps "
                         "it consistent with the discount rate on every path.", recommended=not out))
    elif cat == "multiple":
        out.append(_sugg({"kind": "lognormal", "mean": _r(b), "sd": _r(0.25 * b), "bound": 0.0, "side": "lower"},
                         "Lognormal (positive, right-skewed)",
                         "Multiples are positive and right-skewed across peers.", recommended=not out))
    elif cat == "nonop":
        out.append(_sugg({"kind": "pert", "low": _r(0.5 * b, 2), "mode": _r(b, 2), "high": _r(1.1 * b, 2), "lam": 4},
                         "PERT with a long downside",
                         "Private stakes carried at fair value from funding rounds are illiquid and "
                         "volatile: the downside is longer than the upside. If you believe a haircut "
                         "applies on average, lower the base value itself so the distribution stays "
                         "anchored on your expectation.",
                         recommended=not out))
    if not any(s["dist"]["kind"] == "fixed" for s in out):
        out.append(_sugg({"kind": "fixed"}, "Keep fixed",
                         "Fine for inputs you know well or that barely move value.",
                         recommended=not out or not vary))
    if not any(s["recommended"] for s in out):
        out[0]["recommended"] = True
    out.sort(key=lambda s: not s["recommended"])
    return {"key": key, "vary": vary, "suggestions": out}


def recommended_dist(key: str, base: float | None, low: float | None = None,
                     high: float | None = None) -> dict:
    res = suggest(key, base, low, high)
    return res["suggestions"][0]["dist"] if res["suggestions"] else {"kind": "fixed"}
