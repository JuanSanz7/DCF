"""Validated input model for one valuation."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .distributions import Distribution, Fixed
from .parameters import PARAMETERS


class ParamInput(BaseModel):
    """Base (point) value plus the uncertainty around it."""
    model_config = ConfigDict(extra="forbid")

    value: float | None = None
    dist: Distribution = Field(default_factory=Fixed)
    source: str | None = None     # e.g. "sheet:GOOGL!B13", "yahoo:...", "manual"
    note: str | None = None


class CompanyInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str = Field(min_length=1, max_length=32)
    name: str = ""
    currency: str = Field(default="USD", min_length=3, max_length=3)
    yahoo_symbol: str | None = None
    as_of: str | None = None

    @field_validator("ticker", "currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage1_years: int = Field(default=5, ge=1, le=20)
    stage2_years: int = Field(default=5, ge=0, le=20)
    stage2_mode: Literal["flat", "fade"] = "flat"
    reinvestment_mode: Literal["rate", "roic"] = "rate"
    discount_mode: Literal["direct", "build_up"] = "direct"
    wacc_fade: bool = False
    mid_year: bool = False
    tax_on_losses: bool = False


class TerminalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # rf_linked: g = Rf (Damodaran cap); gordon: g is its own input; exit_multiple: EV/EBIT x year-N EBIT
    method: Literal["rf_linked", "gordon", "exit_multiple"] = "rf_linked"
    # market: WACC_T = cost of capital of a mature firm (Rf + beta_T x ERP, with optional debt);
    # direct: terminal_wacc input; explicit: same WACC as the last explicit year
    wacc_source: Literal["market", "direct", "explicit"] = "market"
    # equal_wacc: ROIC_T = WACC_T (no excess returns); spread: WACC_T + spread; absolute: input
    roic_mode: Literal["equal_wacc", "spread", "absolute"] = "equal_wacc"


class CountryRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    region: str
    weight: float = Field(ge=0, le=1)
    crp: float = Field(ge=0, le=0.3)


class Correlation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: str
    b: str
    rho: float = Field(ge=-0.99, le=0.99)


class SimulationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n: int = Field(default=20_000, ge=100, le=2_000_000)
    seed: int | None = None
    correlations: list[Correlation] = Field(default_factory=list)
    min_terminal_spread: float = Field(default=0.005, ge=0.0, le=0.05)


class ValuationInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: CompanyInfo
    params: dict[str, ParamInput] = Field(default_factory=dict)
    model: ModelSettings = Field(default_factory=ModelSettings)
    terminal: TerminalSettings = Field(default_factory=TerminalSettings)
    country_risk: list[CountryRisk] = Field(default_factory=list)
    simulation: SimulationSettings = Field(default_factory=SimulationSettings)

    @field_validator("params")
    @classmethod
    def _known(cls, v: dict[str, ParamInput]) -> dict[str, ParamInput]:
        unknown = sorted(set(v) - set(PARAMETERS))
        if unknown:
            raise ValueError(f"Unknown parameters: {', '.join(unknown)}")
        return v

    # ------------------------------------------------------------ helpers
    def base(self, key: str) -> float | None:
        p = self.params.get(key)
        if p is not None and p.value is not None:
            return p.value
        return PARAMETERS[key].default

    @property
    def crp_weighted(self) -> float:
        tot = sum(c.weight for c in self.country_risk)
        if tot <= 0:
            return 0.0
        return sum(c.weight * c.crp for c in self.country_risk) / tot


def active_parameters(inp: ValuationInputs) -> list[str]:
    """Parameters the current settings actually use, in display order."""
    m, t = inp.model, inp.terminal
    keys: list[str] = ["price", "shares", "ebit", "tax_rate", "growth_1"]
    has_s2 = m.stage2_years > 0
    if has_s2 and m.stage2_mode == "flat":
        keys.append("growth_2")
    if m.reinvestment_mode == "rate":
        keys.append("reinvestment_1")
        if has_s2 and m.stage2_mode == "flat":
            keys.append("reinvestment_2")
    else:
        keys.append("roic_1")
        if has_s2 and m.stage2_mode == "flat":
            keys.append("roic_2")

    needs_market = False
    if m.discount_mode == "direct":
        keys.append("wacc")
    else:
        keys += ["risk_free", "erp", "beta", "default_spread", "debt_weight"]

    if t.method in ("rf_linked", "gordon"):
        if t.method == "rf_linked":
            needs_market = True  # g = Rf
        else:
            keys.append("terminal_growth")
        if t.wacc_source == "market":
            needs_market = True
            keys += ["terminal_beta", "terminal_debt_weight"]
        elif t.wacc_source == "direct":
            keys.append("terminal_wacc")
        if t.roic_mode == "absolute":
            keys.append("terminal_roic")
        elif t.roic_mode == "spread":
            keys.append("terminal_roic_spread")
    else:
        keys.append("exit_multiple")
        if has_s2 and m.stage2_mode == "fade":
            keys.append("terminal_growth")  # fade target
    if m.wacc_fade and t.method != "exit_multiple" and t.wacc_source == "market":
        needs_market = True
    if needs_market:
        for k in ("risk_free", "erp"):
            if k not in keys:
                keys.append(k)
        if (inp.base("terminal_debt_weight") or 0) > 0 and "default_spread" not in keys:
            keys.append("default_spread")

    keys += ["cash", "debt", "non_operating_assets", "minority_interests", "lease_liabilities",
             "pension_deficit", "options_value", "failure_probability"]
    if (inp.base("failure_probability") or 0) > 0 or _is_random(inp, "failure_probability"):
        keys.append("distress_proceeds")
    # keep registry order
    order = list(PARAMETERS)
    return sorted(dict.fromkeys(keys), key=order.index)


def _is_random(inp: ValuationInputs, key: str) -> bool:
    p = inp.params.get(key)
    return bool(p and p.dist.is_random)
