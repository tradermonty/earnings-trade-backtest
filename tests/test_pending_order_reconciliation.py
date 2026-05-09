"""Phase 5 parity test: reconcile_pending_orders dry-run is no-op.

The live reconciliation logic is wired in conjunction with the
``execute_pending`` 6-phase refactor (Phase 3c follow-up). This test
locks in the current contract:

- Dry-run mode never instantiates Alpaca (no API key required).
- Dry-run reports 0 unresolved entries/exits when state is empty.
- ``DryRunAccount`` fills are immediate, so no record ever has
  ``submission_status == 'pending'`` in dry-run state.

When the live path is wired, additional tests will cover the
post-09:30 fill discovery flow.
"""

import json
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECONCILE_SCRIPT = os.path.join(PROJECT_ROOT, 'scripts', 'reconcile_pending_orders.py')
PYTHON = sys.executable


def _seed_state(state_dir):
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, 'paper_trades.json'), 'w') as f:
        json.dump([], f)
    with open(os.path.join(state_dir, 'pending_entries.json'), 'w') as f:
        json.dump([], f)
    with open(os.path.join(state_dir, 'pending_exits.json'), 'w') as f:
        json.dump([], f)


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
            _seed_state(tmp)
            with open(os.path.join(tmp, 'pending_entries.json'), 'w') as f:
                json.dump([{
                    'symbol': 'AAPL', 'trade_date': '2025-06-15', 'timing': 'amc',
                    'submission_status': 'pending',
                    'submitted_client_order_id': 'cid_x',
                }], f)
            result = subprocess.run(
                [PYTHON, RECONCILE_SCRIPT, '--dry-run', '--state-dir', tmp],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0
            assert 'unresolved entries: 1' in result.stdout
            assert 'investigation needed' in result.stdout

    def test_dry_run_does_not_require_alpaca_keys(self, monkeypatch):
        """Dry-run path must never instantiate AlpacaOrderManager."""
        # Run in a clean env — would fail with ValueError if AlpacaOrderManager
        # were instantiated and ALPACA_API_KEY_PAPER weren't set.
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


class TestDocumentedContract:
    """Live path is intentionally a no-op stub for now (Phase 3c follow-up).

    Once wired, add tests for: filled discovery, partial-fill remainder cancel,
    rejected/cancelled handling, unresolved logging.
    """

    def test_live_path_runs_cleanly_as_stub(self):
        with tempfile.TemporaryDirectory() as tmp:
            _seed_state(tmp)
            # Live path needs Alpaca env to instantiate AlpacaOrderManager
            # in the future. The current stub doesn't construct one, so it
            # exits cleanly without keys. Once wired, this test gets updated.
            result = subprocess.run(
                [PYTHON, RECONCILE_SCRIPT, '--state-dir', tmp],
                capture_output=True, text=True, timeout=30,
            )
            assert result.returncode == 0
            assert 'not yet wired' in result.stdout
