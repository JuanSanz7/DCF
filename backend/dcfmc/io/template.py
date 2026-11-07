"""Reads a company tab built from Juan's Damodaran FCFF template.

Inputs are located by the label text in column A (accent- and case-
insensitive), so inserted, deleted or reordered rows don't matter. For each
field the first matching candidate wins; candidates are tried as a prefix
match first and as a substring match second, so "roic" finds "ROIC (adjusted)"
before it finds "... (g = ROIC x RR)".

Values are read from column B. A few rows carry a second value in column C
(stage-2 ROIC, reinvestment and growth). Cell notes are parsed for researched
ranges such as "RANGO: 4,00% - 5,25%" and become distribution suggestions.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ..core import advisor
from ..core.parameters import PARAMETERS
from ..core.units import Unit
from .numbers import Locale, detect_locale, parse_number
from .tickers import to_yahoo


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


# key -> (candidate labels, column index (1 = B, 2 = C), kind)
# kind: "param" (model input), "meta" (company info), "ref" (reference value for cross-checks)
FIELDS: dict[str, tuple[list[str], int, str]] = {
    "ticker": (["ticker"], 1, "meta"),
    "name": (["nombre de la empresa", "company name"], 1, "meta"),
    "name_ticker": (["nombre de la empresa / ticker"], 1, "meta"),
    "currency": (["divisa", "currency"], 1, "meta"),
    "price": (["precio de mercado actual", "precio", "current price", "price"], 1, "param"),
    "shares": (["shares outstanding", "acciones en circulacion", "acciones diluidas", "diluted shares"], 1, "param"),
    "risk_free": (["tasa libre de riesgo", "risk free rate", "riskfree rate", "risk-free rate"], 1, "param"),
    "erp": (["prima de riesgo", "equity risk premium", "erp"], 1, "param"),
    "beta": (["beta"], 1, "param"),
    "default_spread": (["margen de incumplimiento", "default spread"], 1, "param"),
    "tax_rate": (["tasa impositiva", "tax rate"], 1, "param"),
    "market_cap": (["capitalizacion bursatil", "market cap"], 1, "ref"),
    "debt": (["deuda total", "total debt"], 1, "param"),
    "wacc": (["cost of capital (wacc)", "wacc (periodo explicito", "wacc"], 1, "param"),
    "ebit_reported": (["ebit reportado", "reported ebit"], 1, "ref"),
    "ebit": (["ebit (con i+d capitalizado)", "ebit ajustado", "adjusted ebit", "operating income base"], 1, "param"),
    "rd_asset": (["activo de investigacion", "research asset"], 1, "ref"),
    "cash": (["caja y equivalentes", "cash and equivalents", "cash & equivalents"], 1, "param"),
    "invested_capital": (["capital invertido", "invested capital"], 1, "ref"),
    "nopat": (["nopat"], 1, "ref"),
    "roic_hist": (["roic"], 1, "ref"),
    "roic_stage2": (["roic"], 2, "ref"),
    "rr_hist": (["tasa de reinversion", "reinvestment rate (hist"], 1, "ref"),
    "rr_stage2_ref": (["tasa de reinversion"], 2, "ref"),
    "growth_1": (["growth 5y", "growth stage 1", "crecimiento nopat, anos 1-5"], 1, "param"),
    "growth_2": (["growth 5-10y", "growth stage 2", "crecimiento nopat, anos 6-10"], 1, "param"),
    "reinvestment_1": (["reinvestment 5y", "reinvestment stage 1"], 1, "param"),
    "reinvestment_2": (["reinvestment 5-10y", "reinvestment stage 2"], 1, "param"),
    "non_operating_assets": (["memo (+) participaciones", "non-operating assets", "activos no operativos",
                              "participaciones no cotizadas"], 1, "param"),
    "minority_interests": (["intereses minoritarios", "minority interest"], 1, "param"),
    "intrinsic_value": (["valor intrinseco por accion", "valor intrinseco", "intrinsic value"], 1, "ref"),
    "terminal_growth_ref": (["terminal growth"], 1, "ref"),
    "terminal_wacc_ref": (["terminal wacc"], 1, "ref"),
}
# Labels that must not be confused with the field (substring traps).
EXCLUDE = {
    "price": ["precio objetivo"],
    "beta": ["unlevered", "desapalancada"],
    "ebit": ["reportado"],
    "debt": ["(-)", "peso", "despues"],
    "cash": ["(+)"],
    "erp": ["terminal"],
    "risk_free": ["terminal"],
    "tax_rate": ["despues"],
}
_PERCENT_KEYS = {k for k, p in PARAMETERS.items() if p.unit in (Unit.PERCENT, Unit.PROBABILITY)} | {
    "roic_hist", "roic_stage2", "rr_hist", "rr_stage2_ref", "terminal_growth_ref", "terminal_wacc_ref"}
_MONEY_KEYS = {k for k, p in PARAMETERS.items() if p.unit == Unit.MONEY_M} | {
    "market_cap", "ebit_reported", "rd_asset", "invested_capital", "nopat"}


@dataclass
class ImportedField:
    key: str
    value: float | str | None
    raw: str | None
    cell: str | None
    note: str | None = None
    range: tuple[float, float] | None = None
    ambiguous: bool = False


@dataclass
class ImportResult:
    source: str
    fields: dict[str, ImportedField] = field(default_factory=dict)
    messages: list[dict] = field(default_factory=list)
    locale: str | None = None

    def msg(self, severity: str, text: str, key: str | None = None):
        self.messages.append({"severity": severity, "message": text, "key": key})

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "locale": self.locale,
            "fields": {k: {"value": f.value, "raw": f.raw, "cell": f.cell, "note": f.note,
                           "range": list(f.range) if f.range else None, "ambiguous": f.ambiguous}
                       for k, f in self.fields.items()},
            "messages": self.messages,
        }


def _col_letter(i: int) -> str:
    return "ABCDEFGHIJ"[i]


def _match(labels: list[str], cands: list[str], exclude: list[str]) -> int | None:
    for mode in ("prefix", "contains"):
        for c in cands:
            for i, lab in enumerate(labels):
                if not lab:
                    continue
                ok = lab.startswith(c) if mode == "prefix" else c in lab
                if ok and not any(x in lab for x in exclude):
                    return i
    return None


_RANGE_RX = re.compile(
    r"rango(?:\s+razonable)?\s*:?\s*([-+]?\d[\d.,]*\s*%?)\s*(?:-|–|a|to)\s*([-+]?\d[\d.,]*\s*%?)",
    re.I)


def parse_range(note: str | None, locale: Locale | None, percent: bool) -> tuple[float, float] | None:
    if not note:
        return None
    m = _RANGE_RX.search(note) or _RANGE_RX.search(norm(note))
    if not m:
        return None
    a, b = (parse_number(x, locale=locale or "eu") for x in m.groups())
    if not a or not b:
        return None
    va, vb = a.value, b.value
    if percent and not a.is_percent and abs(va) > 1.5:
        va /= 100
    if percent and not b.is_percent and abs(vb) > 1.5:
        vb /= 100
    lo, hi = sorted((va, vb))
    return (lo, hi) if lo < hi else None


def read_grid(rows: list[list], notes: dict[tuple[int, int], str] | None = None,
              source: str = "sheet", locale: Locale | None = None) -> ImportResult:
    """rows: list of rows (each a list of cell values, column A first).
    notes: optional {(row_idx, col_idx): text} cell notes."""
    notes = notes or {}
    res = ImportResult(source=source)
    labels = [norm(r[0]) if r and r[0] is not None else "" for r in rows]
    if locale is None:
        sample = [str(c) for r in rows for c in r[1:4] if isinstance(c, str)]
        locale = detect_locale(sample)
    res.locale = locale
    for key, (cands, col, kind) in FIELDS.items():
        i = _match(labels, cands, EXCLUDE.get(key, []))
        if i is None:
            continue
        row = rows[i]
        raw = row[col] if len(row) > col else None
        cell = f"{_col_letter(col)}{i + 1}"
        note = notes.get((i, col)) or notes.get((i, 0))
        if kind == "meta":
            if raw is None or str(raw).strip() == "":
                continue
            res.fields[key] = ImportedField(key, str(raw).strip(), str(raw), cell, note)
            continue
        prefer = "thousands" if key in _MONEY_KEYS or key == "shares" else "decimal"
        p = parse_number(raw, locale=locale, prefer=prefer)
        if p is None:
            continue
        v = p.value
        if key in _PERCENT_KEYS and not p.is_percent and abs(v) > 1.5 and isinstance(raw, str):
            v /= 100.0  # "4.65" typed without % in a percent field
            res.msg("warning", f"{key}: read '{raw}' as {v:.2%} (no % sign).", key)
        if p.scale_to_millions not in (None, 1.0) and key in _MONEY_KEYS:
            v *= p.scale_to_millions
        rng = parse_range(note, locale, key in _PERCENT_KEYS) if key in PARAMETERS else None
        f = ImportedField(key, v, None if raw is None else str(raw), cell, note, rng, p.ambiguous)
        res.fields[key] = f
        if p.ambiguous:
            res.msg("warning", f"{key}: '{raw}' is ambiguous (thousands or decimal); read as {v:,.4g}.", key)
    return res


def to_inputs_payload(res: ImportResult, tab: str | None = None, with_distributions: bool = True) -> dict:
    """Converts an ImportResult into a ValuationInputs-compatible dict."""
    f = res.fields
    val = lambda k: f[k].value if k in f else None  # noqa: E731
    ticker_raw = str(val("ticker") or tab or "UNKNOWN")
    name = str(val("name") or "")
    if not name and val("name_ticker"):
        name = str(val("name_ticker"))
    cur = str(val("currency") or "USD").strip().upper()
    cur_code = re.sub(r"[^A-Z]", "", cur)[:3] or "USD"
    yahoo = to_yahoo(ticker_raw)
    params: dict[str, dict] = {}
    for key in PARAMETERS:
        if key in f and isinstance(f[key].value, (int, float)):
            params[key] = {"value": float(f[key].value), "source": f"{res.source}!{f[key].cell}"}
    model = {"discount_mode": "direct", "reinvestment_mode": "rate", "stage2_mode": "flat"}
    # Prefer the build-up WACC when every ingredient is present; it keeps Rf/ERP/beta consistent.
    have = all(k in params for k in ("risk_free", "erp", "beta"))
    mc, debt = val("market_cap"), val("debt")
    if have and isinstance(mc, (int, float)) and mc > 0:
        dw = (debt or 0.0) / (mc + (debt or 0.0))
        params["debt_weight"] = {"value": dw, "source": f"{res.source} (debt / (market cap + debt))"}
        params.setdefault("default_spread", {"value": PARAMETERS["default_spread"].default, "source": "default"})
        model["discount_mode"] = "build_up"
        if "wacc" in params:
            ke = params["risk_free"]["value"] + params["beta"]["value"] * params["erp"]["value"]
            kd = params["risk_free"]["value"] + params["default_spread"]["value"]
            t = params.get("tax_rate", {}).get("value", 0.21)
            wb = ke * (1 - dw) + kd * (1 - t) * dw
            if abs(wb - params["wacc"]["value"]) > 0.0005:
                res.msg("warning", f"Build-up WACC {wb:.2%} differs from the sheet's WACC "
                                   f"{params['wacc']['value']:.2%}; switch to direct mode to use the sheet value.")
    if with_distributions:
        for key, p in params.items():
            spec = PARAMETERS[key]
            rng = f[key].range if key in f else None
            if rng or spec.stochastic_by_default:
                d = advisor.recommended_dist(key, p["value"], *(rng or (None, None)))
                p["dist"] = d
                if rng:
                    p["note"] = f"Range from sheet note: {rng[0]:.4g} to {rng[1]:.4g}"
    return {
        "company": {"ticker": re.sub(r"^[A-Z]+:", "", ticker_raw.strip().upper())[:32] or "UNKNOWN",
                    "name": name, "currency": cur_code, "yahoo_symbol": yahoo},
        "params": params,
        "model": model,
        "terminal": {"method": "rf_linked", "wacc_source": "market", "roic_mode": "equal_wacc"},
    }
