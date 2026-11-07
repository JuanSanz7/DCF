"""Loading template tabs from Google Sheets (public link) or an Excel workbook.

Google Sheets: the workbook is exported as .xlsx, which keeps typed numbers
(no locale guessing) and the cell notes (where researched ranges live). If that
export is refused, the tab is read as CSV of displayed values and the parser
detects the decimal separator from the tab itself.
"""
from __future__ import annotations

import io
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

import openpyxl

from .template import ImportResult, read_grid

_UA = "dcfmc/2.0 (+https://github.com/JuanSanz7/DCF)"
_CACHE: dict[str, tuple[float, bytes]] = {}
_TTL = 300


class SheetError(RuntimeError):
    pass


def extract_sheet_id(url_or_id: str) -> str:
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", url_or_id or "")
    sid = m.group(1) if m else (url_or_id or "").strip()
    if not re.fullmatch(r"[a-zA-Z0-9_-]{20,}", sid):
        raise SheetError("That doesn't look like a Google Sheets link or spreadsheet ID.")
    return sid


def extract_gid(url: str) -> str | None:
    m = re.search(r"[?&#]gid=(\d+)", url or "")
    return m.group(1) if m else None


def _get(url: str, timeout: float = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise SheetError("Google refused access. Share the spreadsheet as 'Anyone with the link: Viewer', "
                             "or upload the .xlsx instead.") from e
        if e.code == 404:
            raise SheetError("Spreadsheet not found (404). Check the link.") from e
        raise SheetError(f"Google Sheets returned HTTP {e.code}.") from e
    except urllib.error.URLError as e:
        raise SheetError(f"Could not reach Google Sheets ({e.reason}).") from e
    head = data[:400].lower()
    if b"<html" in head or b"<!doctype html" in head:
        raise SheetError("Google returned a sign-in page instead of data. Share the spreadsheet as "
                         "'Anyone with the link: Viewer', or upload the .xlsx instead.")
    return data


def fetch_workbook_bytes(sheet_id: str) -> bytes:
    now = time.time()
    hit = _CACHE.get(sheet_id)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    data = _get(f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx", timeout=60)
    _CACHE[sheet_id] = (now, data)
    return data


@dataclass
class Workbook:
    wb: openpyxl.Workbook

    @classmethod
    def from_bytes(cls, data: bytes) -> "Workbook":
        try:
            return cls(openpyxl.load_workbook(io.BytesIO(data), data_only=True))
        except Exception as e:  # noqa: BLE001
            raise SheetError(f"Could not open the workbook ({e}).") from e

    def tabs(self) -> list[str]:
        return list(self.wb.sheetnames)

    def read_tab(self, tab: str, source: str, max_rows: int = 400, max_cols: int = 8) -> ImportResult:
        if tab not in self.wb.sheetnames:
            match = [n for n in self.wb.sheetnames if n.strip().lower() == tab.strip().lower()]
            if not match:
                raise SheetError(f"Tab '{tab}' not found. Available: {', '.join(self.wb.sheetnames)}")
            tab = match[0]
        ws = self.wb[tab]
        rows, notes = [], {}
        for r_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=min(ws.max_row, max_rows),
                                                 max_col=max_cols)):
            rows.append([c.value for c in row])
            for c_idx, c in enumerate(row):
                if c.comment is not None and c.comment.text:
                    notes[(r_idx, c_idx)] = c.comment.text
        res = read_grid(rows, notes, source=f"{source}:{tab}")
        return res


def _csv_tab(sid: str, gid: str | None, tab: str | None) -> ImportResult:
    import csv
    if gid:
        q = f"export?format=csv&gid={gid}"
    else:
        q = "gviz/tq?tqx=out:csv&sheet=" + urllib.parse.quote(tab or "")
    text = _get(f"https://docs.google.com/spreadsheets/d/{sid}/{q}").decode("utf-8", "replace")
    rows = list(csv.reader(io.StringIO(text)))
    res = read_grid(rows, None, source=f"sheet-csv:{tab or 'gid=' + str(gid)}")
    res.msg("info", "Read the displayed values (CSV). Cell notes, and the ranges written in them, "
                    "are only available when a tab name is chosen.")
    return res


def load_google_tab(url: str, tab: str | None, with_notes: bool = False) -> tuple[ImportResult, list[str]]:
    """Reads one company tab. Fast path (default): only that tab, as CSV of displayed values
    (~1 s). With notes: the whole workbook is exported as .xlsx to also read the cell notes
    (slow for large workbooks)."""
    sid = extract_sheet_id(url)
    gid = extract_gid(url)
    if not tab:
        if not gid:
            raise SheetError("Type the name of the company's tab (or paste a link that ends in #gid=...).")
        return _csv_tab(sid, gid, None), []
    if not with_notes:
        try:
            res = _csv_tab(sid, None, tab)
        except SheetError:
            raise
        if len(res.fields) < 5:
            raise SheetError(f"Tab '{tab}' not found, or it isn't built from the valuation template. "
                             "Check the spelling (it must match the tab name exactly).")
        res.messages = [m for m in res.messages if "Cell notes" not in m["message"]]
        tk = res.fields.get("ticker")
        if tk and isinstance(tk.value, str):
            t = tk.value.split(":")[-1].strip().upper()
            if t and t not in tab.upper() and tab.upper() not in t:
                res.msg("warning", f"The tab's ticker is '{tk.value}', not '{tab}'. Google returns the first tab "
                                   "when a name doesn't exist: check the tab name.")
        return res, []
    try:
        wb = Workbook.from_bytes(fetch_workbook_bytes(sid))
        return wb.read_tab(tab, "sheet"), wb.tabs()
    except SheetError as first:
        try:
            return _csv_tab(sid, None, tab), []
        except SheetError:
            raise first


def list_google_tabs(url: str) -> list[str]:
    return Workbook.from_bytes(fetch_workbook_bytes(extract_sheet_id(url))).tabs()
