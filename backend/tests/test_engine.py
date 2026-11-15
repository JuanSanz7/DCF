import numpy as np
import pytest

from dcfmc.core.engine import base_case, simulate
from dcfmc.core.inputs import ValuationInputs
from dcfmc.core.stats import summarize


def mk(mode="direct", **over):
    p = dict(price=354.3, shares=12309, ebit=171221.6, tax_rate=0.19, growth_1=0.18, growth_2=0.10,
             reinvestment_1=0.9, reinvestment_2=0.52, wacc=0.095899459892044, risk_free=0.0465, erp=0.0482,
             debt=98165, cash=242474, beta=1.05, default_spread=0.0055, debt_weight=98165 / 4459243.7)
    p.update(over.pop("params", {}))
    return ValuationInputs(company={"ticker": "GOOGL"}, params={k: {"value": v} for k, v in p.items()},
                           model={"discount_mode": mode, **over.pop("model", {})}, **over)


def test_golden_googl_direct():
    assert base_case(mk())["value_per_share"] == pytest.approx(241.975283106158, rel=1e-12)


def test_golden_googl_build_up():
    b = base_case(mk("build_up"))
    assert b["wacc"] == pytest.approx(0.095899459892044, rel=1e-12)
    assert b["value_per_share"] == pytest.approx(241.975283106158, rel=1e-12)
    assert b["tv_share"] == pytest.approx(0.797396019376728, rel=1e-9)


def test_golden_asml_template():
    inp = ValuationInputs(company={"ticker": "ASML", "currency": "EUR"}, params={k: {"value": v} for k, v in dict(
        price=1499.6, shares=386, ebit=14397.4, tax_rate=0.1758, growth_1=0.135, growth_2=0.08,
        reinvestment_1=0.381, reinvestment_2=0.28, wacc=0.0882705929516029, risk_free=0.0315, erp=0.0417,
        debt=3720, cash=7582).items()})
    assert base_case(inp)["value_per_share"] == pytest.approx(766.148178770599, rel=1e-12)


def test_simulation_centres_on_base_with_tiny_noise():
    d = mk(params={}, simulation={"n": 4000, "seed": 1}).model_dump(by_alias=True)
    d["params"]["growth_1"]["dist"] = {"kind": "normal", "mean": 0.18, "sd": 1e-6}
    inp = ValuationInputs.model_validate(d)
    out = simulate(inp)
    v = out.paths["value_per_share"]
    assert np.median(v) == pytest.approx(241.9753, rel=1e-4)


def test_seed_reproducible():
    d = mk(simulation={"n": 2000, "seed": 7}).model_dump(by_alias=True)
    d["params"]["growth_1"]["dist"] = {"kind": "pert", "low": 0.14, "mode": 0.18, "high": 0.24}
    inp = ValuationInputs.model_validate(d)
    a = simulate(inp).paths["value_per_share"]
    b = simulate(inp).paths["value_per_share"]
    assert np.array_equal(a, b)


def test_bad_terminal_paths_are_flagged():
    inp = mk("build_up", simulation={"n": 5000, "seed": 3, "min_terminal_spread": 0.02})
    d = inp.model_dump(by_alias=True)
    d["params"]["erp"]["dist"] = {"kind": "normal", "mean": 0.0482, "sd": 0.03}
    out = simulate(ValuationInputs.model_validate(d))
    s = summarize(out)
    assert s["invalid_fraction"] > 0          # ERP < 2% -> terminal spread below the floor
    assert "erp" in s["clipped"]              # negative ERP draws clipped at the hard min
    assert np.isfinite(s["mean"])


def test_correlation_is_applied():
    d = mk(simulation={"n": 20000, "seed": 11, "correlations": [{"a": "growth_1", "b": "reinvestment_1", "rho": 0.8}]}
           ).model_dump(by_alias=True)
    d["params"]["growth_1"]["dist"] = {"kind": "normal", "mean": 0.18, "sd": 0.03}
    d["params"]["reinvestment_1"]["dist"] = {"kind": "truncnormal", "mean": 0.9, "sd": 0.1, "low": 0.5, "high": 1.3}
    out = simulate(ValuationInputs.model_validate(d))
    from scipy.stats import spearmanr
    rho = spearmanr(out.draws.values["growth_1"], out.draws.values["reinvestment_1"]).statistic
    assert rho == pytest.approx(0.8, abs=0.03)


def test_roic_mode_links_reinvestment():
    d = mk(model={"reinvestment_mode": "roic"}, params={"roic_1": 0.2, "roic_2": 0.192}).model_dump(by_alias=True)
    b = base_case(ValuationInputs.model_validate(d))
    t = b["table"]
    assert t["reinvestment"][0] == pytest.approx(0.18 / 0.2)
    assert t["reinvestment"][-1] == pytest.approx(0.10 / 0.192)


def test_fade_reaches_terminal_growth():
    b = base_case(mk(model={"stage2_mode": "fade"}))
    assert b["table"]["growth"][-1] == pytest.approx(0.0465)


def test_mid_year_raises_value():
    a = base_case(mk())["value_per_share"]
    b = base_case(mk(model={"mid_year": True}))["value_per_share"]
    assert b > a


def test_exit_multiple():
    inp = mk(terminal={"method": "exit_multiple"}, params={"exit_multiple": 15})
    b = base_case(inp)
    ebit_N = b["table"]["nopat"][-1] / (1 - 0.19)
    assert b["tv"] == pytest.approx(15 * ebit_N)


def test_failure_probability_expected_value():
    base = base_case(mk())["value_per_share"]
    b = base_case(mk(params={"failure_probability": 0.2, "distress_proceeds": 0.0}))
    distress_equity = max(0 + 242474 - 98165, 0) / 12309
    assert b["value_per_share"] == pytest.approx(0.8 * base + 0.2 * distress_equity)


def test_non_operating_assets_add_value():
    b = base_case(mk(params={"non_operating_assets": 131461}))
    assert b["value_per_share"] == pytest.approx(252.655354598562, rel=1e-9)  # sheet memo line


def test_summary_shapes():
    d = mk("build_up", simulation={"n": 6000, "seed": 5}).model_dump(by_alias=True)
    d["params"]["growth_1"]["dist"] = {"kind": "lognormal", "mean": 0.18, "sd": 0.04, "bound": 0.08, "side": "lower"}
    d["params"]["beta"]["dist"] = {"kind": "truncnormal", "mean": 1.05, "sd": 0.12, "low": 0.6, "high": 1.6}
    d["params"]["risk_free"]["dist"] = {"kind": "truncnormal", "mean": 0.0465, "sd": 0.005, "low": 0.03, "high": 0.07}
    s = summarize(simulate(ValuationInputs.model_validate(d)))
    assert 0 <= s["prob_above_price"] <= 1
    assert len(s["histogram"]["counts"]) == 70
    assert {t["key"] for t in s["tornado"]} == {"growth_1", "beta", "risk_free"}
    assert s["heatmaps"] and len(s["heatmaps"][0]["median"]) == 10
    assert s["percentiles"]["p5"] < s["median"] < s["percentiles"]["p95"]
