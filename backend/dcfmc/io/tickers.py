"""Ticker conversions between Google Finance ("EXCH:SYM") and Yahoo Finance."""
from __future__ import annotations

import re

# Google Finance exchange prefix -> Yahoo suffix ("" = US listing, no suffix)
GOOGLE_TO_YAHOO = {
    "NASDAQ": "", "NYSE": "", "NYSEARCA": "", "NYSEAMERICAN": "", "BATS": "", "OTCMKTS": "", "OTC": "",
    "AMS": ".AS", "EPA": ".PA", "ETR": ".DE", "FRA": ".F", "BIT": ".MI", "BME": ".MC",
    "LON": ".L", "SWX": ".SW", "VTX": ".SW", "CPH": ".CO", "STO": ".ST", "HEL": ".HE",
    "OSL": ".OL", "EBR": ".BR", "ELI": ".LS", "VIE": ".VI", "WSE": ".WA", "ATH": ".AT",
    "TSE": ".TO", "CVE": ".V", "TYO": ".T", "HKG": ".HK", "SHA": ".SS", "SHE": ".SZ",
    "TPE": ".TW", "KRX": ".KS", "ASX": ".AX", "NSE": ".NS", "BOM": ".BO", "SGX": ".SI",
    "BVMF": ".SA", "JSE": ".JO", "TLV": ".TA", "IST": ".IS",
}


def to_yahoo(ticker: str | None) -> str | None:
    """'AMS:ASML' -> 'ASML.AS', 'NASDAQ:GOOGL' -> 'GOOGL', 'CPH:NOVO-B' -> 'NOVO-B.CO'.
    Plain tickers are returned unchanged (upper-cased)."""
    if not ticker:
        return None
    t = ticker.strip().upper().replace(" ", "")
    m = re.fullmatch(r"([A-Z]+):([A-Z0-9.\-]+)", t)
    if not m:
        return t or None
    exch, sym = m.groups()
    suffix = GOOGLE_TO_YAHOO.get(exch)
    if suffix is None:
        return sym
    if suffix == ".HK" and sym.isdigit():
        sym = sym.zfill(4)
    return sym + suffix
