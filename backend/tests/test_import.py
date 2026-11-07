import pytest

from dcfmc.core.engine import base_case
from dcfmc.core.inputs import ValuationInputs
from dcfmc.core.validation import validate
from dcfmc.io.sheets import Workbook
from dcfmc.io.template import read_grid, to_inputs_payload
from dcfmc.io.tickers import to_yahoo


def test_excel_import_reproduces_sheet(googl_xlsx):
    res = Workbook.from_bytes(googl_xlsx).read_tab("GOOGL", "excel")
    f = res.fields
    assert f["risk_free"].value == pytest.approx(0.0465)
    assert f["risk_free"].range == pytest.approx((0.04, 0.0525))
    assert f["reinvestment_1"].range == pytest.approx((0.70, 1.10))
    assert f["beta"].range == pytest.approx((0.95, 1.25))
    assert f["roic_stage2"].value == pytest.approx(0.19)
    payload = to_inputs_payload(res, "GOOGL")
    inp = ValuationInputs.model_validate(payload)
    assert inp.model.discount_mode == "build_up"
    # non-operating memo is imported; remove it to compare with the sheet's base case
    inp.params.pop("non_operating_assets")
    assert base_case(inp)["value_per_share"] == pytest.approx(f["intrinsic_value"].value, rel=1e-9)
    assert inp.params["reinvestment_1"].dist.kind == "pert"        # from the note's range
    assert inp.params["growth_1"].dist.kind == "truncnormal"       # symmetric with an editable sigma
    assert not [i for i in validate(inp) if i.severity == "error"]


def test_csv_displayed_values_european(googl_rows):
    # Same tab as Google's CSV export of displayed values in a Spanish-locale sheet
    def disp(v):
        if isinstance(v, float) and abs(v) < 1.5:
            return f"{v * 100:.2f}%".replace(".", ",")
        if isinstance(v, (int, float)):
            s = f"{v:,.0f}".replace(",", ".")
            return s + " m"
        return v
    rows = [[r[0]] + [disp(x) for x in r[1:]] for r in googl_rows]
    rows[5][1] = "354,30 $"
    rows[40][1] = "354,30 $"
    rows[6][1] = "12309,00"
    rows[11][1] = "1,05"
    res = read_grid(rows, source="csv")
    assert res.locale == "eu"
    f = res.fields
    assert f["debt"].value == pytest.approx(98165)
    assert f["price"].value == pytest.approx(354.30)
    assert f["shares"].value == pytest.approx(12309)
    assert f["beta"].value == pytest.approx(1.05)
    assert f["risk_free"].value == pytest.approx(0.0465)
    assert f["growth_1"].value == pytest.approx(0.18)


@pytest.mark.parametrize("g,y", [("AMS:ASML", "ASML.AS"), ("NASDAQ:GOOGL", "GOOGL"), ("CPH:NOVO-B", "NOVO-B.CO"),
                                 ("HKG:700", "0700.HK"), ("BIT:LDO", "LDO.MI"), ("JD", "JD")])
def test_tickers(g, y):
    assert to_yahoo(g) == y
