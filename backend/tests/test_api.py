import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dcfmc.api.app import create_app
from dcfmc.store.db import Store
from test_engine import mk


@pytest.fixture
def client(tmp_path):
    app = create_app(Store(f"sqlite:///{tmp_path / 't.db'}"), static_dir=tmp_path / "none")
    return TestClient(app)


def payload(**kw):
    d = mk("build_up", simulation={"n": 3000, "seed": 1}, **kw).model_dump(by_alias=True)
    d["params"]["growth_1"]["dist"] = {"kind": "pert", "low": 0.12, "mode": 0.18, "high": 0.26}
    d["params"]["beta"]["dist"] = {"kind": "truncnormal", "mean": 1.05, "sd": 0.1, "low": 0.7, "high": 1.5}
    return d


def test_meta(client):
    m = client.get("/api/meta").json()
    assert {p["key"] for p in m["parameters"]} >= {"growth_1", "erp"}
    assert m["distributions"][0]["kind"] == "fixed"


def test_validate_and_simulate_and_save(client):
    v = client.post("/api/validate", json=payload()).json()
    assert v["base"]["value_per_share"] == pytest.approx(241.9753, rel=1e-6)
    r = client.post("/api/simulate", json=payload()).json()
    s = r["summary"]
    assert s["n_valid"] > 2900 and "heatmaps" in s
    ex = client.get("/api/explore", params={"x": "growth_1", "y": "beta", "run_token": r["run_token"]}).json()
    assert len(ex["median"]) == 12
    saved = client.post("/api/valuations", json={"run_token": r["run_token"], "label": "first"}).json()
    assert saved["median"] == pytest.approx(s["median"], rel=1e-6)
    got = client.get(f"/api/valuations/{saved['id']}").json()
    assert got["inputs"]["params"]["growth_1"]["dist"]["kind"] == "pert"
    assert len(got["summary"]["sample"]["value"]) > 1000
    ex2 = client.get("/api/explore", params={"x": "growth_1", "y": "beta", "valuation_id": saved["id"]}).json()
    assert ex2["median"]
    x = client.get(f"/api/valuations/{saved['id']}/export.xlsx")
    assert x.status_code == 200 and x.content[:2] == b"PK"
    import io, openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(x.content))
    assert {"Summary", "Inputs", "Base case", "Distribution", "Sensitivity"} <= set(wb.sheetnames)
    comps = client.get("/api/companies").json()
    assert comps[0]["ticker"] == "GOOGL" and comps[0]["n_valuations"] == 1
    assert client.patch(f"/api/valuations/{saved['id']}", json={"notes": "hello"}).json()["notes"] == "hello"
    assert client.delete(f"/api/valuations/{saved['id']}").json()["ok"]
    assert client.get("/api/companies").json() == []


def test_simulate_rejects_errors(client):
    d = payload()
    d["params"]["shares"]["value"] = 0
    r = client.post("/api/simulate", json=d)
    assert r.status_code == 422


def test_bad_payload_422(client):
    assert client.post("/api/validate", json={"company": {"ticker": "X"}, "params": {"nope": {}}}).status_code == 422


def test_excel_import(client, googl_xlsx):
    r = client.post("/api/import/excel", files={"file": ("g.xlsx", googl_xlsx)}, data={"tab": "GOOGL"}).json()
    assert r["check"]["match"] is True
    assert r["inputs"]["params"]["reinvestment_1"]["dist"]["kind"] == "pert"
    r2 = client.post("/api/import/excel", files={"file": ("g.xlsx", googl_xlsx)}).json()
    assert r2["needs_tab"] and "GOOGL" in r2["tabs"]


def test_suggest_and_preview(client):
    s = client.post("/api/suggest", json={"key": "growth_1", "base": 0.18, "low": 0.14, "high": 0.24}).json()
    assert s["suggestions"][0]["recommended"]
    p = client.post("/api/distribution/preview", json=s["suggestions"][0]["dist"]).json()
    assert p["p5"] < 0.18 < p["p95"]


def test_password(tmp_path, monkeypatch):
    monkeypatch.setenv("DCF_APP_PASSWORD", "s3cret")
    c = TestClient(create_app(Store(f"sqlite:///{tmp_path / 'p.db'}"), static_dir=tmp_path / "none"))
    assert c.get("/api/meta").status_code == 401
    assert c.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    assert c.post("/api/auth/login", json={"password": "s3cret"}).status_code == 200
    assert c.get("/api/meta").status_code == 200


def test_legacy_import(tmp_path):
    from dcfmc.store.repo import import_legacy, list_valuations
    folder = tmp_path / "saved_analyses"
    (folder / "GOOGL_20250102_101010").mkdir(parents=True)
    (folder / "analyses_index.json").write_text(json.dumps({"GOOGL": {"GOOGL_20250102_101010": {
        "company_name": "Alphabet", "timestamp": "20250102_101010", "date": "2025-01-02"}}}))
    (folder / "GOOGL_20250102_101010" / "valuation_summary.json").write_text(json.dumps({
        "current_price": "168.40 USD", "mean_value": "189.00 USD", "median_value": "186.64 USD",
        "prob_undervalued": "80.1%", "VaR 95%": "150.2 USD", "Std. Deviation": "27.94 USD",
        "Variable Parameters": {"Growth 5y": "15.0% (±2.0%)", "WACC": "9.6% (±0.5%)"}}))
    st = Store(f"sqlite:///{tmp_path / 'l.db'}")
    assert import_legacy(st, folder) == {"imported": 1, "skipped": 0}
    row = list_valuations(st)[0]
    assert row["median"] == pytest.approx(186.64) and row["prob_above_price"] == pytest.approx(0.801)
    assert row["created_at"].startswith("2025-01-02")
