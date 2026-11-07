"""Units used by model parameters.

Internally every rate is stored as a decimal fraction (0.0465 = 4.65 %), every
money amount in millions of the valuation currency, the share count in
millions, and prices in currency units per share. The UI converts for display.
"""
from __future__ import annotations

from enum import Enum


class Unit(str, Enum):
    PERCENT = "percent"        # stored as fraction, displayed x100 with "%"
    MONEY_M = "money_m"        # millions of valuation currency
    PRICE = "price"            # currency per share
    SHARES_M = "shares_m"      # millions of shares
    RATIO = "ratio"            # plain number, e.g. beta
    MULTIPLE = "multiple"      # valuation multiple, e.g. 15x
    YEARS = "years"
    PROBABILITY = "probability"  # stored as fraction, displayed as %

    @property
    def display_factor(self) -> float:
        return 100.0 if self in (Unit.PERCENT, Unit.PROBABILITY) else 1.0

    @property
    def suffix(self) -> str:
        return {
            Unit.PERCENT: "%",
            Unit.PROBABILITY: "%",
            Unit.MONEY_M: "m",
            Unit.PRICE: "",
            Unit.SHARES_M: "m sh",
            Unit.RATIO: "",
            Unit.MULTIPLE: "x",
            Unit.YEARS: "y",
        }[self]

    def to_display(self, value: float | None) -> float | None:
        return None if value is None else value * self.display_factor

    def from_display(self, value: float | None) -> float | None:
        return None if value is None else value / self.display_factor
