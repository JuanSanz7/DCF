"""Probability distributions for model inputs.

Every distribution is sampled through its inverse CDF (``ppf``) from uniform
numbers. That lets the engine impose correlations with a Gaussian copula for
any mix of shapes: correlated normals -> uniforms -> each input's own ppf.

All parameters are in the parameter's canonical unit (fractions for rates).
"""
from __future__ import annotations

import math
from typing import Annotated, Literal, Union

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy import stats

_EPS = 1e-12


class _Dist(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    def ppf(self, u: np.ndarray) -> np.ndarray:  # pragma: no cover - abstract
        raise NotImplementedError

    def mean(self) -> float:
        u = (np.arange(20000) + 0.5) / 20000
        return float(np.mean(self.ppf(u)))

    def std(self) -> float:
        u = (np.arange(20000) + 0.5) / 20000
        return float(np.std(self.ppf(u)))

    @property
    def is_random(self) -> bool:
        return True

    def quantiles(self, qs=(0.05, 0.10, 0.50, 0.90, 0.95)) -> dict[str, float]:
        vals = self.ppf(np.asarray(qs, dtype=float))
        return {f"p{int(round(q * 100))}": float(v) for q, v in zip(qs, vals)}

    def density(self, points: int = 120) -> dict:
        """x/y points for a preview chart (a smoothed histogram of the ppf)."""
        u = (np.arange(4000) + 0.5) / 4000
        x = self.ppf(u)
        lo, hi = float(np.quantile(x, 0.0025)), float(np.quantile(x, 0.9975))
        if hi - lo < _EPS:
            return {"x": [lo], "y": [1.0], "discrete": True}
        hist, edges = np.histogram(x, bins=min(points, 60), range=(lo, hi), density=True)
        centers = 0.5 * (edges[:-1] + edges[1:])
        return {"x": centers.tolist(), "y": hist.tolist(), "discrete": False}

    def label(self) -> str:  # pragma: no cover - overridden
        return self.__class__.__name__


class Fixed(_Dist):
    kind: Literal["fixed"] = "fixed"

    @property
    def is_random(self) -> bool:
        return False

    def ppf(self, u):  # value supplied by the engine (base value)
        raise RuntimeError("Fixed distributions are resolved to the base value by the engine")

    def label(self) -> str:
        return "Fixed"


class Normal(_Dist):
    kind: Literal["normal"] = "normal"
    mean_: float = Field(alias="mean")
    sd: float = Field(ge=0)

    def ppf(self, u):
        return self.mean_ + self.sd * stats.norm.ppf(u)

    def label(self) -> str:
        return "Normal"


class TruncNormal(_Dist):
    kind: Literal["truncnormal"] = "truncnormal"
    mean_: float = Field(alias="mean")
    sd: float = Field(gt=0)
    low: float
    high: float

    @model_validator(mode="after")
    def _check(self):
        if not self.low < self.high:
            raise ValueError("truncnormal: low must be < high")
        return self

    def ppf(self, u):
        a = (self.low - self.mean_) / self.sd
        b = (self.high - self.mean_) / self.sd
        return stats.truncnorm.ppf(u, a, b, loc=self.mean_, scale=self.sd)

    def label(self) -> str:
        return "Truncated normal"


class LogNormal(_Dist):
    """Shifted lognormal: X = bound + LN (side='lower', right skew) or
    X = bound - LN (side='upper', left skew). `mean`/`sd` are of X itself."""
    kind: Literal["lognormal"] = "lognormal"
    mean_: float = Field(alias="mean")
    sd: float = Field(gt=0)
    bound: float = 0.0
    side: Literal["lower", "upper"] = "lower"

    @model_validator(mode="after")
    def _check(self):
        m = self.mean_ - self.bound if self.side == "lower" else self.bound - self.mean_
        if m <= 0:
            raise ValueError("lognormal: the mean must lie on the open side of the bound")
        return self

    def _params(self):
        m = self.mean_ - self.bound if self.side == "lower" else self.bound - self.mean_
        s2 = math.log(1.0 + (self.sd / m) ** 2)
        mu = math.log(m) - s2 / 2
        return mu, math.sqrt(s2)

    def ppf(self, u):
        mu, s = self._params()
        y = np.exp(mu + s * stats.norm.ppf(u))
        return self.bound + y if self.side == "lower" else self.bound - y

    def label(self) -> str:
        return "Lognormal"


class Triangular(_Dist):
    kind: Literal["triangular"] = "triangular"
    low: float
    mode: float
    high: float

    @model_validator(mode="after")
    def _check(self):
        if not (self.low <= self.mode <= self.high and self.low < self.high):
            raise ValueError("triangular: need low <= mode <= high and low < high")
        return self

    def ppf(self, u):
        c = (self.mode - self.low) / (self.high - self.low)
        return stats.triang.ppf(u, c, loc=self.low, scale=self.high - self.low)

    def label(self) -> str:
        return "Triangular"


class Pert(_Dist):
    kind: Literal["pert"] = "pert"
    low: float
    mode: float
    high: float
    lam: float = Field(default=4.0, gt=0, description="Shape: higher = more peaked around the mode")

    @model_validator(mode="after")
    def _check(self):
        if not (self.low <= self.mode <= self.high and self.low < self.high):
            raise ValueError("pert: need low <= mode <= high and low < high")
        return self

    def ppf(self, u):
        r = self.high - self.low
        a = 1 + self.lam * (self.mode - self.low) / r
        b = 1 + self.lam * (self.high - self.mode) / r
        return self.low + r * stats.beta.ppf(u, a, b)

    def label(self) -> str:
        return "PERT"


class Uniform(_Dist):
    kind: Literal["uniform"] = "uniform"
    low: float
    high: float

    @model_validator(mode="after")
    def _check(self):
        if not self.low < self.high:
            raise ValueError("uniform: low must be < high")
        return self

    def ppf(self, u):
        return self.low + (self.high - self.low) * np.asarray(u)

    def label(self) -> str:
        return "Uniform"


class StudentT(_Dist):
    """Fat-tailed symmetric distribution; `sd` is the true standard deviation."""
    kind: Literal["student_t"] = "student_t"
    mean_: float = Field(alias="mean")
    sd: float = Field(gt=0)
    df: float = Field(default=5.0, gt=2.0)

    def ppf(self, u):
        scale = self.sd * math.sqrt((self.df - 2) / self.df)
        return self.mean_ + scale * stats.t.ppf(u, self.df)

    def label(self) -> str:
        return "Student-t"


class Discrete(_Dist):
    kind: Literal["discrete"] = "discrete"
    values: list[float] = Field(min_length=1)
    probs: list[float] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self):
        if len(self.values) != len(self.probs):
            raise ValueError("discrete: values and probs must have the same length")
        if any(p < 0 for p in self.probs) or sum(self.probs) <= 0:
            raise ValueError("discrete: probabilities must be >= 0 and not all zero")
        return self

    def ppf(self, u):
        p = np.asarray(self.probs, dtype=float)
        cdf = np.cumsum(p / p.sum())
        idx = np.searchsorted(cdf, np.asarray(u), side="right")
        return np.asarray(self.values, dtype=float)[np.clip(idx, 0, len(self.values) - 1)]

    def density(self, points: int = 120) -> dict:
        p = np.asarray(self.probs, dtype=float)
        return {"x": list(map(float, self.values)), "y": (p / p.sum()).tolist(), "discrete": True}

    def label(self) -> str:
        return "Discrete"


class Empirical(_Dist):
    """Resamples observed data (history or peers), optionally interpolating."""
    kind: Literal["empirical"] = "empirical"
    values: list[float] = Field(min_length=2)
    smooth: bool = True

    def ppf(self, u):
        method = "linear" if self.smooth else "inverted_cdf"
        return np.quantile(np.asarray(self.values, dtype=float), np.asarray(u), method=method)

    def label(self) -> str:
        return "Empirical"


Distribution = Annotated[
    Union[Fixed, Normal, TruncNormal, LogNormal, Triangular, Pert, Uniform, StudentT, Discrete, Empirical],
    Field(discriminator="kind"),
]

DIST_CATALOG: list[dict] = [
    {"kind": "fixed", "label": "Fixed", "fields": [],
     "when": "Inputs you know well or whose effect on value is small. Damodaran: simulate only the "
             "few drivers that matter; varying everything adds noise, not insight."},
    {"kind": "normal", "label": "Normal", "fields": ["mean", "sd"],
     "when": "Symmetric, unbounded uncertainty around an expected value. Avoid for bounded "
             "inputs (rates near zero, reinvestment) where tails become impossible values."},
    {"kind": "truncnormal", "label": "Truncated normal", "fields": ["mean", "sd", "low", "high"],
     "when": "Symmetric around the base case but with hard limits (ERP, beta, reinvestment). "
             "Note: 'mean' is the centre of the parent normal."},
    {"kind": "lognormal", "label": "Lognormal (shifted)", "fields": ["mean", "sd", "bound", "side"],
     "when": "Skewed inputs with a floor (side=lower: rare big upside, e.g. growth, ROIC, "
             "multiples) or a cap (side=upper: rare big downside). Damodaran used a lognormal "
             "for Apple's revenue growth."},
    {"kind": "triangular", "label": "Triangular", "fields": ["low", "mode", "high"],
     "when": "You can state a minimum, most-likely and maximum value. Bounded, can be skewed. "
             "Damodaran used it for Apple's operating margin so margins could not run to "
             "infinity."},
    {"kind": "pert", "label": "PERT", "fields": ["low", "mode", "high", "lam"],
     "when": "Like triangular but smoother and with more weight near the most-likely value: "
             "the best default when you have a range (low/base/high) from your research."},
    {"kind": "uniform", "label": "Uniform", "fields": ["low", "high"],
     "when": "You only know the range, not where in it the value is most likely (Damodaran's "
             "example: margins anywhere between two bounds)."},
    {"kind": "student_t", "label": "Student-t", "fields": ["mean", "sd", "df"],
     "when": "Symmetric but fat-tailed: large surprises happen more often than a normal implies. "
             "Lower df = fatter tails."},
    {"kind": "discrete", "label": "Discrete", "fields": ["values", "probs"],
     "when": "A few distinct outcomes (a tax regime, a regulatory decision, a contract won or "
             "lost). Damodaran: discrete risks are better handled as discrete outcomes."},
    {"kind": "empirical", "label": "Empirical (data)", "fields": ["values", "smooth"],
     "when": "You have historical or cross-sectional data (past growth rates, peer margins) and "
             "prefer the data's own shape over a fitted curve. Assumes the past is "
             "representative (no structural break)."},
]


def describe(dist: _Dist) -> dict:
    """Summary used by the UI for previews."""
    if not dist.is_random:
        return {"kind": "fixed", "label": "Fixed"}
    q = dist.quantiles()
    return {"kind": dist.kind, "label": dist.label(), "mean": dist.mean(), "sd": dist.std(),
            **q, "density": dist.density()}
