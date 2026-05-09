"""Phase 5 parity test: check_risk_gate honors today_str (replay-deterministic)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.paper_auto_entry import check_risk_gate


def _trade_with_exit(date, pnl):
    return {'legs': [{'action': 'exit_stop', 'date': date, 'pnl': pnl}]}


class TestRiskGateRecentLossesBlock:
    def test_recent_loss_above_limit_blocks(self):
        # 10% loss in last 30 days at portfolio 100k → blocks (limit -6%)
        trades = [_trade_with_exit('2025-01-10', -10000.0)]
        assert check_risk_gate(trades, 100_000.0, today_str='2025-01-15') is False

    def test_recent_loss_below_limit_allows(self):
        trades = [_trade_with_exit('2025-01-10', -1000.0)]  # 1% only
        assert check_risk_gate(trades, 100_000.0, today_str='2025-01-15') is True

    def test_old_loss_outside_window_does_not_block(self):
        trades = [_trade_with_exit('2025-01-10', -10000.0)]
        # 60 days later — outside 30-day window
        assert check_risk_gate(trades, 100_000.0, today_str='2025-03-15') is True


class TestRiskGateBoundaryConditions:
    def test_zero_portfolio_value_returns_true(self):
        trades = [_trade_with_exit('2025-01-10', -10000.0)]
        assert check_risk_gate(trades, 0.0, today_str='2025-01-15') is True

    def test_no_trades_returns_true(self):
        assert check_risk_gate([], 100_000.0, today_str='2025-01-15') is True

    def test_only_entry_legs_returns_true(self):
        trades = [{'legs': [{'action': 'entry', 'date': '2025-01-10'}]}]
        assert check_risk_gate(trades, 100_000.0, today_str='2025-01-15') is True


class TestRiskGateReplayDeterminism:
    """Same inputs (trades, portfolio, today_str) must produce same result.

    Without ``today_str`` injection, the gate would depend on wall clock
    and parity tests couldn't reproduce historical decisions.
    """

    def test_same_today_str_same_result(self):
        trades = [_trade_with_exit('2025-06-01', -7000.0)]
        r1 = check_risk_gate(trades, 100_000.0, today_str='2025-06-15')
        r2 = check_risk_gate(trades, 100_000.0, today_str='2025-06-15')
        assert r1 == r2 is False

    def test_different_today_str_different_result(self):
        trades = [_trade_with_exit('2025-06-01', -7000.0)]
        # 2025-06-15: within 30 days → blocks
        # 2025-08-01: 61 days later → allows
        r_blocks = check_risk_gate(trades, 100_000.0, today_str='2025-06-15')
        r_allows = check_risk_gate(trades, 100_000.0, today_str='2025-08-01')
        assert r_blocks is False
        assert r_allows is True


class TestRiskGateDefaultToday:
    """When today_str is omitted, defaults to NY-tz today (live behavior preserved)."""

    def test_default_today_str_is_used_when_omitted(self):
        # Just verify it doesn't raise when omitted; behavior matches NY today.
        result = check_risk_gate([], 100_000.0)
        assert result is True
