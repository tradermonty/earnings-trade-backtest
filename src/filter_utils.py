"""Shared filtering utilities for backtest and live paper trading.

These helpers compute pre-earnings momentum and volume averages using
**only data strictly before the trade date**. They eliminate the look-ahead
bias that was present in the original `DataFilter` (which read trade_date
close/volume) and let the live screener share exactly the same logic.

Contract:
- All helpers accept either a DataFrame indexed by date (any datetime-like
  index) or a DataFrame with a 'date' column. Internal normalization handles
  both.
- ``None`` or empty input never raises; helpers return an empty DataFrame
  (`get_prior_bars`) or ``None`` (computational helpers). Callers map ``None``
  to a "skip" decision in the existing data-filter pipeline.
- Window distance for `compute_pre_earnings_change` is preserved at 19
  trading positions (`iloc[-1]` vs `iloc[-20]`) to match the original
  backtest behavior; the only change vs. the original is that the slice
  excludes ``trade_date`` itself (the look-ahead fix).
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


def normalize_to_date_index(stock_data: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Return a copy with a sorted DatetimeIndex.

    - ``None`` or empty input → empty DataFrame.
    - DataFrame with a ``date`` column → ``date`` parsed and set as index.
    - DataFrame already indexed by datetime/date → returned sorted.
    - Any other input → empty DataFrame (defensive; never raises).
    """
    if stock_data is None:
        return pd.DataFrame()
    if not isinstance(stock_data, pd.DataFrame) or stock_data.empty:
        return pd.DataFrame()

    df = stock_data.copy()
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
    elif 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date')
    elif not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except (TypeError, ValueError):
            return pd.DataFrame()
    return df.sort_index()


def get_prior_bars(stock_data: Optional[pd.DataFrame], trade_date: str) -> pd.DataFrame:
    """Return rows strictly before ``trade_date``.

    Empty DataFrame on None/empty input or when ``trade_date`` is unparseable.
    """
    df = normalize_to_date_index(stock_data)
    if df.empty:
        return df
    try:
        cutoff = pd.to_datetime(trade_date)
    except (TypeError, ValueError):
        return pd.DataFrame()
    return df.loc[df.index < cutoff]


def compute_pre_earnings_change(stock_data: Optional[pd.DataFrame],
                                trade_date: str) -> Optional[float]:
    """20-trading-day price change ending at the previous trading day.

    Distance preserved at 19 positions (``iloc[-1]`` vs ``iloc[-20]``) to
    match the original backtest behavior. Returns ``None`` when fewer than
    20 prior bars exist (insufficient history).
    """
    prior = get_prior_bars(stock_data, trade_date)
    if len(prior) < 20:
        return None
    close_col = _resolve_column(prior, 'Close', 'close')
    if close_col is None:
        return None
    current_close = float(prior.iloc[-1][close_col])
    price_20d_ago = float(prior.iloc[-20][close_col])
    if price_20d_ago == 0:
        return None
    return ((current_close - price_20d_ago) / price_20d_ago) * 100.0


def compute_avg_volume_20d(stock_data: Optional[pd.DataFrame],
                           trade_date: str) -> Optional[float]:
    """Mean of the last 20 Volume values strictly before ``trade_date``.

    Returns ``None`` when fewer than 20 prior bars exist.
    """
    prior = get_prior_bars(stock_data, trade_date)
    if len(prior) < 20:
        return None
    vol_col = _resolve_column(prior, 'Volume', 'volume')
    if vol_col is None:
        return None
    return float(prior[vol_col].tail(20).mean())


def _resolve_column(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    """Return the first matching column name, or ``None`` if no candidate exists."""
    for c in candidates:
        if c in df.columns:
            return c
    return None
