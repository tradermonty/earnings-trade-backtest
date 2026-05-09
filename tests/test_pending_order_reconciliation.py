"""Tests for scripts/reconcile_pending_orders.py.

The reconciliation job resolves orders that were submitted by
``execute_pending`` but did not reach a strict ``filled`` state inside the
short 09:30 polling window.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECONCILE_SCRIPT = os.path.join(PROJECT_ROOT, 'scripts', 'reconcile_pending_orders.py')
PYTHON = sys.executable


def _seed_state(state_dir, *, trades=None, entries=None, exits=None):
    os.makedirs(state_dir, exist_ok=True)
    Path(state_dir, 'paper_trades.json').write_text(json.dumps(trades or []))
    Path(state_dir, 'pending_entries.json').write_text(json.dumps(entries or []))
    Path(state_dir, 'pending_exits.json').write_text(json.dumps(exits or []))


def _read(path):
    with open(path) as f:
        return json.load(f)


class FakeOrderManager:
    def __init__(self, orders):
        self.orders = orders
        self.cancelled = []

    def get_order_by_client_id(self, client_order_id):
        return self.orders.get(client_order_id)

    def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        return True


class TestDryRunReconcile:
    def test_dry_run_reports_zero_unresolved_with_empty_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            _seed_state(tmp)
            result = subprocess.run(
                [PYTHON, RECONCILE_SCRIPT, '--dry-run', '--state-dir', tmp],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0, f'stderr={result.stderr}'
            assert '(dry-run) unresolved entries: 0' in result.stdout
            assert '(dry-run) unresolved exits:   0' in result.stdout

    def test_dry_run_warns_if_pending_status_records_exist(self):
        """DryRunAccount fills are immediate; pending status records indicate a bug."""
        with tempfile.TemporaryDirectory() as tmp:
            _seed_state(tmp, entries=[{
                'symbol': 'AAPL',
                'trade_date': '2025-06-15',
                'timing': 'amc',
                'submission_status': 'pending',
                'submitted_client_order_id': 'cid_x',
            }])
            result = subprocess.run(
                [PYTHON, RECONCILE_SCRIPT, '--dry-run', '--state-dir', tmp],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0
            assert 'unresolved entries: 1' in result.stdout
            assert 'investigation needed' in result.stdout

    def test_dry_run_does_not_require_alpaca_keys(self):
        """Dry-run path must never instantiate AlpacaOrderManager."""
        env = os.environ.copy()
        env.pop('ALPACA_API_KEY_PAPER', None)
        env.pop('ALPACA_SECRET_KEY_PAPER', None)
        with tempfile.TemporaryDirectory() as tmp:
            _seed_state(tmp)
            result = subprocess.run(
                [PYTHON, RECONCILE_SCRIPT, '--dry-run', '--state-dir', tmp],
                capture_output=True, text=True, timeout=30, env=env,
            )
            assert result.returncode == 0, (
                f'dry-run should not need Alpaca keys; stderr={result.stderr}'
            )


class TestLiveReconcile:
    def test_filled_entry_appends_open_trade_and_removes_pending(self):
        from scripts.reconcile_pending_orders import reconcile_pending_orders
        from src.paper_state import get_state_paths

        with tempfile.TemporaryDirectory() as tmp:
            paths = get_state_paths(tmp)
            _seed_state(tmp, entries=[{
                'symbol': 'AAPL',
                'trade_date': '2026-03-03',
                'timing': 'bmo',
                'eps_surprise_percent': 12.5,
                'submission_status': 'pending',
                'submitted_client_order_id': 'cid_entry',
                'submitted_shares': 50,
                'submitted_reference_price': 100.0,
            }])
            mgr = FakeOrderManager({
                'cid_entry': {
                    'id': 'order_entry',
                    'client_order_id': 'cid_entry',
                    'status': 'filled',
                    'filled_avg_price': 101.5,
                    'filled_qty': 50,
                }
            })

            result = reconcile_pending_orders(
                alpaca_manager=mgr,
                today_str='2026-03-03',
                state_dir=tmp,
            )

            assert len(result['entries_reconciled']) == 1
            assert _read(paths.pending_entries) == []
            trades = _read(paths.trades)
            assert len(trades) == 1
            assert trades[0]['symbol'] == 'AAPL'
            assert trades[0]['entry_price'] == 101.5
            assert trades[0]['remaining_shares'] == 50
            assert trades[0]['status'] == 'open'

    def test_filled_exit_updates_trade_and_removes_matching_pending_exit(self):
        from scripts.reconcile_pending_orders import reconcile_pending_orders
        from src.paper_state import get_state_paths

        trade = {
            'symbol': 'AAPL',
            'entry_date': '2026-03-01',
            'entry_price': 100.0,
            'initial_shares': 50,
            'remaining_shares': 50,
            'status': 'open',
            'legs': [{'action': 'entry', 'shares': 50, 'price': 100.0}],
        }
        exit_rec = {
            'symbol': 'AAPL',
            'reason': 'stop_loss',
            'shares': 50,
            'submission_status': 'pending',
            'submitted_client_order_id': 'cid_exit',
            'submitted_shares': 50,
            'submitted_reference_price': 95.0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            paths = get_state_paths(tmp)
            _seed_state(tmp, trades=[trade], exits=[exit_rec])
            mgr = FakeOrderManager({
                'cid_exit': {
                    'id': 'order_exit',
                    'client_order_id': 'cid_exit',
                    'status': 'filled',
                    'filled_avg_price': 95.0,
                    'filled_qty': 50,
                }
            })

            result = reconcile_pending_orders(
                alpaca_manager=mgr,
                today_str='2026-03-03',
                state_dir=tmp,
            )

            assert len(result['exits_reconciled']) == 1
            assert _read(paths.pending_exits) == []
            trades = _read(paths.trades)
            assert trades[0]['status'] == 'closed'
            assert trades[0]['remaining_shares'] == 0
            assert trades[0]['legs'][-1]['action'] == 'exit_stop_loss'
            assert trades[0]['legs'][-1]['pnl'] == -250.0

    def test_partial_exit_cancels_remainder_and_keeps_remaining_position(self):
        from scripts.reconcile_pending_orders import reconcile_pending_orders
        from src.paper_state import get_state_paths

        trade = {
            'symbol': 'MSFT',
            'entry_price': 100.0,
            'initial_shares': 50,
            'remaining_shares': 50,
            'status': 'open',
            'legs': [{'action': 'entry', 'shares': 50, 'price': 100.0}],
        }
        exit_rec = {
            'symbol': 'MSFT',
            'reason': 'partial_profit',
            'shares': 50,
            'submission_status': 'pending',
            'submitted_client_order_id': 'cid_partial',
            'submitted_shares': 50,
            'submitted_reference_price': 103.0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            paths = get_state_paths(tmp)
            _seed_state(tmp, trades=[trade], exits=[exit_rec])
            mgr = FakeOrderManager({
                'cid_partial': {
                    'id': 'order_partial',
                    'client_order_id': 'cid_partial',
                    'status': 'partially_filled',
                    'filled_avg_price': 103.0,
                    'filled_qty': 20,
                }
            })

            result = reconcile_pending_orders(
                alpaca_manager=mgr,
                today_str='2026-03-03',
                state_dir=tmp,
            )

            assert len(result['exits_reconciled']) == 1
            assert mgr.cancelled == ['order_partial']
            assert _read(paths.pending_exits) == []
            trades = _read(paths.trades)
            assert trades[0]['status'] == 'open'
            assert trades[0]['remaining_shares'] == 30
            assert trades[0]['legs'][-1]['shares'] == 20

    def test_rejected_entry_is_removed_without_trade(self):
        from scripts.reconcile_pending_orders import reconcile_pending_orders
        from src.paper_state import get_state_paths

        entry_rec = {
            'symbol': 'REJ',
            'trade_date': '2026-03-03',
            'timing': 'bmo',
            'submission_status': 'pending',
            'submitted_client_order_id': 'cid_rejected',
            'submitted_shares': 10,
        }
        with tempfile.TemporaryDirectory() as tmp:
            paths = get_state_paths(tmp)
            _seed_state(tmp, entries=[entry_rec])
            mgr = FakeOrderManager({
                'cid_rejected': {
                    'id': 'order_rejected',
                    'client_order_id': 'cid_rejected',
                    'status': 'rejected',
                }
            })

            result = reconcile_pending_orders(
                alpaca_manager=mgr,
                today_str='2026-03-03',
                state_dir=tmp,
            )

            assert len(result['entries_cancelled']) == 1
            assert _read(paths.trades) == []
            assert _read(paths.pending_entries) == []

    def test_unresolved_entry_is_retained_and_logged(self, monkeypatch, tmp_path):
        import scripts.reconcile_pending_orders as mod
        from src.paper_state import get_state_paths

        entry_rec = {
            'symbol': 'WAIT',
            'trade_date': '2026-03-03',
            'timing': 'bmo',
            'submission_status': 'pending',
            'submitted_client_order_id': 'cid_wait',
            'submitted_shares': 10,
        }
        state_dir = tmp_path / 'state'
        paths = get_state_paths(str(state_dir))
        _seed_state(state_dir, entries=[entry_rec])
        monkeypatch.setattr(mod, 'project_root', str(tmp_path))
        mgr = FakeOrderManager({
            'cid_wait': {
                'id': 'order_wait',
                'client_order_id': 'cid_wait',
                'status': 'accepted',
            }
        })

        result = mod.reconcile_pending_orders(
            alpaca_manager=mgr,
            today_str='2026-03-03',
            state_dir=str(state_dir),
        )

        assert len(result['entries_unresolved']) == 1
        assert _read(paths.pending_entries) == [entry_rec]
        log_path = tmp_path / 'logs' / 'paper_dryrun' / 'orders_unresolved_2026-03-03.log'
        assert log_path.exists()
        assert '"kind": "entry"' in log_path.read_text()
