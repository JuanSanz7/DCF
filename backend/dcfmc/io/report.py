"""Excel report of one saved valuation (inputs, results, base case, distribution)."""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ..core.parameters import PARAMETERS
from ..core.units import Unit

INK = "14213D"
HEAD = Font(bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor=INK)
BOLD = Font(bold=True)
FMT = {Unit.PERCENT: "0.00%", Unit.PROBABILITY: "0.0%", Unit.MONEY_M: "#,##0", Unit.SHARES_M: "#,##0.0",
       Unit.PRICE: "#,##0.00", Unit.RATIO: "0.00", Unit.MULTIPLE: "0.0x", Unit.YEARS: "0"}


def _dist_text(d: dict | None, unit: Unit) -> str:
    if not d or d.get("kind") == "fixed":
        return "Fixed"
    f = 100 if unit in (Unit.PERCENT, Unit.PROBABILITY) else 1
    sfx = "%" if f == 100 else ""
    parts = []
    for k in ("mean", "sd", "low", "mode", "high", "bound"):
        if k in d and d[k] is not None:
            parts.append(f"{k}={d[k] * f:.4g}{sfx}")
    for k in ("lam", "df", "side"):
        if k in d:
            parts.append(f"{k}={d[k]}")
    if "values" in d:
        parts.append(f"{len(d['values'])} values")
    return f"{d['kind']}(" + ", ".join(parts) + ")"


def _header(ws, row, cols):
    for j, c in enumerate(cols, start=1):
        cell = ws.cell(row, j, c)
        cell.font, cell.fill = HEAD, HEAD_FILL
        cell.alignment = Alignment(vertical="center")


def _widths(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def build_xlsx(v: dict) -> bytes:
    s = v.get("summary") or {}
    inp = v.get("inputs") or {}
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    cur = v.get("currency", "")
    ws["A1"] = f"{v['ticker']} {v.get('name', '')} - FCFF Monte Carlo valuation"
    ws["A1"].font = Font(bold=True, size=14, color=INK)
    rows = [
        ("Valued on", v["created_at"][:10], None), ("Label", v.get("label", ""), None), ("Notes", v.get("notes", ""), None),
        ("Currency", cur, None), ("Market price", v.get("price"), "#,##0.00"),
        ("Base-case value per share", v.get("base_value"), "#,##0.00"), ("Mean", v.get("mean"), "#,##0.00"),
        ("Median", v.get("median"), "#,##0.00"), ("Std. deviation", v.get("sd"), "#,##0.00"),
        ("P5", v.get("p5"), "#,##0.00"), ("P10", v.get("p10"), "#,##0.00"), ("P25", v.get("p25"), "#,##0.00"),
        ("P75", v.get("p75"), "#,##0.00"), ("P90", v.get("p90"), "#,##0.00"), ("P95", v.get("p95"), "#,##0.00"),
        ("Probability value > price", v.get("prob_above_price"), "0.0%"),
        ("Upside at the median", v.get("upside_median"), "0.0%"),
        ("Terminal value share of EV (base)", v.get("tv_share"), "0.0%"),
        ("Paths", v.get("n_paths"), "#,##0"), ("Paths dropped", s.get("invalid_fraction"), "0.00%"),
        ("Seed", v.get("seed"), None), ("Engine version", v.get("engine_version"), None),
    ]
    for i, (k, val, fmt) in enumerate(rows, start=3):
        ws.cell(i, 1, k).font = BOLD
        c = ws.cell(i, 2, val)
        if fmt:
            c.number_format = fmt
    m = inp.get("model") or {}
    t = inp.get("terminal") or {}
    r = len(rows) + 4
    ws.cell(r, 1, "Model settings").font = Font(bold=True, color=INK, size=12)
    for k, val in {**{f"model.{a}": b for a, b in m.items()}, **{f"terminal.{a}": b for a, b in t.items()}}.items():
        r += 1
        ws.cell(r, 1, k)
        ws.cell(r, 2, str(val))
    _widths(ws, [36, 40])

    wi = wb.create_sheet("Inputs")
    _header(wi, 1, ["Input", "Unit", "Base value", "Distribution", "Simulated P5", "Simulated median", "Simulated P95", "Source"])
    sim_in = s.get("inputs") or {}
    for i, (k, p) in enumerate((inp.get("params") or {}).items(), start=2):
        spec = PARAMETERS.get(k)
        if spec is None:
            continue
        wi.cell(i, 1, spec.label)
        wi.cell(i, 2, spec.unit.value)
        c = wi.cell(i, 3, p.get("value"))
        c.number_format = FMT[spec.unit]
        wi.cell(i, 4, _dist_text(p.get("dist"), spec.unit))
        for j, q in enumerate(("p5", "p50", "p95"), start=5):
            if k in sim_in:
                cc = wi.cell(i, j, sim_in[k].get(q))
                cc.number_format = FMT[spec.unit]
        wi.cell(i, 8, p.get("source") or "")
    _widths(wi, [34, 11, 14, 46, 14, 16, 14, 40])

    base = s.get("base") or {}
    tab = base.get("table") or {}
    if tab:
        wt = wb.create_sheet("Base case")
        _header(wt, 1, ["m " + cur] + [f"Year {y}" for y in tab["year"]])
        lines = [("NOPAT growth", "growth", "0.0%"), ("NOPAT", "nopat", "#,##0"), ("Reinvestment rate", "reinvestment", "0.0%"),
                 ("Return on new capital", "roic", "0.0%"), ("FCFF", "fcff", "#,##0"), ("WACC", "wacc", "0.00%"),
                 ("Discount factor", "discount_factor", "0.0000"), ("PV of FCFF", "pv_fcff", "#,##0")]
        for i, (lab, key, fmt) in enumerate(lines, start=2):
            wt.cell(i, 1, lab).font = BOLD
            for j, x in enumerate(tab[key], start=2):
                wt.cell(i, j, x).number_format = fmt
        r = len(lines) + 3
        for lab, key in (("PV explicit FCFF", "pv_fcff"), ("Terminal value", "tv"), ("PV terminal value", "pv_tv"),
                         ("Enterprise value", "ev"), ("Equity value", "equity"), ("Value per share", "value_per_share")):
            wt.cell(r, 1, lab).font = BOLD
            wt.cell(r, 2, base.get(key)).number_format = "#,##0.00"
            r += 1
        _widths(wt, [26] + [12] * len(tab["year"]))

    h = s.get("histogram")
    if h:
        wd = wb.create_sheet("Distribution")
        _header(wd, 1, ["From", "To", "Paths", "Share"])
        for i, cnt in enumerate(h["counts"], start=2):
            wd.cell(i, 1, h["edges"][i - 2]).number_format = "#,##0.00"
            wd.cell(i, 2, h["edges"][i - 1]).number_format = "#,##0.00"
            wd.cell(i, 3, cnt)
            wd.cell(i, 4, cnt / h["total"]).number_format = "0.00%"
        _widths(wd, [12, 12, 10, 10])
    if s.get("tornado"):
        wsn = wb.create_sheet("Sensitivity")
        _header(wsn, 1, ["Input", "P10 input", "P90 input", "Value at P10", "Value at P90", "Swing"])
        for i, t in enumerate(s["tornado"], start=2):
            unit = Unit(t["unit"])
            wsn.cell(i, 1, t["label"])
            wsn.cell(i, 2, t["input_low"]).number_format = FMT[unit]
            wsn.cell(i, 3, t["input_high"]).number_format = FMT[unit]
            for j, k in ((4, "value_low"), (5, "value_high"), (6, "swing")):
                wsn.cell(i, j, t[k]).number_format = "#,##0.00"
        _widths(wsn, [34, 12, 12, 14, 14, 12])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
