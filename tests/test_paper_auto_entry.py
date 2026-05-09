"""Tests for scripts/paper_auto_entry.py"""

import pytest
import json
import os
import sys
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.alpaca_order_manager import AlpacaOrderManager


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Create a temporary data directory with empty state files."""
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    (data_dir / 'paper_trades.json').write_text('[]')
    (data_dir / 'pending_entries.json').write_text('[]')
    (data_dir / 'pending_exits.json').write_text('[]')
    return str(data_dir)


@pytest.fixture
def patch_paths(tmp_data_dir):
    """Patch all file paths to use tmp dir."""
    import scripts.paper_auto_entry as mod
    original = {
        'DATA_DIR': mod.DATA_DIR,
        'TRADES_FILE': mod.TRADES_FILE,
        'PENDING_ENTRIES_FILE': mod.PENDING_ENTRIES_FILE,
        'PENDING_EXITS_FILE': mod.PENDING_EXITS_FILE,
        'LOCK_FILE': mod.LOCK_FILE,
    }
    mod.DATA_DIR = tmp_data_dir
    mod.TRADES_FILE = os.path.join(tmp_data_dir, 'paper_trades.json')
    mod.PENDING_ENTRIES_FILE = os.path.join(tmp_data_dir, 'pending_entries.json')
    mod.PENDING_EXITS_FILE = os.path.join(tmp_data_dir, 'pending_exits.json')
    mod.LOCK_FILE = os.path.join(tmp_data_dir, '.paper_state.lock')
    yield mod
    # Restore
    for k, v in original.items():
        setattr(mod, k, v)


class TestCheckRiskGate:

    def test_allows_when_no_trades(self):
        from scripts.paper_auto_entry import check_risk_gate
        assert check_risk_gate([], 100000) is True

    def test_allows_when_losses_within_limit(self):
        from scripts.paper_auto_entry import check_risk_gate
        today = datetime.now().strftime('%Y-%m-%d')
        trades = [{
            'legs': [{'action': 'exit_stop', 'date': today, 'pnl': -3000}]
        }]
        # -3000 / 100000 = -3%, within -6% limit
        assert check_risk_gate(trades, 100000) is True

    def test_blocks_when_losses_exceed_limit(self):
        from scripts.paper_auto_entry import check_risk_gate
        today = datetime.now().strftime('%Y-%m-%d')
        trades = [{
            'legs': [{'action': 'exit_stop', 'date': today, 'pnl': -7000}]
        }]
        # -7000 / 100000 = -7%, exceeds -6% limit
        assert check_risk_gate(trades, 100000) is False

    def test_includes_partial_profit_in_calculation(self):
        from scripts.paper_auto_entry import check_risk_gate
        today = datetime.now().strftime('%Y-%m-%d')
        trades = [{
            'legs': [
                {'action': 'exit_stop', 'date': today, 'pnl': -5500},
                {'action': 'exit_partial', 'date': today, 'pnl': 200},
            ]
        }]
        # net = -5300 / 100000 = -5.3%, within limit
        assert check_risk_gate(trades, 100000) is True


class TestExecutePending:

    def test_exits_before_entries(self, patch_paths):
        """Exit symbols are excluded from entry plan."""
        mod = patch_paths

        # Setup: pending exit AND pending entry for same symbol
        with open(mod.PENDING_EXITS_FILE, 'w') as f:
            json.dump([{'symbol': 'VSNT', 'shares': 45, 'reason': 'stop_loss'}], f)
        with open(mod.PENDING_ENTRIES_FILE, 'w') as f:
            json.dump([
                {'symbol': 'VSNT', 'timing': None, 'date': '2026-03-03',
                 'prev_close': 33.0, 'score': 85},
                {'symbol': 'AAPL', 'timing': None, 'date': '2026-03-03',
                 'prev_close': 150.0, 'score': 70},
            ], f)
        # Also need an open trade for VSNT so the exit has something to close
        with open(mod.TRADES_FILE, 'w') as f:
            json.dump([{
                'symbol': 'VSNT', 'entry_date': '2026-03-01', 'entry_price': 30.0,
                'initial_shares': 45, 'remaining_shares': 45,
                'stop_loss_price': 27.0, 'status': 'open', 'legs': [],
            }], f)

        mock_mgr = Mock()
        mock_mgr.get_positions.return_value = []
        mock_mgr.get_account_summary.return_value = {
            'portfolio_value': 100000, 'buying_power': 100000,
        }
        mock_mgr.submit_market_order.return_value = {
            'id': 'o1', 'status': 'filled', 'filled_avg_price': 28.0,
            'client_order_id': 'test',
        }

        with patch.object(mod, 'AlpacaOrderManager', return_value=mock_mgr) as MockCls:
            MockCls.calculate_position_size = AlpacaOrderManager.calculate_position_size
            MockCls.make_client_order_id = AlpacaOrderManager.make_client_order_id
            with patch.object(mod, 'get_today_str', return_value='2026-03-04'):
                mod.execute_pending(dry_run=False)

        # VSNT should be sold (exit) but NOT bought (excluded from entries)
        # AAPL should be bought (not in exit symbols)
        calls = mock_mgr.submit_market_order.call_args_list
        sell_symbols = [c.kwargs.get('symbol') or c[0][0] for c in calls if (c.kwargs.get('side') or c[1].get('side', c[0][1] if len(c[0]) > 1 else '')) == 'sell']
        buy_symbols = [c.kwargs.get('symbol') or c[0][0] for c in calls if (c.kwargs.get('side') or c[1].get('side', c[0][1] if len(c[0]) > 1 else '')) == 'buy']

        assert 'VSNT' in sell_symbols, "VSNT should be sold (exit)"
        assert 'VSNT' not in buy_symbols, "VSNT should NOT be re-bought (excluded)"
        assert 'AAPL' in buy_symbols, "AAPL should be bought"

    def test_duplicate_order_not_recorded(self, patch_paths):
        """Duplicate orders should not update paper_trades.json."""
        mod = patch_paths

        with open(mod.PENDING_ENTRIES_FILE, 'w') as f:
            json.dump([{'symbol': 'TEST', 'timing': None, 'date': '2026-03-03',
                        'prev_close': 50.0, 'score': 70}], f)

        mock_mgr = Mock()
        mock_mgr.get_positions.return_value = []
        mock_mgr.get_account_summary.return_value = {
            'portfolio_value': 100000, 'buying_power': 100000,
        }
        # Return duplicate status
        mock_mgr.submit_market_order.return_value = {
            'status': 'duplicate', 'client_order_id': 'TEST_2026-03-03_entry_bmo_buy'
        }

        with patch.object(mod, 'AlpacaOrderManager', return_value=mock_mgr) as MockCls:
            MockCls.calculate_position_size = AlpacaOrderManager.calculate_position_size
            MockCls.make_client_order_id = AlpacaOrderManager.make_client_order_id
            with patch.object(mod, 'get_today_str', return_value='2026-03-03'):
                mod.execute_pending(dry_run=False)

        with open(mod.TRADES_FILE) as f:
            trades = json.load(f)
        assert len(trades) == 0  # no trade recorded for duplicate

    def test_successful_entry_recorded(self, patch_paths):
        """Successful market order should create a trade record."""
        mod = patch_paths

        # timing=None to skip live re-verification (which needs real price data)
        with open(mod.PENDING_ENTRIES_FILE, 'w') as f:
            json.dump([{'symbol': 'AAPL', 'timing': None, 'date': '2026-03-03',
                        'prev_close': 150.0, 'score': 70,
                        'entry_price_est': 155.0, 'gap_percent': 3.3,
                        'eps_surprise': 10.0}], f)

        mock_mgr = Mock()
        mock_mgr.get_positions.return_value = []
        mock_mgr.get_account_summary.return_value = {
            'portfolio_value': 100000, 'buying_power': 100000,
        }
        mock_mgr.submit_market_order.return_value = {
            'id': 'order123', 'status': 'filled', 'filled_avg_price': 155.50,
            'client_order_id': 'AAPL_2026-03-03_entry_bmo_buy',
        }

        with patch.object(mod, 'AlpacaOrderManager', return_value=mock_mgr) as MockCls:
            MockCls.calculate_position_size = AlpacaOrderManager.calculate_position_size
            MockCls.make_client_order_id = AlpacaOrderManager.make_client_order_id
            with patch.object(mod, 'get_today_str', return_value='2026-03-03'):
                mod.execute_pending(dry_run=False)

        with open(mod.TRADES_FILE) as f:
            trades = json.load(f)
        assert len(trades) == 1
        assert trades[0]['symbol'] == 'AAPL'
        assert trades[0]['status'] == 'open'
        assert trades[0]['entry_price'] == 155.50
        assert len(trades[0]['legs']) == 1
        assert trades[0]['legs'][0]['action'] == 'entry'

    def test_pending_entries_cleared_after_success(self, patch_paths):
        """Successful entries should be removed from pending_entries.json."""
        mod = patch_paths

        with open(mod.PENDING_ENTRIES_FILE, 'w') as f:
            json.dump([{'symbol': 'TEST', 'timing': None, 'date': '2026-03-03',
                        'prev_close': 50.0, 'score': 70}], f)

        mock_mgr = Mock()
        mock_mgr.get_positions.return_value = []
        mock_mgr.get_account_summary.return_value = {
            'portfolio_value': 100000, 'buying_power': 100000,
        }
        mock_mgr.submit_market_order.return_value = {
            'id': 'o1', 'status': 'filled', 'filled_avg_price': 51.0,
            'client_order_id': 'TEST_2026-03-03_entry_bmo_buy',
        }

        with patch.object(mod, 'AlpacaOrderManager', return_value=mock_mgr) as MockCls:
            MockCls.calculate_position_size = AlpacaOrderManager.calculate_position_size
            MockCls.make_client_order_id = AlpacaOrderManager.make_client_order_id
            with patch.object(mod, 'get_today_str', return_value='2026-03-03'):
                mod.execute_pending(dry_run=False)

        with open(mod.PENDING_ENTRIES_FILE) as f:
            pending = json.load(f)
        assert len(pending) == 0

    def test_failed_entry_stays_in_pending(self, patch_paths):
        """Failed entries should remain in pending_entries.json."""
        mod = patch_paths

        with open(mod.PENDING_ENTRIES_FILE, 'w') as f:
            json.dump([{'symbol': 'FAIL', 'timing': None, 'date': '2026-03-03',
                        'prev_close': 50.0, 'score': 70}], f)

        mock_mgr = Mock()
        mock_mgr.get_positions.return_value = []
        mock_mgr.get_account_summary.return_value = {
            'portfolio_value': 100000, 'buying_power': 100000,
        }
        mock_mgr.submit_market_order.side_effect = Exception("API error")

        with patch.object(mod, 'AlpacaOrderManager', return_value=mock_mgr) as MockCls:
            MockCls.calculate_position_size = AlpacaOrderManager.calculate_position_size
            MockCls.make_client_order_id = AlpacaOrderManager.make_client_order_id
            with patch.object(mod, 'get_today_str', return_value='2026-03-03'):
                mod.execute_pending(dry_run=False)

        with open(mod.PENDING_ENTRIES_FILE) as f:
            pending = json.load(f)
        assert len(pending) == 1
        assert pending[0]['symbol'] == 'FAIL'

    def test_dry_run_uses_injected_state_dir_and_records_fill(self, tmp_data_dir):
        """dry-run should use DryRunAccount and persist only to the injected state dir."""
        import scripts.paper_auto_entry as mod

        pending_entries = os.path.join(tmp_data_dir, 'pending_entries.json')
        trades_file = os.path.join(tmp_data_dir, 'paper_trades.json')
        with open(pending_entries, 'w') as f:
            json.dump([{
                'symbol': 'DRY',
                'timing': None,
                'date': '2026-03-03',
                'entry_price_est': 50.0,
                'score': 70,
            }], f)

        fake_fetcher = Mock()
        fake_fetcher.get_preopen_price.return_value = 50.0

        result = mod.execute_pending(
            dry_run=True,
            data_fetcher=fake_fetcher,
            today_str='2026-03-03',
            state_dir=tmp_data_dir,
        )

        assert [e['symbol'] for e in result['entries_placed']] == ['DRY']
        with open(trades_file) as f:
            trades = json.load(f)
        assert len(trades) == 1
        assert trades[0]['symbol'] == 'DRY'
        assert trades[0]['entry_price'] == 50.0
        with open(pending_entries) as f:
            pending = json.load(f)
        assert pending == []

    def test_not_filled_entry_is_annotated_for_reconciliation(self, tmp_data_dir):
        """accepted/new orders that do not fill inside polling stay pending with submission metadata."""
        import scripts.paper_auto_entry as mod

        pending_entries = os.path.join(tmp_data_dir, 'pending_entries.json')
        with open(pending_entries, 'w') as f:
            json.dump([{
                'symbol': 'LATE',
                'timing': None,
                'date': '2026-03-03',
                'entry_price_est': 40.0,
                'score': 70,
            }], f)

        mock_mgr = Mock()
        mock_mgr.get_positions.return_value = []
        mock_mgr.get_account_summary.return_value = {
            'portfolio_value': 100000,
            'buying_power': 100000,
        }
        mock_mgr.submit_market_order.return_value = {
            'id': 'accepted1',
            'status': 'accepted',
            'client_order_id': 'late-order',
        }
        mock_mgr.get_order_by_client_id.return_value = None

        with patch.object(mod, 'MAX_POLL_TRIES', 0):
            result = mod.execute_pending(
                dry_run=False,
                alpaca_manager=mock_mgr,
                today_str='2026-03-03',
                state_dir=tmp_data_dir,
            )

        assert result['entries_placed'] == []
        assert result['entries_skipped'][0]['reason'] == 'not_filled'
        with open(pending_entries) as f:
            pending = json.load(f)
        assert len(pending) == 1
        assert pending[0]['symbol'] == 'LATE'
        assert pending[0]['submission_status'] == 'pending'
        assert pending[0]['submitted_client_order_id']
        assert pending[0]['submitted_shares'] > 0

    def test_pending_exit_submission_is_not_resubmitted_and_blocks_reentry(self, tmp_data_dir):
        """In-flight exit orders are reconciled by reconcile_pending_orders, not resubmitted."""
        import scripts.paper_auto_entry as mod

        with open(os.path.join(tmp_data_dir, 'pending_exits.json'), 'w') as f:
            json.dump([{
                'symbol': 'WAIT',
                'shares': 10,
                'reason': 'stop_loss',
                'submission_status': 'pending',
                'submitted_client_order_id': 'cid_wait_exit',
            }], f)
        with open(os.path.join(tmp_data_dir, 'pending_entries.json'), 'w') as f:
            json.dump([{
                'symbol': 'WAIT',
                'timing': None,
                'date': '2026-03-03',
                'entry_price_est': 40.0,
                'score': 70,
            }], f)

        mock_mgr = Mock()
        mock_mgr.get_positions.return_value = []
        mock_mgr.get_account_summary.return_value = {
            'portfolio_value': 100000,
            'buying_power': 100000,
        }

        result = mod.execute_pending(
            dry_run=False,
            alpaca_manager=mock_mgr,
            today_str='2026-03-03',
            state_dir=tmp_data_dir,
        )

        mock_mgr.submit_market_order.assert_not_called()
        assert result['exits_planned'] == []
        assert result['entries_placed'] == []
        assert result['entries_skipped'][0]['reason'] == 'already_pending_exit'


class TestScreenAndSave:

    def test_dry_run_screen_persists_to_dryrun_state_dir(self, tmp_path, tmp_data_dir):
        """screen dry-run must persist candidates so execute dry-run can consume them."""
        import scripts.paper_auto_entry as mod

        reports_dir = tmp_path / 'reports' / 'screener'
        reports_dir.mkdir(parents=True)
        csv_path = reports_dir / 'daily_candidates_2026-03-03.csv'
        csv_path.write_text(
            "symbol,trade_date,prev_close,entry_price,score,eps_surprise_percent,gap_percent\n"
            "DRY,2026-03-03,49.0,50.0,70,12.5,2.0\n"
        )

        completed = Mock()
        completed.returncode = 0
        completed.stderr = ''
        with patch.object(mod, 'project_root', str(tmp_path)):
            with patch.object(mod.subprocess, 'run', return_value=completed):
                with patch.object(mod, 'get_today_str', return_value='2026-03-03'):
                    mod.screen_and_save('bmo', dry_run=True, state_dir=tmp_data_dir)

        with open(os.path.join(tmp_data_dir, 'pending_entries.json')) as f:
            pending = json.load(f)
        assert len(pending) == 1
        assert pending[0]['symbol'] == 'DRY'
        assert pending[0]['trade_date'] == '2026-03-03'
        assert pending[0]['eps_surprise_percent'] == 12.5
