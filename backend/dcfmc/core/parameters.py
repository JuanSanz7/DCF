"""Registry of every model parameter: meaning, unit, bounds and guidance.

`hard_min`/`hard_max` are physical or logical limits: base values outside them
are rejected and simulated draws are clipped to them. `soft_min`/`soft_max`
mark the "plausible" band: values outside raise a warning, not an error.

The help texts paraphrase the valuation logic taught by Aswath Damodaran
(NYU Stern) in his books, class lectures and blog; they are guidance, not
rules.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .units import Unit


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    group: str
    unit: Unit
    description: str
    help: str = ""
    hard_min: float | None = None
    hard_max: float | None = None
    soft_min: float | None = None
    soft_max: float | None = None
    default: float | None = None
    category: str = "generic"          # used by the distribution advisor
    stochastic_by_default: bool = False
    allow_zero: bool = True
    required: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["unit"] = self.unit.value
        d["tags"] = list(self.tags)
        return d


GROUPS: dict[str, str] = {
    "market": "Company & market",
    "operating": "Operating base",
    "growth": "Growth & reinvestment",
    "discount": "Discount rate",
    "terminal": "Terminal value",
    "bridge": "Equity bridge",
    "risk": "Distress risk",
}

_P = ParamSpec

PARAMETERS: dict[str, ParamSpec] = {p.key: p for p in [
    # ---------------------------------------------------------------- market
    _P("price", "Market price", "market", Unit.PRICE,
       "Current market price per share, in the valuation currency.",
       "Only used to compare against the intrinsic value. If the listing currency differs from the "
       "reporting currency (ADRs, dual listings) convert either the price or every money amount so "
       "both are in the same currency.",
       hard_min=1e-9, allow_zero=False, required=True, category="price"),
    _P("shares", "Shares outstanding (diluted)", "market", Unit.SHARES_M,
       "Diluted share count in millions, consistent with the price (ADS-equivalent for ADRs).",
       "Damodaran prefers the primary share count plus a separate value for options; using the "
       "diluted count is the common shortcut. For ADRs use the count implied by market cap / price, "
       "otherwise the ADR ratio silently scales the value per share.",
       hard_min=1e-9, allow_zero=False, required=True, category="shares"),
    # ------------------------------------------------------------- operating
    _P("ebit", "Base operating income (EBIT)", "operating", Unit.MONEY_M,
       "Starting EBIT (TTM or last year), normalised and with R&D capitalised where it applies.",
       "Normalise one-offs, but keep charges that recur in practice. Capitalising R&D (Damodaran) "
       "moves R&D from an expense to an investment: EBIT + R&D(current) - amortisation of the "
       "research asset. A distribution here captures uncertainty about 'true' normalised earnings.",
       required=True, category="operating_base", soft_min=1e-9),
    _P("tax_rate", "Tax rate", "operating", Unit.PERCENT,
       "Tax rate applied to EBIT to get NOPAT, constant over the forecast.",
       "Damodaran uses the effective rate early on and moves toward the marginal (statutory) rate "
       "over time, because deferrals and incentives don't last forever. A distribution skewed toward "
       "the marginal rate reflects that.",
       hard_min=0.0, hard_max=0.6, soft_min=0.05, soft_max=0.35, default=0.21, required=True,
       category="tax"),
    # ---------------------------------------------------------------- growth
    _P("growth_1", "NOPAT growth, stage 1", "growth", Unit.PERCENT,
       "Annual growth of NOPAT during the high-growth stage (years 1-N1).",
       "Growth has to be paid for: g = ROIC x reinvestment rate. Check the implied ROIC. Revenue "
       "growth is usually positively skewed (rare big upside, a floor on the downside), which is why "
       "Damodaran used a lognormal for Apple's growth.",
       hard_min=-0.6, hard_max=1.5, soft_min=-0.1, soft_max=0.4, required=True,
       category="growth", stochastic_by_default=True),
    _P("growth_2", "NOPAT growth, stage 2", "growth", Unit.PERCENT,
       "Annual NOPAT growth in the transition stage (years N1+1 to N). Ignored when stage 2 fades.",
       "Should sit between stage-1 growth and the terminal growth rate. Fading linearly to the "
       "terminal rate is the Damodaran default and avoids a cliff in year N+1.",
       hard_min=-0.6, hard_max=1.5, soft_min=-0.05, soft_max=0.25, category="growth",
       stochastic_by_default=True),
    _P("reinvestment_1", "Reinvestment rate, stage 1", "growth", Unit.PERCENT,
       "Share of NOPAT reinvested (net capex + working capital + R&D) in stage 1.",
       "Reinvestment is bounded below by maintenance needs and above by funding capacity; values "
       "above 100% mean negative FCFF (funded by cash or new capital). Implied ROIC = g / RR.",
       hard_min=-1.0, hard_max=3.0, soft_min=0.0, soft_max=1.2, category="reinvestment",
       stochastic_by_default=True),
    _P("reinvestment_2", "Reinvestment rate, stage 2", "growth", Unit.PERCENT,
       "Share of NOPAT reinvested in stage 2.",
       "Usually moves toward the terminal reinvestment rate g / ROIC_terminal.",
       hard_min=-1.0, hard_max=3.0, soft_min=0.0, soft_max=1.0, category="reinvestment",
       stochastic_by_default=True),
    _P("roic_1", "Return on new capital, stage 1", "growth", Unit.PERCENT,
       "Marginal ROIC on new investment in stage 1 (ROIC mode: reinvestment = g / ROIC).",
       "Linking growth and reinvestment through ROIC keeps every simulated path internally "
       "consistent: a path with high growth automatically needs more reinvestment. ROIC is "
       "positive and right-skewed, so lognormal or PERT shapes fit better than a normal.",
       hard_min=0.005, hard_max=3.0, soft_min=0.03, soft_max=0.6, category="roic",
       stochastic_by_default=True),
    _P("roic_2", "Return on new capital, stage 2", "growth", Unit.PERCENT,
       "Marginal ROIC on new investment in stage 2.",
       "Competition erodes excess returns: ROIC normally moves toward the cost of capital.",
       hard_min=0.005, hard_max=3.0, soft_min=0.03, soft_max=0.5, category="roic",
       stochastic_by_default=True),
    # -------------------------------------------------------------- discount
    _P("wacc", "Cost of capital (WACC)", "discount", Unit.PERCENT,
       "Weighted average cost of capital for the explicit period (direct mode).",
       "In build-up mode the WACC is computed from Rf, beta, ERP and the debt spread instead, so "
       "simulated WACC moves consistently with the risk-free rate and the terminal value.",
       hard_min=0.01, hard_max=0.4, soft_min=0.05, soft_max=0.15, category="wacc"),
    _P("risk_free", "Risk-free rate", "discount", Unit.PERCENT,
       "Long-term government bond yield in the valuation currency (default-free).",
       "Must match the currency of the cash flows. For currencies with sovereign default risk, "
       "subtract the sovereign default spread from the government bond yield. It also caps the "
       "terminal growth rate.",
       hard_min=-0.02, hard_max=0.25, soft_min=0.0, soft_max=0.08, category="risk_free",
       stochastic_by_default=True),
    _P("erp", "Equity risk premium (mature)", "discount", Unit.PERCENT,
       "Mature-market equity risk premium; country risk premiums are added separately.",
       "Damodaran estimates an implied ERP from S&P 500 prices and expected cash flows every month. "
       "It is bounded well above zero; a normal with a large standard deviation can push the "
       "terminal spread to ~0 and blow up the terminal value.",
       hard_min=0.01, hard_max=0.2, soft_min=0.03, soft_max=0.08, category="erp",
       stochastic_by_default=True),
    _P("beta", "Levered beta", "discount", Unit.RATIO,
       "Equity beta used in the cost of equity (Ke = Rf + beta x ERP).",
       "Damodaran prefers bottom-up betas (industry unlevered beta, relevered at the company's D/E) "
       "because regression betas have large standard errors (often 0.1-0.3).",
       hard_min=0.05, hard_max=4.0, soft_min=0.5, soft_max=2.0, default=1.0, category="beta",
       stochastic_by_default=True),
    _P("default_spread", "Default spread", "discount", Unit.PERCENT,
       "Spread over Rf for the company's debt (from the rating or a synthetic rating).",
       "Second-order input unless the company is heavily indebted.",
       hard_min=0.0, hard_max=0.3, soft_min=0.0, soft_max=0.1, default=0.01,
       category="spread"),
    _P("debt_weight", "Debt weight D/(D+E)", "discount", Unit.PERCENT,
       "Debt share of capital at market values, used in the WACC.",
       "Use market value of equity and (book or market) value of debt including leases. "
       "Left empty, it is computed as debt / (debt + price x shares).",
       hard_min=0.0, hard_max=0.95, soft_min=0.0, soft_max=0.6, default=None,
       category="weight"),
    # -------------------------------------------------------------- terminal
    _P("terminal_growth", "Terminal growth", "terminal", Unit.PERCENT,
       "Perpetual growth after year N (Gordon method).",
       "No firm can grow forever faster than the economy; Damodaran caps stable growth at the "
       "risk-free rate, which proxies nominal growth in the long run.",
       hard_min=-0.05, hard_max=0.15, soft_min=-0.01, soft_max=0.05, category="terminal_growth"),
    _P("terminal_roic", "Terminal ROIC", "terminal", Unit.PERCENT,
       "Return on new capital in perpetuity (absolute mode). Reinvestment = g / ROIC.",
       "Setting ROIC = cost of capital means growth adds no value in perpetuity, the conservative "
       "Damodaran default. Firms with durable moats can justify a modest excess return.",
       hard_min=0.005, hard_max=2.0, soft_min=0.04, soft_max=0.3, category="roic"),
    _P("terminal_roic_spread", "Terminal excess return", "terminal", Unit.PERCENT,
       "ROIC minus WACC in perpetuity (spread mode).",
       "0% = no excess returns. Positive values describe a moat that never fully erodes.",
       hard_min=-0.1, hard_max=0.5, soft_min=0.0, soft_max=0.1, default=0.0,
       category="roic_spread"),
    _P("terminal_beta", "Terminal beta", "terminal", Unit.RATIO,
       "Beta in stable growth; mature firms move toward 1.",
       "Damodaran moves betas toward one in stable growth: a stable firm looks like the market.",
       hard_min=0.3, hard_max=2.5, soft_min=0.8, soft_max=1.2, default=1.0, category="beta"),
    _P("terminal_debt_weight", "Terminal debt weight", "terminal", Unit.PERCENT,
       "D/(D+E) in stable growth (0 reproduces the template: terminal WACC = Rf + beta x ERP).",
       "Mature firms tend to carry more debt; moving toward the industry average is common.",
       hard_min=0.0, hard_max=0.9, soft_min=0.0, soft_max=0.5, default=0.0, category="weight"),
    _P("terminal_wacc", "Terminal WACC", "terminal", Unit.PERCENT,
       "Cost of capital in perpetuity (Gordon method with a direct terminal WACC).",
       "Should be close to the cost of capital of a mature firm in the same business.",
       hard_min=0.02, hard_max=0.3, soft_min=0.05, soft_max=0.12, category="wacc"),
    _P("exit_multiple", "Exit multiple (EV/EBIT)", "terminal", Unit.MULTIPLE,
       "EV / EBIT applied to year-N EBIT (exit-multiple method).",
       "Damodaran warns this turns a DCF into a relative valuation: the multiple embeds growth, risk "
       "and return assumptions that are no longer visible. Use as a cross-check.",
       hard_min=0.5, hard_max=100.0, soft_min=5.0, soft_max=30.0, category="multiple"),
    # ---------------------------------------------------------------- bridge
    _P("cash", "Cash & short-term investments", "bridge", Unit.MONEY_M,
       "Cash, equivalents and marketable securities, added to operating value.",
       "Trapped cash (foreign subsidiaries, minimum operating cash) can deserve a discount.",
       hard_min=0.0, default=0.0, category="money_fixed"),
    _P("debt", "Total debt", "bridge", Unit.MONEY_M,
       "Interest-bearing debt subtracted from enterprise value (include leases if not below).",
       "Damodaran treats lease commitments as debt; add them here or in 'Lease liabilities'.",
       hard_min=0.0, default=0.0, category="money_fixed"),
    _P("non_operating_assets", "Non-operating assets", "bridge", Unit.MONEY_M,
       "Equity stakes, unconsolidated holdings and other assets whose income is not in EBIT.",
       "Value cross-holdings at market when listed; illiquid private stakes deserve a haircut and "
       "a wide, downward-skewed distribution.",
       hard_min=0.0, default=0.0, category="nonop"),
    _P("minority_interests", "Minority interests", "bridge", Unit.MONEY_M,
       "Share of consolidated subsidiaries owned by others, subtracted from value.",
       "Ideally at market value (book value times an industry price-to-book).",
       hard_min=0.0, default=0.0, category="money_fixed"),
    _P("lease_liabilities", "Lease liabilities", "bridge", Unit.MONEY_M,
       "Lease debt not already inside 'Total debt'.",
       "", hard_min=0.0, default=0.0, category="money_fixed"),
    _P("pension_deficit", "Unfunded pensions & other claims", "bridge", Unit.MONEY_M,
       "Debt-like claims: unfunded pensions, litigation, etc.",
       "", hard_min=0.0, default=0.0, category="money_fixed"),
    _P("options_value", "Employee options value", "bridge", Unit.MONEY_M,
       "Value of outstanding employee options/RSUs, if shares are not fully diluted.",
       "Leave at 0 when the share count is already diluted to avoid double counting.",
       hard_min=0.0, default=0.0, category="money_fixed"),
    # ------------------------------------------------------------------ risk
    _P("failure_probability", "Probability of failure", "risk", Unit.PROBABILITY,
       "Chance the firm does not survive as a going concern (discrete risk).",
       "Damodaran values distress separately from the going-concern DCF: "
       "value = (1 - p) x going concern + p x distress proceeds. In the simulation each path "
       "fails with probability p, so the distribution shows the left tail explicitly.",
       hard_min=0.0, hard_max=0.99, soft_min=0.0, soft_max=0.5, default=0.0, category="prob"),
    _P("distress_proceeds", "Distress proceeds (% of EV)", "risk", Unit.PERCENT,
       "Value recovered in distress as a fraction of the going-concern enterprise value.",
       "Fire-sale discounts of 25-50% are common; equity is what is left after paying debt.",
       hard_min=0.0, hard_max=1.5, soft_min=0.2, soft_max=0.8, default=0.5, category="prob"),
]}


def get(key: str) -> ParamSpec:
    try:
        return PARAMETERS[key]
    except KeyError as exc:  # pragma: no cover - programming error
        raise KeyError(f"Unknown parameter '{key}'") from exc


def registry() -> dict:
    return {
        "groups": GROUPS,
        "parameters": [p.to_dict() for p in PARAMETERS.values()],
    }
