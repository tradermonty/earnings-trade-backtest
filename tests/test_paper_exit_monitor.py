"""Tests for scripts/paper_exit_monitor.py"""

import pytest
import math
import os
import sys
from unittest.mock import Mock, patch
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.paper_exit_monitor import check_exit_conditions


def _make_trade(symbol='TEST', entry_date='2026-03-03', entry_price=100.0,
                remaining_shares=45, stop_loss_price=None):
    if stop_loss_price is None:
        stop_loss_price = entry_price * 0.9  # -10%
    return {
        'symbol': symbol,
        'entry_date': entry_date,
        'entry_price': entry_price,
        'remaining_shares': remaining_shares,
        'stop_loss_price': stop_loss_price,
        'status': 'open',
        'legs': [],
    }


def _make_stock_data(dates, closes, lows=None, highs=None):
    """Create a mock DataFrame with OHLCV data."""
    n = len(dates)
    if lows is None:
        lows = [c * 0.98 for c in closes]
    if highs is None:
        highs = [c * 1.02 for c in closes]
    df = pd.DataFrame({
        'date': dates,
        'Open': closes,
        'High': highs,
        'Low': lows,
        'Close': closes,
        'Volume': [1000000] * n,
    })
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date')
    return df


def _mock_fetcher_with_data(stock_data_raw):
    fetcher = Mock()
    df = stock_data_raw.reset_index()
    df = df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low',
                            'Close': 'close', 'Volume': 'volume'})
    df['date'] = df['date'].dt.strftime('%Y-%m-%d')
    fetcher.get_historical_data.return_value = df
    return fetcher


class TestExitPriority:
    """Exit conditions are checked in priority order: max_holding > stop_loss > trailing > partial"""

    def test_stop_loss_triggered(self):
        """Low <= stop_loss_price → exit with stop_loss reason"""
        trade = _make_trade(entry_price=100.0)  # stop at 90
        dates = pd.date_range('2026-03-01', '2026-03-10')
        closes = [100] * 10
        lows = [100] * 9 + [89]  # day 10: low hits stop
        data = _make_stock_data(dates, closes, lows=lows)
        fetcher = _mock_fetcher_with_data(data)

        result = check_exit_conditions(trade, fetcher, '2026-03-10')
        assert result is not None
        assert result['reason'] == 'stop_loss'
        assert result['shares'] == 45

    def test_trailing_stop_triggered(self):
        """Close < MA21 → trailing_stop"""
        trade = _make_trade(entry_date='2026-01-01', entry_price=100.0)
        dates = pd.date_range('2025-12-01', '2026-03-10')
        # 100 days of data, close drops below MA21 on the last day
        closes = [110] * 99 + [95]
        data = _make_stock_data(dates, closes)
        fetcher = _mock_fetcher_with_data(data)

        result = check_exit_conditions(trade, fetcher, '2026-03-10')
        assert result is not None
        assert result['reason'] == 'trailing_stop'

    def test_max_holding_days_triggered(self):
        """Holding > 90 days → max_holding_days (highest priority)"""
        trade = _make_trade(entry_date='2025-12-01', entry_price=100.0)
        dates = pd.date_range('2025-11-01', '2026-03-10')
        closes = [110] * len(dates)  # price is fine, but time exceeded
        data = _make_stock_data(dates, closes)
        fetcher = _mock_fetcher_with_data(data)

        # 2025-12-01 to 2026-03-10 = 99 days > 90
        result = check_exit_conditions(trade, fetcher, '2026-03-10')
        assert result is not None
        assert result['reason'] == 'max_holding_days'

    def test_stop_loss_takes_priority_over_trailing(self):
        """When both stop_loss and trailing_stop trigger, stop_loss wins"""
        trade = _make_trade(entry_date='2026-01-01', entry_price=100.0)
        dates = pd.date_range('2025-12-01', '2026-03-10')
        # Close drops below MA21 AND low hits stop on same day
        closes = [110] * 99 + [85]
        lows = [110] * 99 + [85]  # low hits stop at 90
        data = _make_stock_data(dates, closes, lows=lows)
        fetcher = _mock_fetcher_with_data(data)

        result = check_exit_conditions(trade, fetcher, '2026-03-10')
        assert result is not None
        assert result['reason'] == 'stop_loss'  # not trailing_stop

    def test_no_exit_when_all_conditions_pass(self):
        """No exit when price is above stop and MA21"""
        trade = _make_trade(entry_date='2026-03-03', entry_price=100.0)
        dates = pd.date_range('2026-02-01', '2026-03-10')
        closes = [105] * len(dates)  # healthy, above entry
        data = _make_stock_data(dates, closes)
        fetcher = _mock_fetcher_with_data(data)

        result = check_exit_conditions(trade, fetcher, '2026-03-10')
        assert result is None


class TestPartialProfit:
    """Partial profit only fires on day 1 with +6% close"""

    def test_partial_profit_on_day_1(self):
        """Close >= +6% on entry day → sell floor(shares/2)"""
        trade = _make_trade(entry_date='2026-03-03', entry_price=100.0,
                            remaining_shares=45)
        dates = pd.date_range('2026-02-01', '2026-03-03')
        closes = [100] * len(dates)
        closes[-1] = 107  # +7% on entry day
        data = _make_stock_data(dates, closes)
        fetcher = _mock_fetcher_with_data(data)

        result = check_exit_conditions(trade, fetcher, '2026-03-03')
        assert result is not None
        assert result['reason'] == 'partial_profit'
        assert result['shares'] == 22  # floor(45/2)

    def test_no_partial_on_day_2(self):
        """Day 2 with +6% → no partial profit (day 1 only)"""
        trade = _make_trade(entry_date='2026-03-03', entry_price=100.0)
        dates = pd.date_range('2026-02-01', '2026-03-04')
        closes = [100] * len(dates)
        closes[-1] = 107  # +7% but on day 2
        data = _make_stock_data(dates, closes)
        fetcher = _mock_fetcher_with_data(data)

        result = check_exit_conditions(trade, fetcher, '2026-03-04')
        # Should not trigger partial (days_held=1, not 0)
        assert result is None or result['reason'] != 'partial_profit'

    def test_no_partial_when_only_5_percent(self):
        """+5% on day 1 → below threshold, no partial"""
        trade = _make_trade(entry_date='2026-03-03', entry_price=100.0)
        dates = pd.date_range('2026-02-01', '2026-03-03')
        closes = [100] * len(dates)
        closes[-1] = 105  # +5%, below 6% threshold
        data = _make_stock_data(dates, closes)
        fetcher = _mock_fetcher_with_data(data)

        result = check_exit_conditions(trade, fetcher, '2026-03-03')
        assert result is None

    def test_no_partial_when_1_share(self):
        """1 share → floor(1/2) = 0 → skip partial"""
        trade = _make_trade(entry_date='2026-03-03', entry_price=100.0,
                            remaining_shares=1)
        dates = pd.date_range('2026-02-01', '2026-03-03')
        closes = [100] * len(dates)
        closes[-1] = 107  # +7%
        data = _make_stock_data(dates, closes)
        fetcher = _mock_fetcher_with_data(data)

        result = check_exit_conditions(trade, fetcher, '2026-03-03')
        assert result is None  # 0 shares to sell → no action
