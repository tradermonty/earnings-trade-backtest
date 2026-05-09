"""Phase 5 parity test: DryRunAccount adapter contract.

Asserts:
- Portfolio value derives from state + today's pre-open price (no Alpaca call).
- ``submit_market_order`` returns Alpaca-compatible shape with
  ``filled_avg_price=reference_price`` and is **read-only on state**.
- ``get_order_by_client_id`` always returns None (no underlying broker).
- ``cancel_order`` is a no-op.
- Idempotency: place → re-read state → re-derived ``get_positions`` reflects
  the placed entry, blocking double-buy on subsequent runs.
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import DEFAULTS
from src.paper_state import DryRunAccount, get_state_paths


class FakeFetcher:
    """Minimal DataFetcher stand-in: maps symbol → fixed pre-open price."""

    def __init__(self, prices):
        self.prices = prices

    def get_preopen_price(self, symbol, today_str):
        return self.prices.get(symbol)


@pytest.fixture
def tmp_state():
    with tempfile.TemporaryDirectory() as tmp:
        paths = get_state_paths(tmp)
        with open(paths.trades, 'w') as f:
            json.dump([], f)
        with open(paths.pending_entries, 'w') as f:
            json.dump([], f)
        with open(paths.pending_exits, 'w') as f:
            json.dump([], f)
        yield paths


class TestEmptyState:
    def test_initial_capital(self, tmp_state):
        acc = DryRunAccount(tmp_state, data_fetcher=FakeFetcher({}), today_str='2025-06-15')
        s = acc.get_account_summary()
        assert s['portfolio_value'] == DEFAULTS.initial_capital
        assert s['cash'] == DEFAULTS.initial_capital
        assert s['long_market_value'] == 0.0

    def test_no_positions(self, tmp_state):
        acc = DryRunAccount(tmp_state, data_fetcher=FakeFetcher({}), today_str='2025-06-15')
        assert acc.get_positions() == []


class TestSubmitOrderShape:
    def test_returns_filled_with_reference_price(self, tmp_state):
        acc = DryRunAccount(tmp_state, data_fetcher=FakeFetcher({}), today_str='2025-06-15')
        result = acc.submit_market_order(
            'AAPL', 50, 'buy', 'cid_test', reference_price=150.0,
        )
        assert result['status'] == 'filled'
        assert result['filled_avg_price'] == 150.0
        assert result['filled_qty'] == 50
        assert result['client_order_id'] == 'cid_test'

    def test_does_not_mutate_state(self, tmp_state):
        acc = DryRunAccount(tmp_state, data_fetcher=FakeFetcher({}), today_str='2025-06-15')
        acc.submit_market_order('AAPL', 50, 'buy', 'cid', reference_price=150.0)
        with open(tmp_state.trades) as f:
            assert json.load(f) == []

    def test_missing_reference_price_raises(self, tmp_state):
        acc = DryRunAccount(tmp_state, data_fetcher=FakeFetcher({}), today_str='2025-06-15')
        with pytest.raises(ValueError, match='reference_price'):
            acc.submit_market_order('AAPL', 50, 'buy', 'cid')

    def test_zero_qty_raises(self, tmp_state):
        acc = DryRunAccount(tmp_state, data_fetcher=FakeFetcher({}), today_str='2025-06-15')
        with pytest.raises(ValueError):
            acc.submit_market_order('AAPL', 0, 'buy', 'cid', reference_price=150.0)


class TestNoBrokerSurface:
    def test_get_order_by_client_id_always_none(self, tmp_state):
        acc = DryRunAccount(tmp_state, data_fetcher=FakeFetcher({}), today_str='2025-06-15')
        assert acc.get_order_by_client_id('any-cid') is None

    def test_cancel_order_no_op_returns_true(self, tmp_state):
        acc = DryRunAccount(tmp_state, data_fetcher=FakeFetcher({}), today_str='2025-06-15')
        assert acc.cancel_order('any-id') is True


class TestPortfolioMath:
    def test_open_position_priced_at_today_pre_open(self, tmp_state):
        with open(tmp_state.trades, 'w') as f:
            json.dump([{
                'symbol': 'AAPL',
                'entry_price': 100.0,
                'remaining_shares': 100,
                'status': 'open',
                'legs': [{'action': 'entry', 'shares': 100, 'price': 100.0}],
            }], f)
        # Today's pre-open is 110 → unrealized = (110 - 100) * 100 = 1000
        acc = DryRunAccount(
            tmp_state, data_fetcher=FakeFetcher({'AAPL': 110.0}),
            today_str='2025-06-15',
        )
        s = acc.get_account_summary()
        assert s['portfolio_value'] == DEFAULTS.initial_capital + 1000.0
        assert s['long_market_value'] == 110.0 * 100  # current_price * shares
        positions = acc.get_positions()
        assert len(positions) == 1
        assert positions[0]['symbol'] == 'AAPL'
        assert positions[0]['qty'] == 100
        assert positions[0]['unrealized_pl'] == pytest.approx(1000.0)

    def test_realized_pnl_from_closed_legs(self, tmp_state):
        with open(tmp_state.trades, 'w') as f:
            json.dump([{
                'symbol': 'MSFT',
                'entry_price': 200.0,
                'remaining_shares': 0,
                'status': 'closed',
                'legs': [
                    {'action': 'entry', 'shares': 50, 'price': 200.0},
                    {'action': 'exit_stop', 'shares': 50, 'price': 220.0, 'pnl': 1000.0},
                ],
            }], f)
        acc = DryRunAccount(
            tmp_state, data_fetcher=FakeFetcher({}), today_str='2025-06-15',
        )
        s = acc.get_account_summary()
        assert s['portfolio_value'] == DEFAULTS.initial_capital + 1000.0
        # No open positions
        assert s['long_market_value'] == 0.0
        assert acc.get_positions() == []

    def test_unpriced_position_falls_back_to_entry_price(self, tmp_state):
        """If pre-open is None, valuation falls back to entry_price."""
        with open(tmp_state.trades, 'w') as f:
            json.dump([{
                'symbol': 'NVDA',
                'entry_price': 800.0,
                'remaining_shares': 10,
                'status': 'open',
                'legs': [{'action': 'entry', 'shares': 10, 'price': 800.0}],
            }], f)
        acc = DryRunAccount(
            tmp_state, data_fetcher=FakeFetcher({}),  # no NVDA price → None
            today_str='2025-06-15',
        )
        positions = acc.get_positions()
        assert positions[0]['current_price'] == 800.0
        assert positions[0]['unrealized_pl'] == 0.0


class TestIdempotencyContract:
    """A re-run that re-derives positions from state must reflect prior placements."""

    def test_position_appears_after_state_write(self, tmp_state):
        # Initially empty
        acc = DryRunAccount(
            tmp_state, data_fetcher=FakeFetcher({'AAPL': 150.0}),
            today_str='2025-06-15',
        )
        assert acc.get_positions() == []

        # Simulate execute_pending Phase-6 state write (DryRunAccount itself
        # does NOT write state — that's the contract)
        with open(tmp_state.trades, 'w') as f:
            json.dump([{
                'symbol': 'AAPL',
                'entry_price': 149.5,
                'remaining_shares': 100,
                'status': 'open',
                'legs': [{'action': 'entry', 'shares': 100, 'price': 149.5}],
            }], f)

        # Re-derive — must now see the position
        positions = acc.get_positions()
        assert len(positions) == 1
        assert positions[0]['symbol'] == 'AAPL'
