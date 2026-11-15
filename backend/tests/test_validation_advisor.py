from dcfmc.core import advisor
from dcfmc.core.inputs import ValuationInputs
from dcfmc.core.parameters import PARAMETERS
from dcfmc.core.validation import validate
from test_engine import mk


def codes(inp):
    return {i.code for i in validate(inp)}


def test_missing_required():
    inp = ValuationInputs(company={"ticker": "X"}, params={})
    assert "missing" in codes(inp)


def test_terminal_spread_error():
    inp = mk(terminal={"method": "gordon", "wacc_source": "direct"},
             params={"terminal_growth": 0.09, "terminal_wacc": 0.092})
    assert "terminal_spread" in codes(inp)


def test_implied_roic_warning():
    assert "implied_roic" in codes(mk(params={"reinvestment_1": 0.1}))


def test_unanchored_distribution():
    d = mk().model_dump(by_alias=True)
    d["params"]["growth_1"]["dist"] = {"kind": "normal", "mean": 0.30, "sd": 0.02}
    assert "not_anchored" in codes(ValuationInputs.model_validate(d))


def test_advisor_every_param():
    for key in PARAMETERS:
        s = advisor.suggest(key, 0.1)
        assert s["suggestions"] and s["suggestions"][0]["recommended"]


def test_advisor_uses_range():
    s = advisor.suggest("reinvestment_1", 0.9, 0.7, 1.1)
    assert s["suggestions"][0]["dist"]["kind"] == "pert"
