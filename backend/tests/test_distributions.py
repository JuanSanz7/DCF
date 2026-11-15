import numpy as np
import pytest
from pydantic import TypeAdapter, ValidationError

from dcfmc.core.distributions import Distribution

TA = TypeAdapter(Distribution)
U = (np.arange(20000) + 0.5) / 20000


@pytest.mark.parametrize("spec,mean", [
    ({"kind": "normal", "mean": 0.1, "sd": 0.02}, 0.1),
    ({"kind": "truncnormal", "mean": 0.1, "sd": 0.02, "low": 0.0, "high": 0.2}, 0.1),
    ({"kind": "lognormal", "mean": 0.1, "sd": 0.03, "bound": 0.0}, 0.1),
    ({"kind": "lognormal", "mean": 0.1, "sd": 0.03, "bound": 0.2, "side": "upper"}, 0.1),
    ({"kind": "triangular", "low": 0.0, "mode": 0.1, "high": 0.2}, 0.1),
    ({"kind": "pert", "low": 0.0, "mode": 0.1, "high": 0.2}, 0.1),
    ({"kind": "uniform", "low": 0.0, "high": 0.2}, 0.1),
    ({"kind": "student_t", "mean": 0.1, "sd": 0.02, "df": 5}, 0.1),
    ({"kind": "discrete", "values": [0.0, 0.2], "probs": [1, 1]}, 0.1),
    ({"kind": "empirical", "values": [0.05, 0.1, 0.15]}, 0.1),
])
def test_means(spec, mean):
    d = TA.validate_python(spec)
    assert float(np.mean(d.ppf(U))) == pytest.approx(mean, abs=2e-3)


def test_skew_direction():
    lo = TA.validate_python({"kind": "lognormal", "mean": 0.1, "sd": 0.05, "bound": 0.0})
    up = TA.validate_python({"kind": "lognormal", "mean": 0.1, "sd": 0.05, "bound": 0.2, "side": "upper"})
    x, y = lo.ppf(U), up.ppf(U)
    assert np.median(x) < 0.1 < np.median(y)
    assert x.min() > 0 and y.max() < 0.2


@pytest.mark.parametrize("spec", [
    {"kind": "triangular", "low": 1, "mode": 0, "high": 2},
    {"kind": "uniform", "low": 1, "high": 1},
    {"kind": "normal", "mean": 0, "sd": -1},
    {"kind": "lognormal", "mean": -0.1, "sd": 0.1, "bound": 0},
    {"kind": "discrete", "values": [1, 2], "probs": [1]},
])
def test_invalid(spec):
    with pytest.raises(ValidationError):
        TA.validate_python(spec)


def test_serialises_with_alias():
    d = TA.validate_python({"kind": "normal", "mean": 0.1, "sd": 0.02})
    assert d.model_dump()["mean"] == 0.1
