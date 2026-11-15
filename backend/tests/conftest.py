"""Shared fixtures. Workbooks are generated here (no proprietary files in the repo);
labels and numbers mirror the structure of the FCFF template tabs."""
import io

import openpyxl
import pytest
from openpyxl.comments import Comment

GOOGL_ROWS = [
    ("FCFF VALUATION", "Agosto 2026"),
    ("0. Empresa - Resumen", None),
    ("Ticker", "GOOGL"),
    ("Nombre de la empresa", "Alphabet Inc. (Class A)"),
    ("Divisa", "USD"),
    ("Precio", 354.3),
    ("Shares Outstanding (millions)", 12309),
    ("Valor intrinseco", 241.975283106158),
    ("1. Coste de Capital (WACC)", None),
    ("Tasa libre de riesgo (Rf)", 0.0465),
    ("Prima de riesgo (ERP), mercado maduro", 0.0482),
    ("Beta (apalancado, 5A mensual)", 1.05),
    ("Coste de fondos propios (Ke = Rf + beta x ERP)", 0.09711),
    ("Rating crediticio", "Aa2 / AA+"),
    ("Margen de incumplimiento (default spread)", 0.0055),
    ("Coste de deuda antes de impuestos (Kd = Rf + spread)", 0.052),
    ("Tasa impositiva (usada en todo el modelo)", 0.19),
    ("Coste de deuda despues de impuestos", 0.04212),
    ("Capitalizacion bursatil - MC", 4361078.7),
    ("Deuda total - Debt (valor contable)", 98165),
    ("Valor total (E + D)", 4459243.7),
    ("Peso fondos propios (E/V)", 0.977986177342135),
    ("Peso deuda (D/V)", 0.0220138226578646),
    ("COST OF CAPITAL (WACC)", 0.095899459892044),
    ("EBIT reportado (TTM/ultimo)", 147628),
    ("EBIT (con I+D capitalizado)", 171221.6),
    ("Caja y equivalentes (+ inversiones corto plazo)", 242474),
    ("NOPAT", 138689.496),
    ("ROIC", 0.207097851066403, 0.19),
    ("Tasa de reinversion (Reinversion / NOPAT adj.)", 1.19471628911248, 0.52),
    ("Tasa de crecimiento implicita por inversion (g = ROIC x RR)", 0.247423176109222, 0.1),
    ("Growth 5y - crecimiento NOPAT, Anos 1-5", 0.18),
    ("Growth 5-10y - crecimiento NOPAT, anos 6-10", 0.10),
    ("Reinvestment 5y - tasa de reinversion, anos 1-5", 0.90),
    ("Reinvestment 5-10y - tasa de reinversion, anos 6-10", 0.52),
    ("Terminal growth = Risk free rate", 0.0465),
    ("Terminal WACC = Risk free + Equity premium", 0.0947),
    ("(-) Deuda total", -98165),
    ("(+) Caja y equivalentes", 242474),
    ("VALOR INTRINSECO POR ACCION", 241.975283106158),
    ("Precio de mercado actual", 354.3),
    ("MEMO (+) Participaciones no cotizadas, no incluidas en el caso base", 131461),
]
GOOGL_NOTES = {
    "Tasa libre de riesgo (Rf)": "Rf = 4,65%. RANGO RAZONABLE: 4,00% - 5,25%. SENSIBILIDAD: ...",
    "Reinvestment 5y - tasa de reinversion, anos 1-5": "REINVERSION ETAPA 1 = 90%. RANGO: 70% - 110%.",
    "Beta (apalancado, 5A mensual)": "BETA = 1,05. RANGO: 0,95 - 1,25.",
}


def make_workbook(rows, notes=None, title="GOOGL") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    for i, r in enumerate(rows, start=1):
        for j, v in enumerate(r, start=1):
            ws.cell(i, j, v)
        if notes and r[0] in notes:
            ws.cell(i, 2).comment = Comment(notes[r[0]], "test")
    wb.create_sheet("Other")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def googl_xlsx() -> bytes:
    return make_workbook(GOOGL_ROWS, GOOGL_NOTES)


@pytest.fixture
def googl_rows():
    return [list(r) for r in GOOGL_ROWS]
