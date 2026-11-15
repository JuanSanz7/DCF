import pandas as pd
import pytest

from dcfmc.io import yahoo


class FakeTicker:
    def __init__(self, sym):
        self.sym = sym
        q = pd.to_datetime(["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"])
        a = pd.to_datetime(["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"])
        self.info = {"currency": "USD", "financialCurrency": "CNY", "marketCap": 50e9, "longName": "Fake ADR",
                     "beta": 0.4}
        self.quarterly_income_stmt = pd.DataFrame(
            {d: {"Operating Income": 5e9, "Total Revenue": 50e9, "Diluted Average Shares": 2.4e9,
                 "Research And Development": 2e9} for d in q})
        self.income_stmt = pd.DataFrame(
            {d: {"Operating Income": 18e9, "Total Revenue": 190e9, "Research And Development": 7e9,
                 "Tax Provision": 4e9, "Pretax Income": 20e9} for d in a})
        self.quarterly_balance_sheet = pd.DataFrame(
            {q[0]: {"Cash Cash Equivalents And Short Term Investments": 70e9, "Total Debt": 20e9,
                    "Minority Interest": 5e9}})
        self.balance_sheet = pd.DataFrame()

    def history(self, period="5d", start=None):
        idx = pd.to_datetime(["2026-11-06"])
        if self.sym.endswith("=X"):
            return pd.DataFrame({"Close": [0.14]}, index=idx)
        return pd.DataFrame({"Close": [100.0]}, index=idx)


def test_fetch_adr_with_fx_and_rd():
    y = yahoo.fetch("FAKE", ticker_factory=FakeTicker)
    f = y.fields
    assert f["price"].value == 100.0
    # 4 quarters x 5bn CNY x 0.14 = 2.8bn USD reported EBIT
    assert f["ebit_reported"].value == pytest.approx(2800)
    # R&D capitalised: current 8bn, past 7bn x4 (+1 filled) -> amortisation 7bn -> +1bn CNY
    assert f["ebit"].value == pytest.approx((20e9 + 1e9) * 0.14 / 1e6)
    assert f["tax_rate"].value == pytest.approx(0.2)
    assert f["cash"].value == pytest.approx(70e9 * 0.14 / 1e6)
    # 2.4bn ordinary shares vs 500m price-consistent ADS -> uses 500m and warns
    assert f["shares"].value == pytest.approx(500)
    assert any("mismatch" in m["message"] for m in y.messages)
    p = yahoo.to_inputs_payload(y)
    assert p["company"]["currency"] == "USD"


def test_rd_adjustment_matches_template():
    # Alphabet template: TTM 68,974; FY2025..2021 = 61,087 49,326 45,427 39,500 31,562
    adj = yahoo.rd_adjustment(68974, [61087, 49326, 45427, 39500, 31562])
    assert adj["asset"] == pytest.approx(173510, abs=1)
    assert adj["amortization"] == pytest.approx(45380.4, abs=0.1)
