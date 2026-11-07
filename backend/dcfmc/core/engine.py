"""Vectorised FCFF Monte Carlo engine.

One call values every path at once with NumPy arrays of shape (n,) for inputs
and (n, N) for yearly quantities. The deterministic base case is the same code
run on a single path of base values, so the two can never disagree.

Model (per path):
    NOPAT_0  = EBIT_0 x (1 - t)                    (no tax on losses unless enabled)
    NOPAT_t  = NOPAT_{t-1} x (1 + g_t)
    FCFF_t   = NOPAT_t x (1 - RR_t),  RR_t = g_t / ROIC_t in ROIC mode
    TV_N     = NOPAT_N (1 + g_T)(1 - g_T / ROIC_T) / (WACC_T - g_T)   (Gordon)
             = multiple x EBIT_N                                       (exit multiple)
    EV       = sum FCFF_t / DF_t + TV_N / DF_N
    Equity   = EV + cash + non-operating - debt - minorities - leases - pensions - options
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import stats

from .inputs import ValuationInputs, active_parameters
from .parameters import PARAMETERS

ENGINE_VERSION = "2.0.0"


@dataclass
class Draws:
    values: dict[str, np.ndarray]
    random_keys: list[str]
    clipped: dict[str, float] = field(default_factory=dict)
    corr_adjusted: bool = False
    u_fail: np.ndarray | None = None


def _nearest_psd_corr(c: np.ndarray) -> tuple[np.ndarray, bool]:
    w, v = np.linalg.eigh(c)
    if np.min(w) > 1e-10:
        return c, False
    w = np.clip(w, 1e-8, None)
    c2 = v @ np.diag(w) @ v.T
    d = np.sqrt(np.diag(c2))
    c2 = c2 / np.outer(d, d)
    np.fill_diagonal(c2, 1.0)
    return c2, True


def draw(inp: ValuationInputs, n: int, rng: np.random.Generator) -> Draws:
    keys = active_parameters(inp)
    random_keys = [k for k in keys if k in inp.params and inp.params[k].dist.is_random]
    k = len(random_keys)
    corr_adjusted = False
    if k:
        corr = np.eye(k)
        idx = {key: i for i, key in enumerate(random_keys)}
        has_corr = False
        for c in inp.simulation.correlations:
            if c.a in idx and c.b in idx and c.a != c.b:
                corr[idx[c.a], idx[c.b]] = corr[idx[c.b], idx[c.a]] = c.rho
                has_corr = True
        if has_corr:
            corr, corr_adjusted = _nearest_psd_corr(corr)
            z = rng.standard_normal((n, k)) @ np.linalg.cholesky(corr).T
            u = stats.norm.cdf(z)
        else:
            u = rng.random((n, k))
        u = np.clip(u, 1e-12, 1 - 1e-12)

    values: dict[str, np.ndarray] = {}
    clipped: dict[str, float] = {}
    for key in keys:
        spec = PARAMETERS[key]
        if key in random_keys:
            x = np.asarray(inp.params[key].dist.ppf(u[:, random_keys.index(key)]), dtype=float)
            lo = -np.inf if spec.hard_min is None else spec.hard_min
            hi = np.inf if spec.hard_max is None else spec.hard_max
            out = (x < lo) | (x > hi)
            if out.any():
                clipped[key] = float(out.mean())
                x = np.clip(x, lo, hi)
            values[key] = x
        else:
            b = inp.base(key)
            values[key] = np.full(n, np.nan if b is None else float(b))
    u_fail = rng.random(n) if "failure_probability" in keys else None
    return Draws(values, random_keys, clipped, corr_adjusted, u_fail)


def base_draws(inp: ValuationInputs) -> Draws:
    keys = active_parameters(inp)
    vals = {}
    for k in keys:
        b = inp.base(k)
        vals[k] = np.array([np.nan if b is None else float(b)])
    return Draws(vals, [], {}, False, None)


def value_paths(inp: ValuationInputs, d: Draws, detail: bool = False) -> dict[str, np.ndarray]:
    P = d.values
    m, t = inp.model, inp.terminal
    n = len(P["price"])
    N1, N2 = m.stage1_years, m.stage2_years
    N = N1 + N2
    crp = inp.crp_weighted

    tax = P["tax_rate"]
    ebit0 = P["ebit"]
    nopat0 = ebit0 * (1 - tax) if m.tax_on_losses else np.where(ebit0 > 0, ebit0 * (1 - tax), ebit0)

    # ---------------------------------------------------------- discount rates
    rf = P.get("risk_free")
    erp_tot = P["erp"] + crp if "erp" in P else None
    if m.discount_mode == "direct":
        wacc = P["wacc"]
    else:
        dw = P["debt_weight"]
        ke = rf + P["beta"] * erp_tot
        kd = rf + P["default_spread"]
        wacc = ke * (1 - dw) + kd * (1 - tax) * dw

    # ---------------------------------------------------------- terminal inputs
    gordon = t.method in ("rf_linked", "gordon")
    if t.method == "rf_linked":
        g_T = rf.copy()
    elif "terminal_growth" in P:
        g_T = P["terminal_growth"]
    else:
        g_T = np.full(n, np.nan)

    if gordon:
        if t.wacc_source == "market":
            dT = P["terminal_debt_weight"]
            keT = rf + P["terminal_beta"] * erp_tot
            spread = P["default_spread"] if "default_spread" in P else np.zeros(n)
            wacc_T = keT * (1 - dT) + (rf + spread) * (1 - tax) * dT
        elif t.wacc_source == "direct":
            wacc_T = P["terminal_wacc"]
        else:
            wacc_T = wacc.copy()
        if t.roic_mode == "equal_wacc":
            roic_T = wacc_T.copy()
        elif t.roic_mode == "spread":
            roic_T = wacc_T + P["terminal_roic_spread"]
        else:
            roic_T = P["terminal_roic"]
    else:
        wacc_T = wacc.copy()
        roic_T = wacc.copy()
    rr_T = np.divide(g_T, roic_T, out=np.zeros(n), where=roic_T != 0)

    # ---------------------------------------------------------- yearly arrays
    frac = (np.arange(1, N2 + 1) / N2) if N2 else np.zeros(0)
    g = np.empty((n, N))
    g[:, :N1] = P["growth_1"][:, None]
    if N2:
        if m.stage2_mode == "flat":
            g[:, N1:] = P["growth_2"][:, None]
        else:
            g[:, N1:] = P["growth_1"][:, None] + (g_T - P["growth_1"])[:, None] * frac
    if m.reinvestment_mode == "rate":
        rr = np.empty((n, N))
        rr[:, :N1] = P["reinvestment_1"][:, None]
        if N2:
            if m.stage2_mode == "flat":
                rr[:, N1:] = P["reinvestment_2"][:, None]
            else:
                rr[:, N1:] = P["reinvestment_1"][:, None] + (rr_T - P["reinvestment_1"])[:, None] * frac
        roic = np.divide(g, rr, out=np.full((n, N), np.nan), where=rr != 0)
    else:
        roic = np.empty((n, N))
        roic[:, :N1] = P["roic_1"][:, None]
        if N2:
            if m.stage2_mode == "flat":
                roic[:, N1:] = P["roic_2"][:, None]
            else:
                roic[:, N1:] = P["roic_1"][:, None] + (roic_T - P["roic_1"])[:, None] * frac
        rr = g / roic

    nopat = nopat0[:, None] * np.cumprod(1 + g, axis=1)
    fcff = nopat * (1 - rr)

    w = np.repeat(wacc[:, None], N, axis=1)
    if m.wacc_fade and N2 and gordon:
        w[:, N1:] = wacc[:, None] + (wacc_T - wacc)[:, None] * frac
    df_end = np.cumprod(1 + w, axis=1)
    df_flow = df_end / np.sqrt(1 + w) if m.mid_year else df_end
    pv_fcff_t = fcff / df_flow
    pv_fcff = pv_fcff_t.sum(axis=1)

    if gordon:
        nopat_T1 = nopat[:, -1] * (1 + g_T)
        fcff_T1 = nopat_T1 * (1 - rr_T)
        tv = fcff_T1 / (wacc_T - g_T)
    else:
        ebit_N = np.where(1 - tax > 1e-9, nopat[:, -1] / (1 - tax), nopat[:, -1])
        tv = P["exit_multiple"] * ebit_N
        fcff_T1 = np.full(n, np.nan)
    pv_tv = tv / df_end[:, -1]
    ev = pv_fcff + pv_tv

    claims = (P["debt"] + P["minority_interests"] + P["lease_liabilities"]
              + P["pension_deficit"] + P["options_value"])
    extra = P["cash"] + P["non_operating_assets"]
    equity_gc = ev + extra - claims

    p_fail = P["failure_probability"]
    if "distress_proceeds" in P:
        equity_distress = np.maximum(P["distress_proceeds"] * ev + extra - claims, 0.0)
    else:
        equity_distress = np.zeros(n)
    if d.u_fail is not None:
        failed = d.u_fail < p_fail
        equity = np.where(failed, equity_distress, equity_gc)
    else:  # deterministic: expected value of the two states
        failed = np.zeros(n, dtype=bool)
        equity = (1 - p_fail) * equity_gc + p_fail * equity_distress

    vps = equity / P["shares"]
    valid = np.isfinite(vps) & np.isfinite(ev)
    if gordon:
        valid &= (wacc_T - g_T) > inp.simulation.min_terminal_spread
    valid &= wacc > -0.99

    out = {
        "value_per_share": vps,
        "equity": equity,
        "ev": ev,
        "pv_fcff": pv_fcff,
        "pv_tv": pv_tv,
        "tv": tv,
        "tv_share": np.divide(pv_tv, ev, out=np.full(n, np.nan), where=ev != 0),
        "wacc": wacc,
        "wacc_terminal": wacc_T,
        "growth_terminal": g_T,
        "roic_terminal": roic_T,
        "reinvestment_terminal": rr_T,
        "failed": failed,
        "valid": valid,
        "fcff": fcff,
        "nopat": nopat,
    }
    if detail:
        out.update({
            "nopat0": nopat0, "growth": g, "reinvestment": rr, "roic": roic, "wacc_path": w,
            "df": df_flow, "pv_fcff_t": pv_fcff_t, "fcff_T1": fcff_T1, "cash_extra": extra,
            "claims": claims, "equity_going_concern": equity_gc, "equity_distress": equity_distress,
            "erp_total": erp_tot if erp_tot is not None else np.full(n, np.nan),
        })
    return out


def base_case(inp: ValuationInputs) -> dict:
    """Deterministic valuation with every input at its base value."""
    d = base_draws(inp)
    r = value_paths(inp, d, detail=True)
    N = inp.model.stage1_years + inp.model.stage2_years
    years = list(range(1, N + 1))

    def s(a):
        v = float(np.asarray(a).reshape(-1)[0])
        return v if np.isfinite(v) else None

    def row(a):
        return [float(x) for x in np.asarray(a)[0]]

    table = {
        "year": years,
        "growth": row(r["growth"]),
        "nopat": row(r["nopat"]),
        "reinvestment": row(r["reinvestment"]),
        "roic": row(r["roic"]),
        "fcff": row(r["fcff"]),
        "wacc": row(r["wacc_path"]),
        "discount_factor": row(r["df"]),
        "pv_fcff": row(r["pv_fcff_t"]),
    }
    price = inp.base("price")
    vps = s(r["value_per_share"])
    return {
        "value_per_share": vps,
        "price": price,
        "upside": (vps / price - 1) if (vps is not None and price) else None,
        "nopat0": s(r["nopat0"]),
        "ev": s(r["ev"]),
        "pv_fcff": s(r["pv_fcff"]),
        "tv": s(r["tv"]),
        "pv_tv": s(r["pv_tv"]),
        "tv_share": s(r["tv_share"]),
        "equity": s(r["equity"]),
        "equity_going_concern": s(r["equity_going_concern"]),
        "wacc": s(r["wacc"]),
        "wacc_terminal": s(r["wacc_terminal"]),
        "growth_terminal": s(r["growth_terminal"]),
        "roic_terminal": s(r["roic_terminal"]),
        "reinvestment_terminal": s(r["reinvestment_terminal"]),
        "fcff_terminal": s(r["fcff_T1"]),
        "erp_total": s(r["erp_total"]),
        "valid": bool(r["valid"][0]),
        "table": table,
        "bridge": {
            "ev": s(r["ev"]),
            "cash": inp.base("cash"),
            "non_operating_assets": inp.base("non_operating_assets"),
            "debt": inp.base("debt"),
            "minority_interests": inp.base("minority_interests"),
            "lease_liabilities": inp.base("lease_liabilities"),
            "pension_deficit": inp.base("pension_deficit"),
            "options_value": inp.base("options_value"),
            "equity": s(r["equity"]),
            "shares": inp.base("shares"),
        },
    }


@dataclass
class SimulationOutput:
    inputs: ValuationInputs
    draws: Draws
    paths: dict[str, np.ndarray]
    valid: np.ndarray
    seed: int
    base: dict


def simulate(inp: ValuationInputs) -> SimulationOutput:
    seed = inp.simulation.seed
    if seed is None:
        seed = int(np.random.SeedSequence().entropy % (2**31 - 1))
    rng = np.random.default_rng(seed)
    d = draw(inp, inp.simulation.n, rng)
    paths = value_paths(inp, d)
    return SimulationOutput(inp, d, paths, paths["valid"], seed, base_case(inp))
