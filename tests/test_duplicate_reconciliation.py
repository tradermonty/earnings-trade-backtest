"""Phase 5 parity test: _submit_with_reconciliation strict-fill + polling + partial-fill.

Asserts:
- Immediate ``filled`` → success.
- ``duplicate`` + prior order ``filled`` → reconciled success.
- ``duplicate`` + prior order ``accepted`` → ``duplicate_unfilled``.
- Polling loop catches a late fill within MAX_POLL_TRIES.
- Polling exhaustion → ``pending_unfilled`` for reconcile_pending_orders.
- ``partially_filled`` with ``filled_qty > 0`` cancels remainder, records partial.
- ``rejected`` / ``cancelled`` mid-poll → ``rejected`` outcome.
- Submit exception → ``submit_error``.
- ``cancel_order`` failure during partial doesn't downgrade the partial fill.
"""

import os
import sys
import time
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.paper_auto_entry import _submit_with_reconciliation


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Patch time.sleep to a no-op so polling tests run instantly."""
    monkeypatch.setattr(time, 'sleep', lambda *a, **kw: None)


class TestImmediateFill:
    def test_filled_returns_filled_full(self):
        mgr = MagicMock()
        mgr.submit_market_order.return_value = {
            'status': 'filled', 'filled_avg_price': 100.0, 'filled_qty': 50,
        }
        _, shares, outcome, reason = _submit_with_reconciliation(
            mgr, 'AAPL', 50, 'buy', 'cid', reference_price=100.0,
        )
        assert outcome == 'filled_full'
        assert shares == 50
        assert reason is None


class TestDuplicateReconciliation:
    def test_duplicate_then_prior_filled_is_success(self):
        mgr = MagicMock()
        mgr.submit_market_order.return_value = {'status': 'duplicate'}
        mgr.get_order_by_client_id.return_value = {
            'status': 'filled', 'filled_avg_price': 99.5, 'filled_qty': 50,
        }
        result, shares, outcome, reason = _submit_with_reconciliation(
            mgr, 'AAPL', 50, 'buy', 'cid', reference_price=100.0,
        )
        assert outcome == 'filled_full'
        assert result['filled_avg_price'] == 99.5
        assert reason is None

    def test_duplicate_then_prior_unfilled_is_duplicate_unfilled(self):
        mgr = MagicMock()
        mgr.submit_market_order.return_value = {'status': 'duplicate'}
        mgr.get_order_by_client_id.return_value = {'status': 'accepted'}
        _, _, outcome, reason = _submit_with_reconciliation(
            mgr, 'AAPL', 50, 'buy', 'cid', reference_price=100.0,
        )
        assert outcome == 'duplicate_unfilled'
        assert reason == 'duplicate_unfilled'


class TestPollingLoop:
    def test_late_fill_within_polling_window(self):
        mgr = MagicMock()
        mgr.submit_market_order.return_value = {'status': 'accepted'}
        # First poll returns accepted; second returns filled
        mgr.get_order_by_client_id.side_effect = [
            {'status': 'accepted'},
            {'status': 'filled', 'filled_avg_price': 100.5, 'filled_qty': 50},
        ]
        _, shares, outcome, reason = _submit_with_reconciliation(
            mgr, 'AAPL', 50, 'buy', 'cid', reference_price=100.0,
        )
        assert outcome == 'filled_full'
        assert shares == 50

    def test_polling_exhaustion_returns_pending_unfilled(self):
        mgr = MagicMock()
        mgr.submit_market_order.return_value = {'status': 'accepted'}
        mgr.get_order_by_client_id.return_value = {'status': 'accepted'}
        _, shares, outcome, reason = _submit_with_reconciliation(
            mgr, 'AAPL', 50, 'buy', 'cid', reference_price=100.0,
        )
        assert outcome == 'pending_unfilled'
        assert reason == 'not_filled'
        assert shares == 0


class TestPartialFill:
    def test_partial_fill_cancels_remainder_and_records_filled_qty(self):
        mgr = MagicMock()
        mgr.submit_market_order.return_value = {'status': 'accepted'}
        mgr.get_order_by_client_id.side_effect = [
            {
                'status': 'partially_filled', 'filled_qty': 30,
                'filled_avg_price': 99.5, 'id': 'order123',
            }
        ]
        result, shares, outcome, reason = _submit_with_reconciliation(
            mgr, 'AAPL', 50, 'buy', 'cid', reference_price=100.0,
        )
        assert outcome == 'filled_partial'
        assert shares == 30
        mgr.cancel_order.assert_called_once_with('order123')
        assert reason is None

    def test_cancel_order_failure_does_not_downgrade_partial(self):
        """Per parity_notes §3 / cancel-order spec: warn and proceed."""
        mgr = MagicMock()
        mgr.submit_market_order.return_value = {'status': 'accepted'}
        mgr.get_order_by_client_id.side_effect = [
            {
                'status': 'partially_filled', 'filled_qty': 25,
                'filled_avg_price': 99.0, 'id': 'order_x',
            }
        ]
        mgr.cancel_order.side_effect = RuntimeError('alpaca cancel rejected')
        _, shares, outcome, reason = _submit_with_reconciliation(
            mgr, 'AAPL', 50, 'buy', 'cid', reference_price=100.0,
        )
        # Filled portion preserved, even though cancel failed
        assert outcome == 'filled_partial'
        assert shares == 25


class TestTerminalRejection:
    def test_rejected_status_in_polling_returns_rejected_outcome(self):
        mgr = MagicMock()
        mgr.submit_market_order.return_value = {'status': 'accepted'}
        mgr.get_order_by_client_id.side_effect = [
            {'status': 'rejected', 'id': 'oid'}
        ]
        _, shares, outcome, reason = _submit_with_reconciliation(
            mgr, 'AAPL', 50, 'buy', 'cid', reference_price=100.0,
        )
        assert outcome == 'rejected'
        assert shares == 0
        assert reason == 'rejected'

    def test_cancelled_status_in_polling_returns_rejected_outcome(self):
        mgr = MagicMock()
        mgr.submit_market_order.return_value = {'status': 'accepted'}
        mgr.get_order_by_client_id.side_effect = [
            {'status': 'cancelled', 'id': 'oid'}
        ]
        _, _, outcome, reason = _submit_with_reconciliation(
            mgr, 'AAPL', 50, 'buy', 'cid', reference_price=100.0,
        )
        assert outcome == 'rejected'


class TestSubmitException:
    def test_submit_raises_returns_submit_error(self):
        mgr = MagicMock()
        mgr.submit_market_order.side_effect = RuntimeError('connection refused')
        result, shares, outcome, reason = _submit_with_reconciliation(
            mgr, 'AAPL', 50, 'buy', 'cid', reference_price=100.0,
        )
        assert outcome == 'submit_error'
        assert shares == 0
        assert 'connection refused' in reason
        assert 'error' in result
