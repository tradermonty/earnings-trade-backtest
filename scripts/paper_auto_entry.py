#!/usr/bin/env python3
"""
Paper Trading Auto Entry
全自動エントリー（cron で起動）

Modes:
  --screen-bmo    9:00 AM: Screen BMO candidates → save to pending_entries.json
  --screen-amc   16:00:    Screen AMC candidates → save to pending_entries.json
  --execute       9:30 AM: Execute pending exits (sell) then entries (buy)
  --dry-run       Preview without placing orders or modifying state

Usage:
  python scripts/paper_auto_entry.py --screen-bmo
  python scripts/paper_auto_entry.py --screen-amc
  python scripts/paper_auto_entry.py --execute
  python scripts/paper_auto_entry.py --execute --dry-run
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from filelock import FileLock
from src.alpaca_order_manager import AlpacaOrderManager
from src.config import DEFAULTS
from src.paper_state import (
    DRYRUN_STATE_DIR,
    DryRunAccount,
    LIVE_STATE_DIR,
    StatePaths,
    get_state_paths,
)

logger = logging.getLogger(__name__)

# Legacy module-level paths preserved for backwards compatibility with existing
# tests that import them. New code should use ``get_state_paths(state_dir)``
# which resolves to either ``LIVE_STATE_DIR`` or ``DRYRUN_STATE_DIR``.
DATA_DIR = LIVE_STATE_DIR
_LIVE_PATHS = get_state_paths(LIVE_STATE_DIR)
TRADES_FILE = _LIVE_PATHS.trades
PENDING_ENTRIES_FILE = _LIVE_PATHS.pending_entries
PENDING_EXITS_FILE = _LIVE_PATHS.pending_exits
LOCK_FILE = _LIVE_PATHS.lock

# Strategy parameters are sourced from DEFAULTS (src/config.py); no local hardcodes.
# Use DEFAULTS.position_size, DEFAULTS.slippage, DEFAULTS.stop_loss,
# DEFAULTS.margin_ratio, DEFAULTS.risk_limit, DEFAULTS.min_volume_20d directly.

# Polling configuration for ``_submit_with_reconciliation`` (Phase 3c).
# Live submission may return ``accepted``/``new`` momentarily before a fill.
# Total wait = MAX_POLL_TRIES * POLL_INTERVAL_S = 20s.
MAX_POLL_TRIES = 10
POLL_INTERVAL_S = 2


def _resolve_state_paths(state_dir: Optional[str], dry_run: bool) -> StatePaths:
    """Resolve state paths, preferring explicit state_dir then dry-run isolation."""
    if state_dir is None:
        state_dir = DRYRUN_STATE_DIR if dry_run else LIVE_STATE_DIR
    os.makedirs(state_dir, exist_ok=True)
    return get_state_paths(state_dir)


def _is_filled(result: Optional[Dict[str, Any]]) -> bool:
    """Strict success: status == 'filled' AND filled_avg_price is positive."""
    if not result:
        return False
    if result.get('status') != 'filled':
        return False
    fap = result.get('filled_avg_price')
    return isinstance(fap, (int, float)) and fap > 0


def _skip_entry(en: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Uniform skip record: carries source entry so cleanup keys are unambiguous."""
    return {
        'entry': en,
        'symbol': en.get('symbol'),
        'trade_date': en.get('trade_date'),
        'timing': en.get('timing'),
        'reason': reason,
    }


def _skip_exit(ex: Dict[str, Any], reason: str) -> Dict[str, Any]:
    return {
        'exit': ex,
        'symbol': ex.get('symbol'),
        'reason': reason,
    }


def _submit_with_reconciliation(
    mgr: Any,
    symbol: str,
    shares: int,
    side: str,
    cid: str,
    *,
    reference_price: float,
) -> 'tuple[Dict[str, Any], int, str, Optional[str]]':
    """Submit a market order with strict-fill semantics, polling, and partial-fill handling.

    Returns ``(result, filled_shares, outcome, skip_reason)`` where:

    - ``outcome`` ∈ {``filled_full``, ``filled_partial``, ``pending_unfilled``,
      ``duplicate_unfilled``, ``rejected``, ``submit_error``}
    - ``skip_reason`` is None for successful fills (filled_full / filled_partial)
      and a short string for failures.

    Behavior:

    - On ``status == 'duplicate'``: look up the prior order by client_order_id.
      If filled, treat as success. Otherwise mark ``duplicate_unfilled``.
    - If the initial result is not ``filled``: poll
      ``mgr.get_order_by_client_id(cid)`` up to ``MAX_POLL_TRIES`` times every
      ``POLL_INTERVAL_S`` seconds (total ~20s). Cancel any partially-filled
      remainder and return the filled portion.
    - On polling exhaustion: return ``pending_unfilled`` so caller can persist
      submission metadata for ``reconcile_pending_orders`` to resolve later.

    The caller passes ``reference_price`` so dry-run paths
    (``DryRunAccount.submit_market_order``) can fabricate a deterministic
    fill price; live paths ignore it via ``**_`` absorbing.
    """
    import time as _time

    try:
        result = mgr.submit_market_order(
            symbol, shares, side=side, client_order_id=cid,
            reference_price=reference_price,
        )
        if result.get('status') == 'duplicate':
            existing = mgr.get_order_by_client_id(cid)
            if existing and _is_filled(existing):
                return existing, int(existing.get('filled_qty', shares)), 'filled_full', None
            return result, 0, 'duplicate_unfilled', 'duplicate_unfilled'
        if _is_filled(result):
            return result, int(result.get('filled_qty', shares)), 'filled_full', None
        # Not immediately filled — poll for late fill
        for _ in range(MAX_POLL_TRIES):
            _time.sleep(POLL_INTERVAL_S)
            existing = mgr.get_order_by_client_id(cid)
            if not existing:
                continue
            status = existing.get('status')
            if _is_filled(existing):
                return existing, int(existing.get('filled_qty', shares)), 'filled_full', None
            if status == 'partially_filled' and int(existing.get('filled_qty', 0)) > 0:
                # Cancel remainder; record the filled portion as a partial success.
                try:
                    mgr.cancel_order(existing.get('id'))
                except Exception as e:
                    logger.warning(
                        'cancel_order_failed for %s (%s): %s',
                        symbol, existing.get('id'), e,
                    )
                return existing, int(existing['filled_qty']), 'filled_partial', None
            if status in ('rejected', 'cancelled'):
                return existing, 0, 'rejected', status
        # Polling exhausted — let reconcile_pending_orders resolve later.
        return result, 0, 'pending_unfilled', 'not_filled'
    except Exception as e:
        return {'error': str(e)}, 0, 'submit_error', f'submit_error_{str(e)[:40]}'


def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def save_json_atomic(path, data):
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


def get_today_str():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d')
    except ImportError:
        return datetime.now().strftime('%Y-%m-%d')


def check_risk_gate(
    trades: List[Dict],
    portfolio_value: float,
    today_str: Optional[str] = None,
) -> bool:
    """Check if new entries are allowed based on recent P&L.

    Returns True if new entries are allowed. Matches
    ``RiskManager.check_risk_management()`` logic: block if realized losses
    in the last 30 days exceed ``DEFAULTS.risk_limit`` (%).

    ``today_str`` is the canonical "now" for replay-deterministic tests.
    Defaults to ``get_today_str()`` for live execution. Phase 3c (rev 11)
    fix: explicit injection so parity tests don't depend on wall-clock.
    """
    if today_str is None:
        today_str = get_today_str()
    now = datetime.strptime(today_str, '%Y-%m-%d')
    total_pnl = 0.0

    for trade in trades:
        for leg in trade.get('legs', []):
            if leg.get('action', '').startswith('exit'):
                leg_date = datetime.strptime(leg['date'], '%Y-%m-%d')
                if (now - leg_date).days <= 30:
                    total_pnl += leg.get('pnl', 0)

    if portfolio_value > 0:
        pnl_ratio = (total_pnl / portfolio_value) * 100
        if pnl_ratio < -DEFAULTS.risk_limit:
            print(f"RISK GATE: Recent 30-day P&L {pnl_ratio:.1f}% exceeds "
                  f"-{DEFAULTS.risk_limit}% limit. Blocking new entries.")
            return False

    return True


# --- Screen Modes ---

def screen_and_save(timing: str, dry_run: bool = False):
    """Run screener with --market_timing and save to pending_entries.json."""
    today = get_today_str()
    print(f"=== Screen {timing.upper()} candidates ({today}) ===")

    # Run screener as subprocess
    cmd = [
        sys.executable,
        os.path.join(project_root, 'scripts', 'screen_daily_candidates.py'),
        '--date', today,
        '--market_timing', timing,
        '--verbose',
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        print(f"Screener failed (exit {result.returncode})")
        print(result.stderr[:500] if result.stderr else '')
        return

    # Read the generated CSV
    import csv
    import glob

    # Find the CSV matching today (screener may generate it)
    csv_pattern = os.path.join(project_root, 'reports', 'screener',
                               f'daily_candidates_{today}.csv')
    if not os.path.exists(csv_pattern):
        print(f"No CSV found at {csv_pattern}")
        return

    with open(csv_pattern) as f:
        reader = csv.DictReader(f)
        candidates = [r for r in reader if r.get('symbol')]

    if not candidates:
        print("No candidates found.")
        return

    # Build pending entries
    entries = []
    for c in candidates:
        entry = {
            'symbol': c['symbol'],
            'timing': timing,
            'date': today,
            'prev_close': float(c.get('prev_close', 0)),
            'entry_price_est': float(c.get('entry_price', 0)),
            'score': float(c.get('score', 0)),
            'eps_surprise': float(c.get('eps_surprise_percent', 0)),
            'gap_percent': float(c.get('gap_percent', 0)),
        }
        entries.append(entry)
        print(f"  Candidate: {entry['symbol']} score={entry['score']:.1f} "
              f"gap={entry['gap_percent']:.1f}%")

    if dry_run:
        print(f"\n(dry-run) Would save {len(entries)} entries to pending_entries.json")
        return

    lock = FileLock(LOCK_FILE, timeout=30)
    with lock:
        existing = load_json(PENDING_ENTRIES_FILE)
        # Dedupe by (symbol, date, timing) to handle re-runs
        existing_keys = {
            (e['symbol'], e['date'], e.get('timing'))
            for e in existing
        }
        new_entries = [
            e for e in entries
            if (e['symbol'], e['date'], e.get('timing')) not in existing_keys
        ]
        skipped = len(entries) - len(new_entries)
        existing.extend(new_entries)
        save_json_atomic(PENDING_ENTRIES_FILE, existing)

    if skipped > 0:
        print(f"\n  Deduplicated: {skipped} entries already pending")
    print(f"Saved {len(new_entries)} new entries to pending_entries.json")


# --- Execute Mode ---

def execute_pending(dry_run: bool = False):
    """Execute pending exits then entries at market open."""
    today = get_today_str()
    print(f"=== Execute Pending Orders ({today}) ===")

    mgr = AlpacaOrderManager(account_type='paper')
    lock = FileLock(LOCK_FILE, timeout=30)

    # Phase 1: Plan (short lock)
    with lock:
        pending_exits = load_json(PENDING_EXITS_FILE)
        pending_entries = load_json(PENDING_ENTRIES_FILE)
        trades = load_json(TRADES_FILE)

    exit_symbols = {e['symbol'] for e in pending_exits}

    # Remove entries for symbols being exited
    entry_plan = [e for e in pending_entries if e['symbol'] not in exit_symbols]
    removed = len(pending_entries) - len(entry_plan)
    if removed > 0:
        print(f"Removed {removed} entries for symbols with pending exits")

    # Check existing positions to avoid duplicates
    current_positions = {p['symbol'] for p in mgr.get_positions()}
    entry_plan = [e for e in entry_plan if e['symbol'] not in current_positions
                  or e['symbol'] in exit_symbols]  # allow re-entry after exit only if also exiting

    print(f"Exit plan: {len(pending_exits)} sells")
    print(f"Entry plan: {len(entry_plan)} buys")

    if dry_run:
        for ex in pending_exits:
            print(f"  [DRY] SELL {ex['symbol']} {ex['shares']} shares ({ex['reason']})")
        for en in entry_plan:
            print(f"  [DRY] BUY {en['symbol']} (prev_close=${en['prev_close']:.2f})")
        print("(dry-run) No orders placed.")
        return

    # Phase 2a: Execute Exits (no lock)
    exit_results = []
    for ex in pending_exits:
        cid = AlpacaOrderManager.make_client_order_id(
            ex['symbol'], today, f"exit_{ex['reason']}", 'sell'
        )
        try:
            result = mgr.submit_market_order(
                ex['symbol'], ex['shares'], side='sell', client_order_id=cid
            )
            if result.get('status') == 'duplicate':
                # Reconcile: look up original order to see if it filled
                existing = mgr.get_order_by_client_id(cid)
                if existing and existing.get('status') == 'filled':
                    exit_results.append({'exit': ex, 'result': existing, 'success': True})
                    print(f"  RECONCILED {ex['symbol']}: prior order filled")
                else:
                    exit_results.append({'exit': ex, 'result': result, 'success': False})
                    print(f"  SKIP {ex['symbol']}: duplicate, prior order status={existing.get('status') if existing else 'unknown'}")
            else:
                exit_results.append({'exit': ex, 'result': result, 'success': True})
                print(f"  SOLD {ex['symbol']} {ex['shares']} shares ({ex['reason']})")
        except Exception as e:
            exit_results.append({'exit': ex, 'result': str(e), 'success': False})
            print(f"  FAILED sell {ex['symbol']}: {e}")

    # Phase 2b: Re-evaluate account and execute entries (no lock)
    account = mgr.get_account_summary()
    portfolio_value = account['portfolio_value']
    print(f"\nPost-exit portfolio: ${portfolio_value:,.2f}")

    # Risk gate
    if not check_risk_gate(trades, portfolio_value):
        entry_plan = []

    # Margin check
    positions = mgr.get_positions()
    total_position_value = sum(p['market_value'] for p in positions)
    margin_room = portfolio_value * DEFAULTS.margin_ratio - total_position_value

    # Re-verify AMC candidates at entry time (gap/volume/price)
    # AMC candidates were screened without trade-date bars;
    # now that market is open we can check pre-open/open conditions.
    from src.data_fetcher import DataFetcher as DF
    df_for_verify = DF(use_fmp=True)

    verified_plan = []
    skipped_entries = []  # Track skipped candidates for pending cleanup
    for en in entry_plan:
        if en.get('timing') in ('amc', 'bmo'):  # both need live re-verification
            sym = en['symbol']
            # Verify gap/price/volume using today's actual bar
            hist = df_for_verify.get_historical_data(
                sym,
                (pd.Timestamp(today) - pd.Timedelta(days=30)).strftime('%Y-%m-%d'),
                today,
            )
            if hist is None or hist.empty:
                print(f"  SKIP {sym}: no price data available")
                skipped_entries.append(en)
                continue

            date_col = 'date'
            close_col = 'Close' if 'Close' in hist.columns else 'close'
            open_col = 'Open' if 'Open' in hist.columns else 'open'
            vol_col = 'Volume' if 'Volume' in hist.columns else 'volume'

            # Check if today's bar actually exists
            today_rows = hist[hist[date_col] == today]
            if today_rows.empty:
                print(f"  SKIP {sym}: today's bar not yet available")
                skipped_entries.append(en)
                continue

            today_open = float(today_rows.iloc[0][open_col])
            # prev_close = most recent close BEFORE today
            prev_rows = hist[hist[date_col] < today]
            prev_close = float(prev_rows.iloc[-1][close_col]) if not prev_rows.empty else en['prev_close']
            avg_volume = float(hist[vol_col].tail(20).mean())

            gap = (today_open - prev_close) / prev_close * 100 if prev_close > 0 else 0

            if gap < 0:
                print(f"  SKIP {sym}: negative gap ({gap:.1f}%)")
                skipped_entries.append(en)
                continue
            if gap > DEFAULTS.max_gap_percent:
                print(f"  SKIP {sym}: gap too large ({gap:.1f}%)")
                skipped_entries.append(en)
                continue
            if today_open < DEFAULTS.screener_price_min:
                print(f"  SKIP {sym}: price ${today_open:.2f} < ${DEFAULTS.screener_price_min:.0f}")
                skipped_entries.append(en)
                continue
            if avg_volume < DEFAULTS.min_volume_20d:
                print(f"  SKIP {sym}: volume {avg_volume:.0f} < {DEFAULTS.min_volume_20d}")
                skipped_entries.append(en)
                continue

            en['prev_close'] = prev_close
            en['entry_price_est'] = today_open
            en['gap_percent'] = gap
            print(f"  VERIFIED {sym}: gap={gap:.1f}%, open=${today_open:.2f}")

        verified_plan.append(en)

    entry_plan = verified_plan
    print(f"After AMC re-verification: {len(entry_plan)} entries")

    entry_results = []
    for en in entry_plan:
        if margin_room <= 0:
            print(f"  SKIP {en['symbol']}: margin limit reached")
            entry_results.append({'entry': en, 'result': 'margin_limit', 'success': False})
            continue

        shares = AlpacaOrderManager.calculate_position_size(
            portfolio_value, DEFAULTS.position_size,
            en['prev_close'], DEFAULTS.slippage,
        )
        if shares <= 0:
            print(f"  SKIP {en['symbol']}: 0 shares (price too high)")
            entry_results.append({'entry': en, 'result': '0_shares', 'success': False})
            continue

        estimated_value = shares * en['prev_close']
        if estimated_value > margin_room:
            shares = int(margin_room / en['prev_close'])
            if shares <= 0:
                continue

        cid = AlpacaOrderManager.make_client_order_id(
            en['symbol'], today, f"entry_{en['timing']}", 'buy'
        )
        try:
            result = mgr.submit_market_order(
                en['symbol'], shares, side='buy', client_order_id=cid
            )
            if result.get('status') == 'duplicate':
                existing = mgr.get_order_by_client_id(cid)
                if existing and existing.get('status') == 'filled':
                    entry_results.append({'entry': en, 'result': existing,
                                          'success': True, 'shares': shares})
                    margin_room -= estimated_value
                    print(f"  RECONCILED {en['symbol']}: prior order filled")
                else:
                    entry_results.append({'entry': en, 'result': result,
                                          'success': False, 'shares': shares})
                    print(f"  SKIP {en['symbol']}: duplicate, status={existing.get('status') if existing else 'unknown'}")
            else:
                entry_results.append({'entry': en, 'result': result,
                                      'success': True, 'shares': shares})
                margin_room -= estimated_value
                print(f"  BOUGHT {en['symbol']} {shares} shares "
                      f"(est ${en['prev_close']:.2f})")
        except Exception as e:
            entry_results.append({'entry': en, 'result': str(e), 'success': False})
            print(f"  FAILED buy {en['symbol']}: {e}")

    # Phase 3: Record (short lock)
    with lock:
        trades = load_json(TRADES_FILE)
        pending_exits = load_json(PENDING_EXITS_FILE)
        pending_entries = load_json(PENDING_ENTRIES_FILE)

        # Record successful exits
        for er in exit_results:
            if er['success']:
                ex = er['exit']
                result = er['result']
                for t in trades:
                    if t['symbol'] == ex['symbol'] and t['status'] == 'open':
                        fill_price = result.get('filled_avg_price') or ex.get('trigger_price', 0)
                        pnl = (fill_price - t['entry_price']) * ex['shares'] if fill_price else 0
                        t['legs'].append({
                            'date': today,
                            'action': f"exit_{ex['reason']}",
                            'shares': ex['shares'],
                            'price': fill_price,
                            'pnl': round(pnl, 2),
                            'reason': ex['reason'],
                            'order_id': result.get('id', ''),
                            'client_order_id': result.get('client_order_id', ''),
                        })
                        t['remaining_shares'] -= ex['shares']
                        if t['remaining_shares'] <= 0:
                            t['status'] = 'closed'
                        break
                # Remove from pending
                pending_exits = [
                    pe for pe in pending_exits if pe['symbol'] != ex['symbol']
                ]

        # Record successful entries
        for er in entry_results:
            if er['success']:
                en = er['entry']
                result = er['result']
                shares = er['shares']
                fill_price = result.get('filled_avg_price') or en['prev_close']
                stop_price = fill_price * (1 - DEFAULTS.stop_loss / 100) if fill_price else 0

                new_trade = {
                    'symbol': en['symbol'],
                    'entry_date': today,
                    'entry_price': fill_price,
                    'initial_shares': shares,
                    'remaining_shares': shares,
                    'stop_loss_price': round(stop_price, 2),
                    'screener_score': en.get('score', 0),
                    'timing': en.get('timing', ''),
                    'status': 'open',
                    'legs': [{
                        'date': today,
                        'action': 'entry',
                        'shares': shares,
                        'price': fill_price,
                        'order_id': result.get('id', ''),
                        'client_order_id': result.get('client_order_id', ''),
                    }],
                }
                trades.append(new_trade)

                # Remove from pending
                pending_entries = [
                    pe for pe in pending_entries
                    if not (pe['symbol'] == en['symbol'] and pe['timing'] == en['timing'])
                ]

        # Also remove skipped entries (failed re-verification) from pending
        # to prevent stale candidates from re-executing on the next day
        skip_keys = {
            (se['symbol'], se.get('timing'))
            for se in skipped_entries
        }
        if skip_keys:
            pending_entries = [
                pe for pe in pending_entries
                if (pe['symbol'], pe.get('timing')) not in skip_keys
            ]
            print(f"  Removed {len(skip_keys)} skipped entries from pending")

        save_json_atomic(TRADES_FILE, trades)
        save_json_atomic(PENDING_EXITS_FILE, pending_exits)
        save_json_atomic(PENDING_ENTRIES_FILE, pending_entries)

    # Summary
    ok_exits = sum(1 for r in exit_results if r['success'])
    ok_entries = sum(1 for r in entry_results if r['success'])
    print(f"\n=== Summary ===")
    print(f"Exits: {ok_exits}/{len(exit_results)} successful")
    print(f"Entries: {ok_entries}/{len(entry_results)} successful")


def main():
    parser = argparse.ArgumentParser(description='Paper trading auto entry')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--screen-bmo', action='store_true',
                       help='Screen BMO candidates and save to pending')
    group.add_argument('--screen-amc', action='store_true',
                       help='Screen AMC candidates and save to pending')
    group.add_argument('--execute', action='store_true',
                       help='Execute pending exits and entries')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without placing orders')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

    if args.screen_bmo:
        screen_and_save('bmo', dry_run=args.dry_run)
    elif args.screen_amc:
        screen_and_save('amc', dry_run=args.dry_run)
    elif args.execute:
        execute_pending(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
