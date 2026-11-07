"""Statistics and chart-ready summaries of a simulation."""
from __future__ import annotations

import numpy as np
from scipy import stats as sps

from .engine import Draws, SimulationOutput, base_draws, value_paths
from .parameters import PARAMETERS

PCTS = [1, 5, 10, 20, 25, 50, 75, 80, 90, 95, 99]


def _f(x) -> float | None:
    x = float(x)
    return x if np.isfinite(x) else None


def _pct(a: np.ndarray) -> dict[str, float | None]:
    if a.size == 0:
        return {f"p{p}": None for p in PCTS}
    vals = np.percentile(a, PCTS)
    return {f"p{p}": _f(v) for p, v in zip(PCTS, vals)}


def histogram(v: np.ndarray, bins: int = 70) -> dict:
    lo, hi = np.percentile(v, [0.5, 99.5])
    if hi - lo <= 1e-12:
        lo, hi = lo - 0.5, hi + 0.5
    counts, edges = np.histogram(v, bins=bins, range=(lo, hi))
    return {
        "edges": edges.tolist(),
        "counts": counts.tolist(),
        "below": int((v < lo).sum()),
        "above": int((v > hi).sum()),
        "total": int(v.size),
    }


def ecdf(v: np.ndarray, points: int = 101) -> dict:
    q = np.linspace(0, 1, points)
    return {"q": q.tolist(), "x": np.quantile(v, q).tolist()}


def convergence(v: np.ndarray, checkpoints: int = 40) -> dict:
    n = v.size
    if n < 50:
        return {"n": [], "mean": [], "median": [], "lo": [], "hi": []}
    ns = np.unique(np.geomspace(50, n, checkpoints).astype(int))
    ns = ns[ns <= n]
    cs = np.cumsum(v)
    mean = cs[ns - 1] / ns
    med = [float(np.median(v[:k])) for k in ns]
    sd = [float(np.std(v[:k], ddof=1)) for k in ns]
    sem = np.asarray(sd) / np.sqrt(ns)
    return {"n": ns.tolist(), "mean": mean.tolist(), "median": med,
            "lo": (mean - 1.96 * sem).tolist(), "hi": (mean + 1.96 * sem).tolist()}


def sensitivity(out: SimulationOutput, v: np.ndarray, mask: np.ndarray) -> list[dict]:
    res = []
    for key in out.draws.random_keys:
        x = out.draws.values[key][mask]
        if np.ptp(x) <= 0:
            continue
        rho = sps.spearmanr(x, v).statistic
        res.append({"key": key, "label": PARAMETERS[key].label, "rho": _f(rho)})
    tot = sum((r["rho"] or 0) ** 2 for r in res) or 1.0
    for r in res:
        r["contribution"] = (r["rho"] or 0) ** 2 / tot
    return sorted(res, key=lambda r: -abs(r["rho"] or 0))


def tornado(out: SimulationOutput, lo_q: float = 10, hi_q: float = 90) -> list[dict]:
    """One-at-a-time swing: each random input at its own P10 / P90, others at base."""
    inp = out.inputs
    keys = out.draws.random_keys
    if not keys:
        return []
    base = base_draws(inp)
    rows = 2 * len(keys)
    vals = {k: np.repeat(a, rows) for k, a in base.values.items()}
    lows, highs = {}, {}
    for i, key in enumerate(keys):
        lo, hi = np.percentile(out.draws.values[key], [lo_q, hi_q])
        vals[key][2 * i] = lo
        vals[key][2 * i + 1] = hi
        lows[key], highs[key] = lo, hi
    r = value_paths(inp, Draws(vals, [], {}, False, None))
    vps = r["value_per_share"]
    base_v = out.base["value_per_share"]
    res = []
    for i, key in enumerate(keys):
        a, b = _f(vps[2 * i]), _f(vps[2 * i + 1])
        res.append({
            "key": key, "label": PARAMETERS[key].label, "unit": PARAMETERS[key].unit.value,
            "input_low": _f(lows[key]), "input_high": _f(highs[key]),
            "value_low": a, "value_high": b, "base": base_v,
            "swing": abs((b or 0) - (a or 0)),
        })
    return sorted(res, key=lambda r: -r["swing"])


def heatmap(x: np.ndarray, y: np.ndarray, v: np.ndarray, price: float | None, bins: int = 10) -> dict:
    """Median value and P(value > price) on a quantile grid of two drivers."""
    qx = np.unique(np.quantile(x, np.linspace(0, 1, bins + 1)))
    qy = np.unique(np.quantile(y, np.linspace(0, 1, bins + 1)))
    if qx.size < 3 or qy.size < 3:
        return {}
    ix = np.clip(np.searchsorted(qx, x, side="right") - 1, 0, qx.size - 2)
    iy = np.clip(np.searchsorted(qy, y, side="right") - 1, 0, qy.size - 2)
    nx, ny = qx.size - 1, qy.size - 1
    med = np.full((ny, nx), np.nan)
    prob = np.full((ny, nx), np.nan)
    cnt = np.zeros((ny, nx), dtype=int)
    order = np.lexsort((ix, iy))
    keys = iy[order] * nx + ix[order]
    splits = np.flatnonzero(np.diff(keys)) + 1
    for grp in np.split(order, splits):
        if grp.size == 0:
            continue
        j, i = iy[grp[0]], ix[grp[0]]
        vv = v[grp]
        med[j, i] = np.median(vv)
        cnt[j, i] = vv.size
        if price:
            prob[j, i] = np.mean(vv > price)
    centers_x = (0.5 * (qx[:-1] + qx[1:])).tolist()
    centers_y = (0.5 * (qy[:-1] + qy[1:])).tolist()
    clean = lambda a: [[_f(z) for z in r] for r in a]  # noqa: E731
    return {"x_edges": qx.tolist(), "y_edges": qy.tolist(), "x": centers_x, "y": centers_y,
            "median": clean(med), "prob_above_price": clean(prob) if price else None,
            "count": cnt.tolist()}


def summarize(out: SimulationOutput, sample_points: int = 2500) -> dict:
    inp = out.inputs
    price = inp.base("price")
    vps = out.paths["value_per_share"]
    mask = out.valid
    v = vps[mask]
    n_total = vps.size
    n_valid = int(v.size)
    res: dict = {
        "n": n_total,
        "n_valid": n_valid,
        "invalid_fraction": 1 - n_valid / n_total if n_total else 0.0,
        "failed_fraction": float(out.paths["failed"][mask].mean()) if n_valid else 0.0,
        "seed": out.seed,
        "clipped": out.draws.clipped,
        "correlation_adjusted": out.draws.corr_adjusted,
        "random_keys": out.draws.random_keys,
        "base": out.base,
        "price": price,
    }
    if n_valid == 0:
        return res
    mean = float(v.mean())
    sd = float(v.std(ddof=1)) if n_valid > 1 else 0.0
    k5 = np.percentile(v, 5)
    res.update({
        "mean": mean,
        "median": float(np.median(v)),
        "sd": sd,
        "sem": sd / np.sqrt(n_valid),
        "skew": _f(sps.skew(v)) if n_valid > 2 else None,
        "percentiles": _pct(v),
        "cvar5": float(v[v <= k5].mean()),
        "prob_above_price": float(np.mean(v > price)) if price else None,
        "upside_median": float(np.median(v) / price - 1) if price else None,
        "upside_mean": mean / price - 1 if price else None,
        "histogram": histogram(v),
        "ecdf": ecdf(v),
        "convergence": convergence(v),
        "tv_share": _pct(out.paths["tv_share"][mask]),
        "ev": _pct(out.paths["ev"][mask]),
        "wacc": _pct(out.paths["wacc"][mask]),
        "wacc_terminal": _pct(out.paths["wacc_terminal"][mask]),
        "growth_terminal": _pct(out.paths["growth_terminal"][mask]),
    })
    fcff = out.paths["fcff"][mask]
    res["fan"] = {
        "year": list(range(1, fcff.shape[1] + 1)),
        **{f"p{p}": np.percentile(fcff, p, axis=0).tolist() for p in (5, 25, 50, 75, 95)},
        "base": out.base["table"]["fcff"],
        "mean": fcff.mean(axis=0).tolist(),
        "sd": fcff.std(axis=0).tolist(),
    }
    res["sensitivity"] = sensitivity(out, v, mask)
    res["tornado"] = tornado(out)
    # input summaries (what was actually simulated)
    res["inputs"] = {
        k: {"label": PARAMETERS[k].label, "unit": PARAMETERS[k].unit.value,
            "mean": float(out.draws.values[k].mean()), "sd": float(out.draws.values[k].std()),
            **_pct(out.draws.values[k])}
        for k in out.draws.random_keys
    }
    # down-sampled joint sample for the explorer (scatter of value vs any driver)
    rng = np.random.default_rng(0)
    idx = np.flatnonzero(mask)
    if idx.size > sample_points:
        idx = np.sort(rng.choice(idx, sample_points, replace=False))
    res["sample"] = {
        "value": vps[idx].tolist(),
        **{k: out.draws.values[k][idx].tolist() for k in out.draws.random_keys},
    }
    # heatmaps for the strongest driver pairs
    top = [s["key"] for s in res["sensitivity"][:3]]
    maps = []
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            a, b = top[i], top[j]
            hm = heatmap(out.draws.values[a][mask], out.draws.values[b][mask], v, price)
            if hm:
                maps.append({"x_key": a, "y_key": b, **hm})
    res["heatmaps"] = maps
    return res


def explore(out: SimulationOutput, x_key: str, y_key: str, bins: int = 12) -> dict:
    mask = out.valid
    v = out.paths["value_per_share"][mask]
    def arr(k):
        if k in out.draws.values:
            return out.draws.values[k][mask]
        if k in out.paths and out.paths[k].ndim == 1:
            return out.paths[k][mask]
        raise KeyError(k)
    return {"x_key": x_key, "y_key": y_key,
            **heatmap(arr(x_key), arr(y_key), v, out.inputs.base("price"), bins=bins)}
