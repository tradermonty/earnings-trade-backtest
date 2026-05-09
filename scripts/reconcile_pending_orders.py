#!/usr/bin/env python3
"""Reconcile pending Alpaca orders that didn't fill within `execute_pending`'s polling window.

Runs at 16:03 ET (between AMC screen at 16:00 and exit monitor at 16:05) to
discover orders that returned ``accepted``/``new`` at 09:30 but filled later
in the day. Without this step, `paper_exit_monitor` wouldn't see the
positions at 16:05 and live state would drift from reality.

State contract:
- A ``pending_entries.json`` or ``pending_exits.json`` record with
  ``submission_status == 'pending'`` carries the ``submitted_client_order_id``,
  ``submitted_shares``, and ``submitted_reference_price`` set by
  ``execute_pending`` when polling exhausted.
- This script polls Alpaca for each such record. If filled (or
  partially-filled with cancel-remainder), it applies the same Phase 6
  state-update logic as ``execute_pending`` and removes the record from
  pending. Persistent ``accepted``/``new`` records are logged to
  ``logs/paper_dryrun/orders_unresolved_{today}.log`` for manual triage.

Dry-run mode is a no-op: ``DryRunAccount`` fills are immediate, so no record
ever reaches ``submission_status == 'pending'``.

Usage:
    python scripts/reconcile_pending_orders.py            # live
    python scripts/reconcile_pending_orders.py --dry-run  # no-op (DryRunAccount fills are immediate)

Status: scaffolding only — full live reconciliation logic is implemented
in conjunction with the `execute_pending` 6-phase refactor (Phase 3c). For
now, the script is callable and exits cleanly so cron entries can be
installed without breakage.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from src.paper_state import DRYRUN_STATE_DIR, LIVE_STATE_DIR, get_state_paths

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Reconcile pending Alpaca orders.')
    p.add_argument('--dry-run', action='store_true',
                   help='No-op: DryRunAccount fills are immediate.')
    p.add_argument('--state-dir', default=None,
                   help='Override state directory (defaults to live or dryrun based on --dry-run).')
    return p.parse_args()


def _load_pending(path: str) -> list:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def main() -> int:
    args = parse_args()
    state_dir = args.state_dir or (DRYRUN_STATE_DIR if args.dry_run else LIVE_STATE_DIR)
    paths = get_state_paths(state_dir)

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    print(f'=== Reconcile Pending Orders ({today}) ===')
    print(f'State dir: {paths.state_dir}')

    if args.dry_run:
        # DryRunAccount fills immediately; no record ever has
        # submission_status='pending'. We still scan to confirm and report.
        pending_entries = _load_pending(paths.pending_entries)
        pending_exits = _load_pending(paths.pending_exits)
        unresolved_entries = [
            p for p in pending_entries
            if p.get('submission_status') == 'pending'
        ]
        unresolved_exits = [
            p for p in pending_exits
            if p.get('submission_status') == 'pending'
        ]
        print(f'(dry-run) unresolved entries: {len(unresolved_entries)}')
        print(f'(dry-run) unresolved exits:   {len(unresolved_exits)}')
        if unresolved_entries or unresolved_exits:
            print('NOTE: DryRunAccount fills should be immediate; '
                  'investigation needed if records exist with submission_status=pending.')
        return 0

    # TODO: live reconciliation — to be wired in conjunction with the
    # ``execute_pending`` 6-phase refactor (Phase 3c) which sets
    # ``submission_status='pending'`` on polling exhaustion. The required
    # logic mirrors ``_submit_with_reconciliation``'s post-poll branch:
    #   for each pending record:
    #     existing = mgr.get_order_by_client_id(rec['submitted_client_order_id'])
    #     if _is_filled(existing): apply Phase-6 state update; mark reconciled.
    #     elif partially_filled and filled_qty > 0: cancel + apply partial.
    #     elif rejected/cancelled: mark cancelled; remove pending.
    #     else: log to logs/paper_dryrun/orders_unresolved_{today}.log
    print('Live reconciliation logic not yet wired (Phase 3c follow-up).')
    print('See docs/parity_notes.md §4.6 for the contract.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
