"""Read/write helpers for the valuation register."""
from __future__ import annotations

import json
import re
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import delete, func, select

from ..core.engine import ENGINE_VERSION, SimulationOutput
from .db import Company, PriceCache, Store, Valuation, ValuationResult, pack_sample, unpack_sample

MAX_STORED_PATHS = 100_000


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def valuation_row(v: Valuation) -> dict:
    return {
        "id": v.id, "ticker": v.company.ticker, "name": v.company.name, "created_at": _iso(v.created_at),
        "label": v.label, "notes": v.notes, "source": v.source, "engine_version": v.engine_version,
        "seed": v.seed, "n_paths": v.n_paths, "currency": v.currency, "price": v.price,
        "base_value": v.base_value, "mean": v.mean, "median": v.median, "sd": v.sd,
        "p5": v.p5, "p10": v.p10, "p25": v.p25, "p75": v.p75, "p90": v.p90, "p95": v.p95,
        "prob_above_price": v.prob_above_price, "tv_share": v.tv_share, "pinned": v.pinned,
        "upside_median": (v.median / v.price - 1) if v.median is not None and v.price else None,
    }


def save_run(store: Store, user_id: int, out: SimulationOutput, summary: dict, label: str = "", notes: str = "") -> str:
    inp = out.inputs
    pct = summary.get("percentiles") or {}
    mask = out.valid
    idx = np.flatnonzero(mask)
    if idx.size > MAX_STORED_PATHS:
        idx = np.sort(np.random.default_rng(0).choice(idx, MAX_STORED_PATHS, replace=False))
    arrays = {"value": out.paths["value_per_share"][idx]}
    for k in out.draws.random_keys:
        arrays[k] = out.draws.values[k][idx]
    for k in ("wacc", "tv_share", "growth_terminal"):
        arrays["_" + k] = out.paths[k][idx]
    light = {k: v for k, v in summary.items() if k != "sample"}
    with store.Session.begin() as s:
        c = store.upsert_company(s, user_id, inp.company.ticker, inp.company.name, inp.company.currency,
                                 inp.company.yahoo_symbol)
        v = Valuation(
            company=c, label=label, notes=notes, source="app", engine_version=ENGINE_VERSION,
            seed=out.seed, n_paths=summary.get("n", 0), currency=inp.company.currency,
            inputs=json.loads(inp.model_dump_json(by_alias=True)),
            price=inp.base("price"), base_value=out.base.get("value_per_share"),
            mean=summary.get("mean"), median=summary.get("median"), sd=summary.get("sd"),
            p5=pct.get("p5"), p10=pct.get("p10"), p25=pct.get("p25"), p75=pct.get("p75"),
            p90=pct.get("p90"), p95=pct.get("p95"), prob_above_price=summary.get("prob_above_price"),
            tv_share=out.base.get("tv_share"),
        )
        s.add(v)
        s.flush()
        s.add(ValuationResult(valuation_id=v.id, summary=_jsonable(light), sample=pack_sample(arrays)))
        return v.id


def _jsonable(x):
    return json.loads(json.dumps(x, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def list_valuations(store: Store, user_id: int, ticker: str | None = None, limit: int = 500) -> list[dict]:
    with store.Session() as s:
        q = (select(Valuation).join(Company).where(Company.user_id == user_id)
             .order_by(Valuation.created_at.desc()).limit(limit))
        if ticker:
            q = q.where(Company.ticker == ticker.upper())
        return [valuation_row(v) for v in s.scalars(q)]


def _owned(s, user_id: int, vid: str) -> Valuation | None:
    v = s.get(Valuation, vid)
    return v if v is not None and v.company.user_id == user_id else None


def get_valuation(store: Store, user_id: int, vid: str, with_sample: bool = False) -> dict | None:
    with store.Session() as s:
        v = _owned(s, user_id, vid)
        if v is None:
            return None
        d = valuation_row(v)
        d["inputs"] = v.inputs
        d["summary"] = v.result.summary if v.result else None
        if with_sample and v.result:
            d["_sample"] = unpack_sample(v.result.sample)
        return d


def update_valuation(store: Store, user_id: int, vid: str, **fields) -> dict | None:
    with store.Session.begin() as s:
        v = _owned(s, user_id, vid)
        if v is None:
            return None
        for k in ("label", "notes", "pinned"):
            if k in fields and fields[k] is not None:
                setattr(v, k, fields[k])
    return get_valuation(store, user_id, vid)


def delete_valuation(store: Store, user_id: int, vid: str) -> bool:
    with store.Session.begin() as s:
        v = _owned(s, user_id, vid)
        if v is None:
            return False
        comp = v.company
        s.delete(v)
        s.flush()
        if not s.scalar(select(func.count()).select_from(Valuation).where(Valuation.company_id == comp.id)):
            s.delete(comp)
        return True


def companies(store: Store, user_id: int) -> list[dict]:
    """Latest valuation per company plus the history of medians (for sparklines)."""
    with store.Session() as s:
        out = []
        for c in s.scalars(select(Company).where(Company.user_id == user_id).order_by(Company.ticker)):
            vals = list(c.valuations)
            if not vals:
                continue
            last = vals[-1]
            out.append({
                "ticker": c.ticker, "name": c.name, "currency": c.currency, "yahoo_symbol": c.yahoo_symbol,
                "n_valuations": len(vals), "latest": valuation_row(last),
                "history": [{"date": _iso(v.created_at), "median": v.median, "p10": v.p10, "p90": v.p90,
                             "price": v.price} for v in vals],
            })
        return out


def company(store: Store, user_id: int, ticker: str) -> dict | None:
    with store.Session() as s:
        c = s.scalar(select(Company).where(Company.user_id == user_id, Company.ticker == ticker.upper()))
        if c is None:
            return None
        return {"ticker": c.ticker, "name": c.name, "currency": c.currency, "yahoo_symbol": c.yahoo_symbol,
                "notes": c.notes, "valuations": [valuation_row(v) for v in c.valuations]}


# ------------------------------------------------------------------ prices
def cached_prices(store: Store, symbol: str, start: str) -> list[tuple[str, float]]:
    with store.Session() as s:
        rows = s.execute(select(PriceCache.date, PriceCache.close)
                         .where(PriceCache.symbol == symbol, PriceCache.date >= start)
                         .order_by(PriceCache.date)).all()
        return [(d, c) for d, c in rows]


def put_prices(store: Store, symbol: str, rows: list[tuple[str, float]]) -> None:
    if not rows:
        return
    with store.Session.begin() as s:
        s.execute(delete(PriceCache).where(PriceCache.symbol == symbol, PriceCache.date >= rows[0][0]))
        s.add_all([PriceCache(symbol=symbol, date=d, close=c) for d, c in rows])


def prices(store: Store, symbol: str, start: str, fetcher=None) -> list[tuple[str, float]]:
    """Cached daily closes; refreshes from Yahoo when the cache is stale (> 1 day)."""
    have = cached_prices(store, symbol, start)
    stale = not have or have[-1][0] < (date.today() - timedelta(days=3)).isoformat() or have[0][0] > start
    if stale and fetcher is not None:
        try:
            fresh = fetcher(symbol, start)
            if fresh:
                put_prices(store, symbol, fresh)
                have = cached_prices(store, symbol, start)
        except Exception:  # noqa: BLE001 - offline: serve what we have
            pass
    return have


# ------------------------------------------------------------------ legacy import
_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _first(s) -> float | None:
    if s is None:
        return None
    m = _NUM.search(str(s).replace(",", ""))
    return float(m.group(0)) if m else None


def _pm(s) -> tuple[float | None, float | None]:
    """'15.0% (±2.0%)' -> (0.15, 0.02)"""
    if not s:
        return None, None
    nums = _NUM.findall(str(s))
    v = float(nums[0]) / 100 if nums else None
    sd = float(nums[1]) / 100 if len(nums) > 1 else None
    return v, sd


def import_legacy(store: Store, user_id: int, folder: str | Path) -> dict:
    """Imports the v1 Streamlit 'saved_analyses' folder (or an extracted export ZIP).
    v1 kept only formatted strings, so inputs are rebuilt where possible and the
    run is marked 'legacy-import'."""
    folder = Path(folder)
    idx_file = folder / "analyses_index.json"
    if not idx_file.exists():
        raise FileNotFoundError(f"{idx_file} not found")
    index = json.loads(idx_file.read_text(encoding="utf-8"))
    imported, skipped = 0, 0
    keymap = {"Growth 5y": "growth_1", "Growth 5-10y": "growth_2", "WACC": "wacc", "Risk Premium": "erp",
              "Risk Free Rate": "risk_free", "Reinvestment 5y": "reinvestment_1",
              "Reinvestment 5-10y": "reinvestment_2"}
    for ticker, analyses in index.items():
        for aid, info in analyses.items():
            f = folder / aid / "valuation_summary.json"
            if not f.exists():
                skipped += 1
                continue
            vs = json.loads(f.read_text(encoding="utf-8"))
            ts = info.get("timestamp", "")
            try:
                created = datetime.strptime(ts, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
            except ValueError:
                created = datetime.now(timezone.utc)
            cur = (str(vs.get("current_price", "")).split() or ["USD"])[-1][:3].upper()
            params = {}
            for lab, key in keymap.items():
                v, sd = _pm((vs.get("Variable Parameters") or {}).get(lab))
                if v is not None:
                    params[key] = {"value": v, "source": "legacy v1"}
                    if sd:
                        params[key]["dist"] = {"kind": "normal", "mean": v, "sd": sd}
            price = _first(vs.get("current_price"))
            if price is not None:
                params["price"] = {"value": price, "source": "legacy v1"}
            with store.Session.begin() as s:
                c = store.upsert_company(s, user_id, ticker, info.get("company_name", ticker), cur)
                vid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"dcfmc-legacy/{user_id}/{aid}"))
                if s.get(Valuation, vid) is not None:
                    skipped += 1
                    continue
                v = Valuation(id=vid, company=c, created_at=created, source="legacy-import",
                              label="Imported from v1", engine_version="1.x", currency=cur,
                              inputs={"company": {"ticker": ticker, "name": info.get("company_name", ""),
                                                  "currency": cur}, "params": params, "_legacy": True},
                              price=price, mean=_first(vs.get("mean_value")), median=_first(vs.get("median_value")),
                              sd=_first(vs.get("Std. Deviation")), p5=_first(vs.get("VaR 95%")),
                              prob_above_price=(_first(vs.get("prob_undervalued")) or 0) / 100)
                s.add(v)
                s.flush()
                s.add(ValuationResult(valuation_id=v.id, summary={"legacy": vs}, sample=None))
                imported += 1
    return {"imported": imported, "skipped": skipped}


def import_legacy_zip(store: Store, user_id: int, data: bytes) -> dict:
    """Imports a v1 'Export ZIP' (or a zipped saved_analyses folder) uploaded from the browser."""
    import io
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            total = 0
            for info in zf.infolist():
                target = (root / info.filename).resolve()
                if root not in target.parents and target != root:
                    raise ValueError("The ZIP contains unsafe paths.")
                total += info.file_size
                if total > 200 * 1024 * 1024:
                    raise ValueError("The ZIP is too large when extracted.")
            zf.extractall(root)
        idx = next(root.rglob("analyses_index.json"), None)
        if idx is None:
            raise ValueError("No analyses_index.json found: this is not a v1 export.")
        return import_legacy(store, user_id, idx.parent)
