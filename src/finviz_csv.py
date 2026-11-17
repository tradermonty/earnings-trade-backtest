"""Parsing and validation helpers for saved Finviz CSV exports.

The column / unit contract is documented in ``docs/finviz_csv_contract.md``.
Keep the two in sync.

Unit rules (per cell, no magnitude guessing):

* Percent columns
    - ``"12.89%"``  -> explicit suffix, already in percentage points -> 12.89
    - ``0.1289``    -> bare number, a numeric *fraction* (historical Finviz
                       numeric export)                                  -> 12.89
    - ``""``/``"-"``/NaN -> missing observation (NaN), never 0
* Market Cap
    - bare number   -> millions of USD (historical Finviz export)
    - ``K``/``M``/``B``/``T`` suffix -> explicit multiplier
* Average Volume
    - bare number   -> thousands of shares (historical Finviz export)
    - ``K``/``M``/``B`` suffix -> explicit multiplier
* Price and plain ratios (P/S, P/E, P/B, RSI) -> taken as-is

Any non-empty value that cannot be parsed raises :class:`FinvizCsvError`
instead of silently becoming 0 or NaN.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import pandas as pd


class FinvizCsvError(ValueError):
    """Raised when a Finviz CSV does not satisfy the documented contract."""


# Tokens Finviz (or a spreadsheet round-trip) uses for "no observation".
_MISSING_TOKENS = {"", "-", "nan", "none", "n/a", "na"}

_NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")

_SUFFIX_MULTIPLIERS = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def _is_missing(val: Any) -> bool:
    if isinstance(val, str):
        return val.strip().lower() in _MISSING_TOKENS
    try:
        return bool(pd.isna(val))  # None, NaN, pd.NA, NaT, numpy NaN of any width
    except (TypeError, ValueError):
        return False


def _clean(val: Any) -> str:
    return str(val).strip().replace(",", "").replace("$", "")


def _parse_number(s: str, what: str) -> float:
    if not _NUMBER_RE.match(s):
        raise FinvizCsvError(f"cannot parse {what} value {s!r}")
    return float(s)


def parse_percent(val: Any) -> float:
    """Return a percent-type cell in percentage points, NaN when missing."""
    if _is_missing(val):
        return math.nan
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val) * 100.0
    s = _clean(val)
    if s.endswith("%"):
        return _parse_number(s[:-1].strip(), "percent")
    return _parse_number(s, "percent") * 100.0


def _parse_with_suffix(val: Any, bare_multiplier: float, what: str) -> float:
    if _is_missing(val):
        return math.nan
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val) * bare_multiplier
    s = _clean(val)
    suffix = s[-1:].upper()
    if suffix in _SUFFIX_MULTIPLIERS:
        try:
            return _parse_number(s[:-1].strip(), what) * _SUFFIX_MULTIPLIERS[suffix]
        except FinvizCsvError:
            raise FinvizCsvError(f"cannot parse {what} value {s!r}") from None
    return _parse_number(s, what) * bare_multiplier


def parse_market_cap(val: Any) -> float:
    """Return market cap in USD. Bare numbers are millions of USD."""
    return _parse_with_suffix(val, 1e6, "market cap")


def parse_avg_volume(val: Any) -> float:
    """Return average volume in shares. Bare numbers are thousands of shares."""
    return _parse_with_suffix(val, 1e3, "average volume")


def parse_plain(val: Any) -> float:
    """Return a plain number (price, ratio, RSI), NaN when missing."""
    if _is_missing(val):
        return math.nan
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    return _parse_number(_clean(val), "numeric")


# -----------------------------------------------------------------------------
# Column contract for scripts/run_backtest_from_aggregated.py
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Field:
    key: str                      # internal column name, e.g. "_eps"
    aliases: Sequence[str]        # accepted header names, first match wins
    parser: Callable[[Any], float]


FIELDS: Dict[str, Field] = {f.key: f for f in [
    Field("_eps", ("EPS Surprise",), parse_percent),
    Field("_price", ("Price", "Open", "Close", "Entry Price", "Entry"), parse_plain),
    Field("_gap", ("Gap",), parse_percent),
    Field("_perf_m", ("Performance (Month)",), parse_percent),
    Field("_change", ("Change",), parse_percent),
    Field("_perf1h", ("Performance (1 Hour)",), parse_percent),
    Field("_mcap", ("Market Cap",), parse_market_cap),
    Field("_vol", ("Average Volume", "Avg Vol", "Avg Vol (3 month)"), parse_avg_volume),
    Field("_ps", ("P/S",), parse_plain),
    Field("_pe", ("P/E",), parse_plain),
    Field("_profit_margin", ("Profit Margin",), parse_percent),
    Field("_roa", ("Return on Assets",), parse_percent),
    Field("_vol_week", ("Volatility (Week)",), parse_percent),
    Field("_perf_week", ("Performance (Week)",), parse_percent),
    Field("_rsi14", ("Relative Strength Index (14)",), parse_plain),
    Field("_pb", ("P/B",), parse_plain),
]}

# Columns needed regardless of filter settings (identity + daily ranking).
ALWAYS_REQUIRED = ("Trade Date", "Ticker")
ALWAYS_REQUIRED_FIELDS = ("_eps",)


def resolve_column(columns: Iterable[str], field: Field) -> Optional[str]:
    cols = set(columns)
    for alias in field.aliases:
        if alias in cols:
            return alias
    return None


def validate_columns(df: pd.DataFrame, required: Dict[str, Sequence[str]]) -> Dict[str, str]:
    """Check that every enabled filter has its source column.

    ``required`` maps a human-readable filter label to the internal field keys it
    needs. Returns ``{field_key: source_column}`` for all resolved fields.
    Raises :class:`FinvizCsvError` listing every missing column at once.
    """
    problems: List[str] = []
    missing_base = [c for c in ALWAYS_REQUIRED if c not in df.columns]
    if missing_base:
        problems.append(f"identity: missing column(s) {missing_base}")

    resolved: Dict[str, str] = {}
    for label, keys in required.items():
        for key in keys:
            field = FIELDS[key]
            col = resolve_column(df.columns, field)
            if col is None:
                problems.append(
                    f"{label}: missing column, expected one of {list(field.aliases)}"
                )
            else:
                resolved[key] = col
    if problems:
        raise FinvizCsvError(
            "Finviz CSV does not satisfy the column contract "
            "(see docs/finviz_csv_contract.md):\n  - " + "\n  - ".join(problems)
        )
    return resolved


CSV_LINE_COL = "_csv_line"


def add_csv_line_numbers(df: pd.DataFrame) -> pd.DataFrame:
    """Record each row's 1-based CSV line (header = line 1) for error messages.

    Call right after ``pd.read_csv`` so the numbers survive later filtering.
    """
    df = df.copy()
    df[CSV_LINE_COL] = range(2, len(df) + 2)
    return df


def _row_label(df: pd.DataFrame, idx: Any) -> str:
    ticker = df.at[idx, "Ticker"] if "Ticker" in df.columns else "?"
    if CSV_LINE_COL in df.columns:
        return f"CSV line {df.at[idx, CSV_LINE_COL]} ({ticker})"
    return f"row index {idx} ({ticker})"


def parse_columns(df: pd.DataFrame, resolved: Dict[str, str]) -> pd.DataFrame:
    """Add parsed internal columns. Unparseable cells raise with row context."""
    df = df.copy()
    for key, col in resolved.items():
        parser = FIELDS[key].parser
        values = []
        for idx, raw in df[col].items():
            try:
                values.append(parser(raw))
            except FinvizCsvError as exc:
                raise FinvizCsvError(f"column {col!r}, {_row_label(df, idx)}: {exc}") from None
        df[key] = pd.Series(values, index=df.index, dtype="float64")
    return df


# -----------------------------------------------------------------------------
# Column contract for scripts/compare_fmp_finviz_accuracy.py
# -----------------------------------------------------------------------------

DATE_COMPARISON_REQUIRED = ("Ticker", "Earnings Date")


def parse_finviz_earnings_date(raw: Any) -> Optional[str]:
    """``"7/1/25 8:30"`` / ``"7/1/2025"`` / ``"2025-07-01"`` -> ``"2025-07-01"``.

    Returns None for a missing value and raises for an unparseable one.
    """
    if _is_missing(raw):
        return None
    date_part = str(raw).strip().split(" ")[0]
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return pd.to_datetime(date_part, format=fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise FinvizCsvError(f"cannot parse Earnings Date {raw!r}")


def load_finviz_earnings_dates(df: pd.DataFrame) -> List[Dict[str, str]]:
    """Validate headers and extract ``symbol/company/finviz_date`` records."""
    df = df.copy()
    df.columns = df.columns.str.strip()
    missing = [c for c in DATE_COMPARISON_REQUIRED if c not in df.columns]
    if missing:
        raise FinvizCsvError(
            f"date comparison needs column(s) {missing}; got {list(df.columns)} "
            "(see docs/finviz_csv_contract.md)"
        )
    records: List[Dict[str, str]] = []
    no_ticker = 0
    no_date: List[str] = []
    for idx, row in df.iterrows():
        symbol = "" if _is_missing(row["Ticker"]) else str(row["Ticker"]).strip()
        if not symbol:
            if not _is_missing(row["Earnings Date"]):
                no_ticker += 1
            continue
        try:
            date = parse_finviz_earnings_date(row["Earnings Date"])
        except FinvizCsvError as exc:
            raise FinvizCsvError(f"CSV line {idx + 2} ({symbol}): {exc}") from None
        if date is None:
            no_date.append(symbol)
            continue
        company_raw = row.get("Company")
        records.append({
            "symbol": symbol,
            "company": "" if _is_missing(company_raw) else str(company_raw).strip(),
            "finviz_date": date,
            "raw_date_str": str(row["Earnings Date"]).strip(),
        })
    if no_date:
        print(f"[WARN] Earnings Date missing, skipped {len(no_date)} row(s): "
              f"{', '.join(no_date[:10])}{' ...' if len(no_date) > 10 else ''}")
    if no_ticker:
        print(f"[WARN] Ticker missing, skipped {no_ticker} row(s) that had an Earnings Date")
    return records


def compare_earnings_dates(finviz_records: List[Dict[str, str]],
                           fmp_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Match each Finviz record to the nearest FMP date for the same symbol."""
    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for rec in fmp_records:
        by_symbol.setdefault(rec["symbol"], []).append(rec)

    results: List[Dict[str, Any]] = []
    for fv in finviz_records:
        result = {
            "symbol": fv["symbol"],
            "company": fv["company"],
            "finviz_date": fv["finviz_date"],
            "finviz_raw": fv["raw_date_str"],
            "fmp_date": None,
            "fmp_time": None,
            "date_match": False,
            "date_diff_days": None,
            "status": "NO_FMP_DATA",
        }
        fv_dt = pd.Timestamp(fv["finviz_date"])
        best, best_diff = None, None
        for rec in by_symbol.get(fv["symbol"], []):
            try:
                diff = abs((fv_dt - pd.Timestamp(rec["fmp_date"])).days)
            except (ValueError, TypeError):
                continue
            if best_diff is None or diff < best_diff:
                best, best_diff = rec, diff
        if best is not None:
            result.update(
                fmp_date=best["fmp_date"],
                fmp_time=best.get("time"),
                date_diff_days=best_diff,
                date_match=best_diff == 0,
                status=("EXACT_MATCH" if best_diff == 0 else
                        "CLOSE_MATCH" if best_diff <= 1 else
                        "MODERATE_DIFF" if best_diff <= 3 else "LARGE_DIFF"),
            )
        results.append(result)
    return results
