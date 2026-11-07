"""Input checks: hard errors block a run, warnings and notes explain risks."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from .engine import base_case
from .inputs import ValuationInputs, active_parameters
from .parameters import PARAMETERS
from .units import Unit


@dataclass
class Issue:
    severity: str  # "error" | "warning" | "info"
    code: str
    message: str
    param: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


DERIVED = {"debt_weight"}  # computed from other inputs when left empty


def fmt(key: str, x: float | None) -> str:
    if x is None:
        return "n/a"
    u = PARAMETERS[key].unit
    if u in (Unit.PERCENT, Unit.PROBABILITY):
        return f"{x * 100:.2f}%"
    if u in (Unit.MONEY_M, Unit.SHARES_M):
        return f"{x:,.0f}m"
    if u == Unit.MULTIPLE:
        return f"{x:.1f}x"
    return f"{x:,.4g}"


def validate(inp: ValuationInputs) -> list[Issue]:
    issues: list[Issue] = []
    add = lambda *a, **k: issues.append(Issue(*a, **k))  # noqa: E731
    keys = active_parameters(inp)

    for key in keys:
        spec = PARAMETERS[key]
        b = inp.base(key)
        if b is None:
            if key in DERIVED:
                continue
            if spec.required or spec.default is None:
                add("error", "missing", f"{spec.label}: a base value is required.", key)
            continue
        if not np.isfinite(b):
            add("error", "not_finite", f"{spec.label}: value is not a number.", key)
            continue
        if not spec.allow_zero and b == 0:
            add("error", "zero", f"{spec.label} cannot be zero.", key)
        if spec.hard_min is not None and b < spec.hard_min:
            add("error", "below_min", f"{spec.label} = {fmt(key, b)} is below the minimum {fmt(key, spec.hard_min)}.", key)
        elif spec.hard_max is not None and b > spec.hard_max:
            add("error", "above_max", f"{spec.label} = {fmt(key, b)} is above the maximum {fmt(key, spec.hard_max)}.", key)
        elif spec.soft_min is not None and b < spec.soft_min:
            add("warning", "unusual_low", f"{spec.label} = {fmt(key, b)} is unusually low (typical >= {fmt(key, spec.soft_min)}).", key)
        elif spec.soft_max is not None and b > spec.soft_max:
            add("warning", "unusual_high", f"{spec.label} = {fmt(key, b)} is unusually high (typical <= {fmt(key, spec.soft_max)}).", key)

        p = inp.params.get(key)
        if p is not None and p.dist.is_random:
            u = (np.arange(4000) + 0.5) / 4000
            try:
                x = np.asarray(p.dist.ppf(u), dtype=float)
            except Exception as exc:  # pragma: no cover - defensive
                add("error", "bad_distribution", f"{spec.label}: distribution error ({exc}).", key)
                continue
            mean = float(x.mean())
            tol = max(0.1 * abs(b), 0.002 if spec.unit in (Unit.PERCENT, Unit.PROBABILITY) else 1e-9)
            if abs(mean - b) > tol:
                add("warning", "not_anchored",
                    f"{spec.label}: the distribution's mean ({fmt(key, mean)}) is far from the base value "
                    f"({fmt(key, b)}). Damodaran anchors the distribution on the base-case expectation.", key)
            lo = spec.hard_min if spec.hard_min is not None else -np.inf
            hi = spec.hard_max if spec.hard_max is not None else np.inf
            outside = float(np.mean((x < lo) | (x > hi)))
            if outside > 0.005:
                add("warning", "clipped",
                    f"{spec.label}: {outside:.1%} of draws fall outside the allowed range and will be "
                    "clipped. Use a bounded shape (truncated normal, PERT, triangular).", key)

    if inp.model.stage2_years == 0 and inp.model.stage2_mode == "fade":
        add("info", "no_stage2", "Stage 2 has 0 years, so there is nothing to fade.")

    # Correlations
    rnd = {k for k in keys if k in inp.params and inp.params[k].dist.is_random}
    for c in inp.simulation.correlations:
        if c.a not in rnd or c.b not in rnd:
            add("warning", "corr_unused",
                f"Correlation {c.a} ~ {c.b} is ignored: both inputs must be active and have a distribution.")
    cw = sum(c.weight for c in inp.country_risk)
    if inp.country_risk and abs(cw - 1) > 0.01:
        add("info", "crp_weights", f"Country-risk weights sum to {cw:.0%}; they are normalised to 100%.")

    if inp.terminal.method == "exit_multiple":
        add("info", "exit_multiple",
            "Exit multiple: Damodaran's warning applies; the terminal value becomes a relative "
            "valuation and hides growth, risk and return assumptions.")
    if inp.simulation.n < 5000:
        add("info", "few_paths", f"{inp.simulation.n:,} paths: tail percentiles will be noisy. 20,000+ is recommended.")

    if any(i.severity == "error" for i in issues):
        return issues

    # Economic consistency on the base case
    b = base_case(inp)
    m, t = inp.model, inp.terminal
    if (inp.base("ebit") or 0) <= 0:
        add("warning", "negative_ebit",
            "Base EBIT is zero or negative. Growing a loss makes it larger: use normalised "
            "(positive) EBIT or a revenue-and-margin model for turnarounds.", "ebit")
    if t.method in ("rf_linked", "gordon"):
        gT, wT = b["growth_terminal"], b["wacc_terminal"]
        if gT is not None and wT is not None and wT - gT <= inp.simulation.min_terminal_spread:
            add("error", "terminal_spread",
                f"Terminal WACC ({wT:.2%}) must exceed terminal growth ({gT:.2%}) by at least "
                f"{inp.simulation.min_terminal_spread:.2%}.", "terminal_growth")
        rf = inp.base("risk_free")
        if t.method == "gordon" and rf is not None and gT is not None and gT > rf + 1e-9:
            add("warning", "g_above_rf",
                f"Terminal growth ({gT:.2%}) is above the risk-free rate ({rf:.2%}). Damodaran caps "
                "stable growth at Rf.", "terminal_growth")
        rT = b["reinvestment_terminal"]
        if rT is not None and rT < 0:
            add("warning", "neg_terminal_rr", "Terminal reinvestment is negative: check terminal ROIC and growth.")
    if m.reinvestment_mode == "rate":
        for s, gk, rk in ((1, "growth_1", "reinvestment_1"), (2, "growth_2", "reinvestment_2")):
            if rk not in keys:
                continue
            g, rr = inp.base(gk), inp.base(rk)
            if g is None or rr is None:
                continue
            if g > 0 and rr <= 0:
                add("warning", "growth_free",
                    f"Stage {s}: {g:.1%} growth with {rr:.1%} reinvestment assumes growth for free.", rk)
            elif rr > 0:
                roic = g / rr
                if roic > 1.0 or roic < 0:
                    add("warning", "implied_roic",
                        f"Stage {s}: implied ROIC = g / RR = {roic:.0%}. Check that growth and "
                        "reinvestment are consistent, or switch to ROIC mode.", rk)
                else:
                    add("info", "implied_roic_ok", f"Stage {s}: implied return on new capital = {roic:.1%}.", rk)
    else:
        for s, gk, ck in ((1, "growth_1", "roic_1"), (2, "growth_2", "roic_2")):
            if ck not in keys:
                continue
            g, roic = inp.base(gk), inp.base(ck)
            if g is not None and roic:
                rr = g / roic
                if rr > 1.5:
                    add("warning", "implied_rr",
                        f"Stage {s}: implied reinvestment = g / ROIC = {rr:.0%} of NOPAT.", ck)
    if b["tv_share"] is not None and b["tv_share"] > 0.9:
        add("info", "tv_heavy",
            f"The terminal value is {b['tv_share']:.0%} of enterprise value. Common for growth "
            "firms; it means the terminal assumptions deserve the most scrutiny.")
    if b["value_per_share"] is not None and b["value_per_share"] < 0:
        add("warning", "negative_value", "Base-case equity value is negative.")
    return issues
