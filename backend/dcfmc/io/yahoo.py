"""Fundamentals from Yahoo Finance (via the open-source yfinance package).

Everything is read from the financial statements rather than the `info`
summary (which mixes definitions), every field carries its source and date,
and a missing field is reported as missing instead of being filled with a
made-up default. Main rules:

* EBIT = sum of the last four quarters of Operating Income (TTM), falling back
  to the last fiscal year.
* R&D is capitalised Damodaran-style (5-year straight-line life, current year at
  100%) when it is material, and the adjusted EBIT is proposed as the base.
* Statements reported in a currency different from the quote currency (ADRs,
  foreign listings) are converted at the spot FX rate.
* The share count is checked against market cap / price; a mismatch (ADR
  ratio) switches to the price-consistent count and says so.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from .template import ImportedField, ImportResult


def _yf():
    import yfinance as yf  # imported lazily: optional at runtime, heavy to import
    return yf


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _row(df, names: list[str]):
    if df is None or getattr(df, "empty", True):
        return None
    for n in names:
        if n in df.index:
            s = df.loc[n]
            s = s[~s.isna()] if hasattr(s, "isna") else s
            if len(s):
                return s
    return None


@dataclass
class YahooData:
    symbol: str
    fields: dict[str, ImportedField] = field(default_factory=dict)
    messages: list[dict] = field(default_factory=list)
    history: dict[str, Any] = field(default_factory=dict)
    currency: str | None = None
    financial_currency: str | None = None
    name: str | None = None

    def put(self, key, value, source, note=None):
        if value is None:
            return
        self.fields[key] = ImportedField(key, value, None, source, note)

    def msg(self, sev, text, key=None):
        self.messages.append({"severity": sev, "message": text, "key": key})

    def to_result(self) -> ImportResult:
        r = ImportResult(source=f"yahoo:{self.symbol}")
        r.fields = self.fields
        r.messages = self.messages
        return r


def rd_adjustment(current: float, past: list[float], life: int = 5) -> dict:
    """Damodaran R&D capitalisation. `past` = R&D of previous years, most recent first.
    Research asset = current + sum(past_k x (life - k)/life); amortisation = sum(past_k)/life
    for k = 1..life. Missing older years are filled with the oldest year available."""
    p = list(past[:life])
    filled = 0
    while len(p) < life and p:
        p.append(p[-1])
        filled += 1
    if not p:
        p = [current] * life
        filled = life
    asset = current + sum(v * (life - k) / life for k, v in enumerate(p, start=1))
    amort = sum(p) / life
    return {"asset": asset, "amortization": amort, "ebit_adjustment": current - amort, "years_filled": filled}


def fetch(symbol: str, ticker_factory: Callable[[str], Any] | None = None,
          capitalize_rd: bool | None = None) -> YahooData:
    yf = None if ticker_factory else _yf()
    T = ticker_factory or yf.Ticker
    sym = symbol.strip().upper()
    out = YahooData(sym)
    t = T(sym)

    def safe(fn, default=None):
        try:
            return fn()
        except Exception:  # noqa: BLE001 - network/parse errors are reported per field
            return default

    info = safe(lambda: t.info, {}) or {}
    out.name = info.get("longName") or info.get("shortName")
    out.currency = (info.get("currency") or "").upper() or None
    out.financial_currency = (info.get("financialCurrency") or out.currency or "").upper() or None

    # ---- price
    price = None
    hist = safe(lambda: t.history(period="5d"))
    if hist is not None and not getattr(hist, "empty", True):
        price = _num(hist["Close"].iloc[-1])
        out.put("price", price, f"yahoo:{sym} close {str(hist.index[-1])[:10]}")
    if price is None:
        price = _num(info.get("currentPrice") or info.get("regularMarketPrice"))
        out.put("price", price, f"yahoo:{sym} info.currentPrice")
    if price is None:
        out.msg("error", f"No price found for {sym}. Check the symbol (Yahoo format, e.g. ASML.AS, NOVO-B.CO).")
        return out

    # ---- FX between statements and quote
    fx = 1.0
    if out.financial_currency and out.currency and out.financial_currency != out.currency:
        pair = f"{out.financial_currency}{out.currency}=X"
        fxh = safe(lambda: T(pair).history(period="5d"))
        if fxh is not None and not getattr(fxh, "empty", True):
            fx = float(fxh["Close"].iloc[-1])
            out.msg("info", f"Statements are in {out.financial_currency}; converted to {out.currency} at {fx:.4f} ({pair}).")
        else:
            out.msg("error", f"Statements are in {out.financial_currency} but the {pair} rate is unavailable; money "
                             "fields were NOT converted.")

    # ---- income statement
    qi = safe(lambda: t.quarterly_income_stmt)
    ai = safe(lambda: t.income_stmt)
    op_q = _row(qi, ["Operating Income", "EBIT"])
    op_a = _row(ai, ["Operating Income", "EBIT"])
    ebit, ebit_src = None, None
    if op_q is not None and len(op_q) >= 4:
        ebit = float(op_q.iloc[:4].sum())
        ebit_src = f"yahoo:{sym} Operating Income, TTM to {str(op_q.index[0])[:10]}"
    elif op_a is not None:
        ebit = float(op_a.iloc[0])
        ebit_src = f"yahoo:{sym} Operating Income, FY to {str(op_a.index[0])[:10]}"
    if ebit is None:
        out.msg("warning", "Operating income not found; enter EBIT manually.", "ebit")

    rev_q = _row(qi, ["Total Revenue", "Operating Revenue"])
    rev_a = _row(ai, ["Total Revenue", "Operating Revenue"])
    revenue = float(rev_q.iloc[:4].sum()) if rev_q is not None and len(rev_q) >= 4 else (
        float(rev_a.iloc[0]) if rev_a is not None else None)

    rd_q = _row(qi, ["Research And Development", "Research Development"])
    rd_a = _row(ai, ["Research And Development", "Research Development"])
    if rd_q is not None and len(rd_q) >= 4:   # current = TTM, past years = every fiscal year
        rd_now = float(rd_q.iloc[:4].sum())
        rd_past = [float(x) for x in rd_a.tolist()] if rd_a is not None else []
    elif rd_a is not None:                     # current = last fiscal year
        rd_now = float(rd_a.iloc[0])
        rd_past = [float(x) for x in rd_a.iloc[1:].tolist()]
    else:
        rd_now, rd_past = None, []
    if ebit is not None:
        material = revenue and rd_now and rd_now / revenue > 0.02
        do_cap = capitalize_rd if capitalize_rd is not None else bool(material)
        out.put("ebit_reported", ebit * fx / 1e6, ebit_src)
        if do_cap and rd_now:
            adj = rd_adjustment(rd_now, rd_past)
            out.put("ebit", (ebit + adj["ebit_adjustment"]) * fx / 1e6,
                    ebit_src + " + R&D capitalised (5y)",
                    f"R&D {rd_now * fx / 1e6:,.0f}m, amortisation {adj['amortization'] * fx / 1e6:,.0f}m, "
                    f"research asset {adj['asset'] * fx / 1e6:,.0f}m")
            out.put("rd_asset", adj["asset"] * fx / 1e6, "computed")
            if adj["years_filled"]:
                out.msg("info", f"R&D capitalisation: {adj['years_filled']} older year(s) not in Yahoo's data were "
                                "assumed equal to the oldest available year.", "ebit")
        else:
            out.put("ebit", ebit * fx / 1e6, ebit_src)

    # ---- tax rate: effective, averaged over available years, bounded
    tax = _row(ai, ["Tax Provision", "Income Tax Expense"])
    pti = _row(ai, ["Pretax Income"])
    if tax is not None and pti is not None:
        rates = [_num(a) / _num(b) for a, b in zip(tax.tolist(), pti.tolist()) if _num(b) and _num(b) > 0 and _num(a) is not None]
        rates = [r for r in rates if 0 <= r <= 0.6]
        if rates:
            eff = float(np.mean(rates[:3]))
            out.put("tax_rate", round(eff, 4), f"yahoo:{sym} effective tax (avg of {min(3, len(rates))}y)")
            if eff < 0.1:
                out.msg("warning", f"Effective tax rate {eff:.1%} is low; consider moving toward the marginal rate.", "tax_rate")
    if "tax_rate" not in out.fields:
        out.msg("warning", "Tax rate not found; enter the effective or marginal rate.", "tax_rate")

    # ---- balance sheet
    qb = safe(lambda: t.quarterly_balance_sheet)
    ab = safe(lambda: t.balance_sheet)
    bs = qb if qb is not None and not getattr(qb, "empty", True) else ab
    bs_date = str(bs.columns[0])[:10] if bs is not None and not getattr(bs, "empty", True) else "n/a"
    def bs_val(names):
        r = _row(bs, names)
        return float(r.iloc[0]) if r is not None else None
    cash = bs_val(["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"])
    debt = bs_val(["Total Debt"])
    leases = bs_val(["Capital Lease Obligations"])
    minority = bs_val(["Minority Interest"])
    for key, v, lab in (("cash", cash, "Cash + short-term investments"), ("debt", debt, "Total Debt (incl. leases)"),
                        ("minority_interests", minority, "Minority Interest")):
        if v is not None:
            out.put(key, max(v, 0.0) * fx / 1e6, f"yahoo:{sym} balance sheet {bs_date}: {lab}")
    if leases:
        out.msg("info", f"Total debt includes {leases * fx / 1e6:,.0f}m of lease obligations (Damodaran treats leases as debt).", "debt")
    if debt is None:
        out.msg("warning", "Total debt not found.", "debt")

    # ---- shares: statements vs price-consistent count
    dil = _row(qi, ["Diluted Average Shares"])
    if dil is None:
        dil = _row(ai, ["Diluted Average Shares"])
    sh_stmt = float(dil.iloc[0]) / 1e6 if dil is not None else None
    mcap = _num(info.get("marketCap"))
    sh_implied = mcap / price / 1e6 if mcap and price else None
    if sh_stmt and sh_implied and abs(sh_implied / sh_stmt - 1) > 0.10:
        ratio = sh_stmt / sh_implied
        out.put("shares", sh_implied, f"yahoo:{sym} market cap / price",
                f"Statements show {sh_stmt:,.0f}m shares; price implies {sh_implied:,.0f}m "
                f"(ratio ~{ratio:.2f}, typical of ADRs or share classes).")
        out.msg("warning", f"Share count mismatch: statements {sh_stmt:,.0f}m vs market cap / price {sh_implied:,.0f}m. "
                           "Using the price-consistent count so value per share matches the quoted price.", "shares")
    elif sh_stmt:
        out.put("shares", sh_stmt, f"yahoo:{sym} diluted average shares (last quarter)")
    elif sh_implied:
        out.put("shares", sh_implied, f"yahoo:{sym} market cap / price")
    else:
        out.msg("error", "Share count not found; enter it manually.", "shares")
    if mcap:
        out.put("market_cap", mcap / 1e6, f"yahoo:{sym} market cap")

    beta = _num(info.get("beta"))
    if beta is not None:
        out.put("beta", beta, f"yahoo:{sym} 5y monthly regression beta",
                "Regression beta (standard error often 0.1-0.3). Damodaran prefers a bottom-up beta.")

    # ---- history for context / empirical distributions
    if rev_a is not None and len(rev_a) >= 2:
        r = rev_a.iloc[::-1]
        g = (r.values[1:] / r.values[:-1] - 1).tolist()
        out.history["revenue_growth"] = [float(x) for x in g]
        out.history["years"] = [str(x)[:4] for x in r.index[1:]]
    if op_a is not None and rev_a is not None:
        out.history["operating_margin"] = [float(a / b) for a, b in zip(op_a.values[::-1], rev_a.values[::-1]) if b]
    return out


def to_inputs_payload(y: YahooData) -> dict:
    params = {}
    for key in ("price", "shares", "ebit", "tax_rate", "cash", "debt", "minority_interests", "beta"):
        f = y.fields.get(key)
        if f is not None and f.value is not None:
            params[key] = {"value": float(f.value), "source": f.cell, **({"note": f.note} if f.note else {})}
    mc = y.fields.get("market_cap")
    if mc and "debt" in params:
        d = params["debt"]["value"]
        params["debt_weight"] = {"value": d / (mc.value + d), "source": "debt / (market cap + debt)"}
    return {
        "company": {"ticker": y.symbol.split(".")[0], "name": y.name or "", "currency": y.currency or "USD",
                    "yahoo_symbol": y.symbol},
        "params": params,
    }


def search(query: str, limit: int = 10) -> list[dict]:
    yf = _yf()
    try:
        s = yf.Search(query, max_results=limit)
        quotes = s.quotes or []
    except Exception:  # noqa: BLE001
        return []
    return [{"symbol": q.get("symbol"), "name": q.get("longname") or q.get("shortname"),
             "exchange": q.get("exchDisp") or q.get("exchange"), "type": q.get("quoteType")}
            for q in quotes if q.get("symbol")]


def price_history(symbol: str, start: str | None = None, period: str = "5y") -> list[tuple[str, float]]:
    yf = _yf()
    t = yf.Ticker(symbol)
    h = t.history(start=start) if start else t.history(period=period)
    if h is None or h.empty:
        return []
    return [(str(i)[:10], float(c)) for i, c in zip(h.index, h["Close"]) if c == c]
