"""Robust number parsing for values typed by people or exported by spreadsheets.

Handles US (1,234.56) and European (1.234,56) formats, percentages, currency
symbols, unit suffixes (m, mm, bn, k, x) and accounting negatives "(123)".
The one genuinely ambiguous case, a single separator followed by exactly three
digits ("1.105", "4,235"), is resolved with a locale hint when available, then
with the value's context (leading zero, percent sign, expected magnitude).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

Locale = Literal["us", "eu"]

_CURRENCY = {"$": "USD", "US$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "CHF": "CHF",
             "kr": "DKK", "HK$": "HKD", "NT$": "TWD", "R$": "BRL", "₹": "INR", "₩": "KRW"}
_SCALE = [  # (regex on the trailing unit, multiplier to millions-or-units)
    (re.compile(r"\b(bn|b|billion|mil millones|mm€?)\b", re.I), 1e3),   # -> millions
    (re.compile(r"\b(m|mn|mio|million|millones|millions)\b", re.I), 1.0),
    (re.compile(r"\b(k|thousand|mil)\b", re.I), 1e-3),
]
_NUM = re.compile(r"[-+]?\(?\d[\d.,'   ]*\d|[-+]?\(?\d")


@dataclass
class Parsed:
    value: float
    is_percent: bool = False
    currency: str | None = None
    scale_to_millions: float | None = None  # set when a unit suffix was present
    ambiguous: bool = False


def detect_locale(samples: list[str]) -> Locale | None:
    """Guess the decimal separator from a batch of displayed values."""
    eu = us = 0
    for s in samples:
        if not isinstance(s, str):
            continue
        t = s.replace(" ", " ")
        if re.search(r"\d\.\d{3},\d", t) or re.search(r"\d,\d{1,2}\s*%", t) or re.search(r"^\s*-?\d+,\d{1,2}\s*(€|%|$)", t):
            eu += 1
        if re.search(r"\d,\d{3}\.\d", t) or re.search(r"\d\.\d{1,2}\s*%", t) or re.search(r"^\s*-?\$?\d+\.\d{1,2}\s*$", t):
            us += 1
    if eu > us:
        return "eu"
    if us > eu:
        return "us"
    return None


def parse_number(raw, locale: Locale | None = None, prefer: Literal["decimal", "thousands"] | None = None) -> Parsed | None:
    """Parse one cell. Returns None when no number is present.

    Percent values are returned as fractions (``"4,5%"`` -> 0.045, ``is_percent=True``).
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and math.isnan(raw):
            return None
        return Parsed(float(raw))
    s = str(raw).strip()
    if not s or s.lower() in {"nan", "n/a", "na", "-", "—", "#n/a", "#value!", "#ref!", "#div/0!"}:
        return None
    is_pct = "%" in s
    currency = None
    for sym, code in sorted(_CURRENCY.items(), key=lambda kv: -len(kv[0])):
        if sym in s:
            currency = code
            break
    scale = None
    tail = re.sub(r"[\d.,\s'\-+()%$€£¥]", " ", s)
    for rx, mult in _SCALE:
        if rx.search(tail):
            scale = mult
            break
    m = _NUM.search(s)
    if not m:
        return None
    tok = m.group(0)
    neg = tok.startswith("-") or (tok.startswith("(") and ")" in s[m.end():m.end() + 3])
    tok = tok.lstrip("+-(").replace(" ", "").replace(" ", "").replace(" ", "").replace("'", "")
    has_c, has_d = "," in tok, "." in tok
    ambiguous = False
    if has_c and has_d:
        if tok.rfind(",") > tok.rfind("."):
            tok = tok.replace(".", "").replace(",", ".")
        else:
            tok = tok.replace(",", "")
    elif has_c or has_d:
        sep = "," if has_c else "."
        parts = tok.split(sep)
        if len(parts) > 2:  # several of the same separator -> thousands
            tok = tok.replace(sep, "")
        else:
            int_part, frac = parts
            if len(frac) != 3:
                tok = int_part + "." + frac  # 1 or 2 (or 4+) decimals -> decimal separator
            else:
                # exactly three digits after a single separator: ambiguous
                if locale == "eu":
                    decimal = sep == ","
                elif locale == "us":
                    decimal = sep == "."
                elif int_part in ("0", ""):
                    decimal = True  # "0.125" is never a thousands group
                elif is_pct:
                    decimal = True  # "4.235%" -> 4.235 %
                elif prefer is not None:
                    decimal = prefer == "decimal"
                else:
                    decimal = False
                    ambiguous = True
                if is_pct or int_part in ("0", ""):
                    decimal = True
                tok = int_part + "." + frac if decimal else int_part + frac
    try:
        val = float(tok)
    except ValueError:
        return None
    if neg:
        val = -val
    if is_pct:
        val /= 100.0
    return Parsed(val, is_percent=is_pct, currency=currency, scale_to_millions=scale, ambiguous=ambiguous)
