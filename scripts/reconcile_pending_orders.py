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

The live path is intentionally small and mirrors the state-update shape used
by ``scripts.paper_auto_entry.execute_pending``: confirmed entry fills append
open trades; confirmed exit fills append exit legs and decrement remaining
shares; unresolved orders stay pending for manual triage.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python <3.9 fallback
    ZoneInfo = None

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from filelock import FileLock
from src.alpaca_order_manager import AlpacaOrderManager
from src.config import DEFAULTS
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


def _save_json_atomic(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _today_str() -> str:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d')
    return datetime.now().strftime('%Y-%m-%d')


def _has_positive_fill_price(order: Optional[Dict[str, Any]]) -> bool:
    if not order:
        return False
    try:
        return float(order.get('filled_avg_price')) > 0
    except (TypeError, ValueError):
        return False


def _is_filled(order: Optional[Dict[str, Any]]) -> bool:
    if not order or order.get('status') != 'filled':
        return False
    return _has_positive_fill_price(order)


def _filled_qty(order: Dict[str, Any], fallback: int) -> int:
    try:
        return int(float(order.get('filled_qty', fallback) or fallback))
    except (TypeError, ValueError):
        return int(fallback)


def _pending_entry_key(rec: Dict[str, Any]) -> tuple:
    return (rec.get('symbol'), rec.get('trade_date') or rec.get('date'), rec.get('timing'))


def _pending_exit_key(rec: Dict[str, Any]) -> tuple:
    return (rec.get('symbol'), rec.get('reason'), int(rec.get('shares', 0) or 0))


def _apply_entry_fill(
    trades: List[Dict[str, Any]],
    rec: Dict[str, Any],
    order: Dict[str, Any],
    today_str: str,
) -> Dict[str, Any]:
    shares = _filled_qty(order, int(rec.get('submitted_shares', rec.get('shares', 0)) or 0))
    fill_price = float(order['filled_avg_price'])
    stop_price = fill_price * (1 - DEFAULTS.stop_loss / 100)
    trade = {
        'symbol': rec['symbol'],
        'entry_date': today_str,
        'entry_price': fill_price,
        'initial_shares': shares,
        'remaining_shares': shares,
        'stop_loss_price': round(stop_price, 2),
        'screener_score': rec.get('score', rec.get('eps_surprise_percent', 0)),
        'eps_surprise_percent': rec.get('eps_surprise_percent', rec.get('eps_surprise')),
        'gap_percent': rec.get('gap_percent'),
        'timing': rec.get('timing', ''),
        'status': 'open',
        'legs': [{
            'date': today_str,
            'action': 'entry',
            'shares': shares,
            'price': fill_price,
            'order_id': order.get('id', ''),
            'client_order_id': order.get('client_order_id', rec.get('submitted_client_order_id', '')),
        }],
    }
    trades.append(trade)
    return trade


def _apply_exit_fill(
    trades: List[Dict[str, Any]],
    rec: Dict[str, Any],
    order: Dict[str, Any],
    today_str: str,
) -> Optional[Dict[str, Any]]:
    shares = _filled_qty(order, int(rec.get('submitted_shares', rec.get('shares', 0)) or 0))
    fill_price = float(order['filled_avg_price'])
    for trade in trades:
        if trade.get('symbol') == rec.get('symbol') and trade.get('status') == 'open':
            pnl = (fill_price - float(trade.get('entry_price', 0) or 0)) * shares
            trade.setdefault('legs', []).append({
                'date': today_str,
                'action': f"exit_{rec.get('reason', 'unknown')}",
                'shares': shares,
                'price': fill_price,
                'pnl': round(pnl, 2),
                'reason': rec.get('reason', ''),
                'order_id': order.get('id', ''),
                'client_order_id': order.get('client_order_id', rec.get('submitted_client_order_id', '')),
            })
            trade['remaining_shares'] = int(trade.get('remaining_shares', 0) or 0) - shares
            if trade['remaining_shares'] <= 0:
                trade['status'] = 'closed'
            return {
                'symbol': rec.get('symbol'),
                'shares': shares,
                'fill_price': fill_price,
                'pnl': round(pnl, 2),
            }
    return None


def _resolve_order(mgr: Any, rec: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], str]:
    cid = rec.get('submitted_client_order_id')
    if not cid:
        return None, 'missing_client_order_id'
    order = mgr.get_order_by_client_id(cid)
    if _is_filled(order):
        return order, 'filled'
    if (
        order
        and order.get('status') == 'partially_filled'
        and _filled_qty(order, 0) > 0
        and _has_positive_fill_price(order)
    ):
        try:
            mgr.cancel_order(order.get('id'))
        except Exception as e:
            logger.warning('cancel_order_failed for %s: %s', cid, e)
        return order, 'partially_filled'
    if order and order.get('status') in ('cancelled', 'rejected'):
        return order, order.get('status')
    return order, 'unresolved'


def reconcile_pending_orders(
    *,
    alpaca_manager: Any = None,
    today_str: Optional[str] = None,
    state_dir: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Reconcile pending order metadata into paper state."""
    state_dir = state_dir or (DRYRUN_STATE_DIR if dry_run else LIVE_STATE_DIR)
    os.makedirs(state_dir, exist_ok=True)
    paths = get_state_paths(state_dir)
    today = today_str or _today_str()

    if dry_run:
        pending_entries = _load_pending(paths.pending_entries)
        pending_exits = _load_pending(paths.pending_exits)
        unresolved_entries = [p for p in pending_entries if p.get('submission_status') == 'pending']
        unresolved_exits = [p for p in pending_exits if p.get('submission_status') == 'pending']
        return {
            'dry_run': True,
            'entries_reconciled': [],
            'exits_reconciled': [],
            'entries_unresolved': unresolved_entries,
            'exits_unresolved': unresolved_exits,
            'entries_cancelled': [],
            'exits_cancelled': [],
        }

    mgr = alpaca_manager or AlpacaOrderManager(account_type='paper')
    entries_reconciled: List[Dict[str, Any]] = []
    exits_reconciled: List[Dict[str, Any]] = []
    entries_unresolved: List[Dict[str, Any]] = []
    exits_unresolved: List[Dict[str, Any]] = []
    entries_cancelled: List[Dict[str, Any]] = []
    exits_cancelled: List[Dict[str, Any]] = []

    with FileLock(paths.lock, timeout=30):
        trades = _load_pending(paths.trades)
        pending_entries = _load_pending(paths.pending_entries)
        pending_exits = _load_pending(paths.pending_exits)

        for rec in list(pending_entries):
            if rec.get('submission_status') != 'pending':
                continue
            order, status = _resolve_order(mgr, rec)
            if status in ('filled', 'partially_filled') and order:
                trade = _apply_entry_fill(trades, rec, order, today)
                entries_reconciled.append({'entry': rec, 'trade': trade, 'order': order})
                pending_entries = [
                    p for p in pending_entries if _pending_entry_key(p) != _pending_entry_key(rec)
                ]
            elif status in ('cancelled', 'rejected'):
                entries_cancelled.append({'entry': rec, 'order': order, 'reason': status})
                pending_entries = [
                    p for p in pending_entries if _pending_entry_key(p) != _pending_entry_key(rec)
                ]
            else:
                entries_unresolved.append({'entry': rec, 'order': order, 'reason': status})

        for rec in list(pending_exits):
            if rec.get('submission_status') != 'pending':
                continue
            order, status = _resolve_order(mgr, rec)
            if status in ('filled', 'partially_filled') and order:
                applied = _apply_exit_fill(trades, rec, order, today)
                if applied is None:
                    exits_unresolved.append({'exit': rec, 'order': order, 'reason': 'no_matching_open_trade'})
                    continue
                exits_reconciled.append({'exit': rec, 'applied': applied, 'order': order})
                pending_exits = [
                    p for p in pending_exits if _pending_exit_key(p) != _pending_exit_key(rec)
                ]
            elif status in ('cancelled', 'rejected'):
                exits_cancelled.append({'exit': rec, 'order': order, 'reason': status})
                pending_exits = [
                    p for p in pending_exits if _pending_exit_key(p) != _pending_exit_key(rec)
                ]
            else:
                exits_unresolved.append({'exit': rec, 'order': order, 'reason': status})

        _save_json_atomic(paths.trades, trades)
        _save_json_atomic(paths.pending_entries, pending_entries)
        _save_json_atomic(paths.pending_exits, pending_exits)

    if entries_unresolved or exits_unresolved:
        log_dir = os.path.join(project_root, 'logs', 'paper_dryrun')
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f'orders_unresolved_{today}.log')
        with open(log_path, 'a') as f:
            for item in entries_unresolved:
                f.write(json.dumps({'kind': 'entry', **item}, default=str) + '\n')
            for item in exits_unresolved:
                f.write(json.dumps({'kind': 'exit', **item}, default=str) + '\n')

    return {
        'dry_run': False,
        'entries_reconciled': entries_reconciled,
        'exits_reconciled': exits_reconciled,
        'entries_unresolved': entries_unresolved,
        'exits_unresolved': exits_unresolved,
        'entries_cancelled': entries_cancelled,
        'exits_cancelled': exits_cancelled,
    }


def main() -> int:
    args = parse_args()
    state_dir = args.state_dir or (DRYRUN_STATE_DIR if args.dry_run else LIVE_STATE_DIR)
    paths = get_state_paths(state_dir)

    today = _today_str()
    print(f'=== Reconcile Pending Orders ({today}) ===')
    print(f'State dir: {paths.state_dir}')

    if args.dry_run:
        # DryRunAccount fills immediately; no record ever has
        # submission_status='pending'. We still scan to confirm and report.
        result = reconcile_pending_orders(
            today_str=today, state_dir=state_dir, dry_run=True,
        )
        print(f"(dry-run) unresolved entries: {len(result['entries_unresolved'])}")
        print(f"(dry-run) unresolved exits:   {len(result['exits_unresolved'])}")
        if result['entries_unresolved'] or result['exits_unresolved']:
            print('NOTE: DryRunAccount fills should be immediate; '
                  'investigation needed if records exist with submission_status=pending.')
        return 0

    result = reconcile_pending_orders(
        today_str=today, state_dir=state_dir, dry_run=False,
    )
    print(f"entries reconciled: {len(result['entries_reconciled'])}")
    print(f"exits reconciled:   {len(result['exits_reconciled'])}")
    print(f"entries unresolved: {len(result['entries_unresolved'])}")
    print(f"exits unresolved:   {len(result['exits_unresolved'])}")
    print(f"entries cancelled:  {len(result['entries_cancelled'])}")
    print(f"exits cancelled:    {len(result['exits_cancelled'])}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
