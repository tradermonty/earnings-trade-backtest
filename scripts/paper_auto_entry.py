#!/usr/bin/env python3
"""
Paper Trading Auto Entry
全自動エントリー（cron で起動）

Modes:
  --screen-bmo    9:00 AM: Screen BMO candidates → save to pending_entries.json
  --screen-amc   16:00:    Screen AMC candidates → save to pending_entries.json
  --execute       9:30 AM: Execute pending exits (sell) then entries (buy)
  --dry-run       Use dry-run state and deterministic fills; no broker orders

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
from datetime import datetime, timedelta
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
from src.filter_utils import (
    compute_avg_volume_20d,
    compute_pre_earnings_change,
    get_prior_bars,
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

def screen_and_save(
    timing: str,
    dry_run: bool = False,
    *,
    state_dir: Optional[str] = None,
):
    """Run screener with --market_timing and save pending entries.

    In dry-run mode candidates are still persisted, but under
    ``data/dryrun`` (or the injected ``state_dir``) so the cron
    screen→execute→exit handoff can be replayed without touching live state.
    """
    today = get_today_str()
    print(f"=== Screen {timing.upper()} candidates ({today}) ===")
    paths = _resolve_state_paths(state_dir, dry_run)

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
        trade_date = c.get('trade_date') or c.get('date') or today
        eps_surprise = float(c.get('eps_surprise_percent') or c.get('eps_surprise') or 0)
        entry = {
            'symbol': c['symbol'],
            'timing': timing,
            'date': trade_date,
            'trade_date': trade_date,
            'prev_close': float(c.get('prev_close', 0)),
            'entry_price_est': float(c.get('entry_price') or c.get('entry_price_est') or 0),
            'score': float(c.get('score') or eps_surprise),
            'eps_surprise': eps_surprise,
            'eps_surprise_percent': eps_surprise,
            'gap_percent': float(c.get('gap_percent', 0)),
        }
        entries.append(entry)
        print(f"  Candidate: {entry['symbol']} score={entry['score']:.1f} "
              f"gap={entry['gap_percent']:.1f}%")

    lock = FileLock(paths.lock, timeout=30)
    with lock:
        existing = load_json(paths.pending_entries)
        # Dedupe by (symbol, trade_date, timing) to handle re-runs
        existing_keys = {
            (e['symbol'], e.get('trade_date') or e.get('date'), e.get('timing'))
            for e in existing
        }
        new_entries = [
            e for e in entries
            if (e['symbol'], e.get('trade_date') or e.get('date'), e.get('timing')) not in existing_keys
        ]
        skipped = len(entries) - len(new_entries)
        existing.extend(new_entries)
        save_json_atomic(paths.pending_entries, existing)

    if skipped > 0:
        print(f"\n  Deduplicated: {skipped} entries already pending")
    state_label = "dry-run" if dry_run else "live"
    print(f"Saved {len(new_entries)} new entries to {state_label} pending_entries.json")


# --- Execute Mode ---

def execute_pending(
    dry_run: bool = False,
    *,
    alpaca_manager: Any = None,
    data_fetcher: Any = None,
    today_str: Optional[str] = None,
    state_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute pending exits first, then entries, and persist state atomically.

    The public shape is intentionally injectable so tests, dry-run cron, and
    live paper trading all exercise the same path. ``dry_run=True`` uses
    ``DryRunAccount`` and writes to ``data/dryrun`` unless ``state_dir`` is
    supplied. Existing tests that monkeypatch module-level path constants are
    still supported when ``state_dir`` is omitted in live mode.
    """
    today = today_str or get_today_str()
    print(f"=== Execute Pending Orders ({today}) ===")

    if state_dir is None and not dry_run:
        paths = StatePaths(DATA_DIR, TRADES_FILE, PENDING_ENTRIES_FILE,
                           PENDING_EXITS_FILE, LOCK_FILE)
    else:
        paths = _resolve_state_paths(state_dir, dry_run)

    from src.data_fetcher import DataFetcher as DF
    df_for_verify = data_fetcher or DF(use_fmp=True)
    if alpaca_manager is not None:
        mgr = alpaca_manager
    elif dry_run:
        mgr = DryRunAccount(paths, data_fetcher=df_for_verify, today_str=today)
    else:
        mgr = AlpacaOrderManager(account_type='paper')

    lock = FileLock(paths.lock, timeout=30)

    def _entry_key(en: Dict[str, Any]) -> tuple:
        return (en.get('symbol'), en.get('trade_date') or en.get('date'), en.get('timing'))

    def _entry_date(en: Dict[str, Any]) -> Optional[str]:
        return en.get('trade_date') or en.get('date')

    def _sort_surprise(en: Dict[str, Any]) -> float:
        return float(en.get('eps_surprise_percent',
                            en.get('eps_surprise', en.get('score', 0))) or 0)

    def _cleanup_eligible(reason: str) -> bool:
        prefixes = (
            'no_preopen', 'no_history', 'insufficient_history',
            'gap_out_of_range', 'price_below_min', 'volume_below_min',
            'pre_change_below_min', 'top_n_cap', 'already_position',
            'already_pending_exit', 'margin_limit', 'zero_shares',
            'margin_caps_to_zero',
        )
        return any(reason == p or reason.startswith(p) for p in prefixes)

    def _pending_entry_matches(p: Dict[str, Any], en: Dict[str, Any]) -> bool:
        return _entry_key(p) == _entry_key(en)

    def _pending_exit_matches(p: Dict[str, Any], ex: Dict[str, Any]) -> bool:
        return (
            p.get('symbol') == ex.get('symbol')
            and p.get('reason') == ex.get('reason')
            and int(p.get('shares', 0) or 0) == int(ex.get('shares', 0) or 0)
        )

    # ===== Phase 1: Plan =====
    with lock:
        pending_exits = load_json(paths.pending_exits)
        pending_entries_all = load_json(paths.pending_entries)
        trades = load_json(paths.trades)

    pending_entries = [
        e for e in pending_entries_all
        if e.get('submission_status') != 'pending'
        and (e.get('trade_date') is None or e.get('trade_date') == today)
    ]

    print(f"Exit plan: {len(pending_exits)} sells")

    # ===== Phase 2: Place exits (no lock) =====
    exit_results: List[Dict[str, Any]] = []
    for ex in pending_exits:
        shares = int(ex.get('shares', 0) or 0)
        if shares <= 0:
            exit_results.append({
                'exit': ex, 'result': {}, 'filled_shares': 0,
                'outcome': 'rejected', 'skip_reason': 'zero_shares',
            })
            continue
        cid = AlpacaOrderManager.make_client_order_id(
            ex['symbol'], today, f"exit_{ex.get('reason', 'unknown')}", 'sell'
        )
        ref_price = float(ex.get('trigger_price') or ex.get('entry_price') or 0)
        result, filled_shares, outcome, skip_reason = _submit_with_reconciliation(
            mgr, ex['symbol'], shares, 'sell', cid, reference_price=ref_price or 0.01,
        )
        exit_results.append({
            'exit': ex,
            'cid': cid,
            'submitted_shares': shares,
            'submitted_reference_price': ref_price,
            'result': result,
            'filled_shares': filled_shares,
            'outcome': outcome,
            'skip_reason': skip_reason,
        })

    # ===== Phase 3: Re-evaluate account/positions =====
    account = mgr.get_account_summary()
    portfolio_value = float(account['portfolio_value'])
    positions = mgr.get_positions()
    current_positions = {p['symbol'] for p in positions}
    total_position_value = sum(float(p.get('market_value', 0) or 0) for p in positions)
    print(f"\nPost-exit portfolio: ${portfolio_value:,.2f}")

    # ===== Phase 4: Filter + verify + top-N entries =====
    forbidden_today = (
        {e.get('symbol') for e in pending_exits}
        | {er['exit'].get('symbol') for er in exit_results}
    )
    entries_skipped: List[Dict[str, Any]] = []
    survivors: List[Dict[str, Any]] = []

    for en in pending_entries:
        sym = en.get('symbol')
        if not sym:
            continue
        if sym in current_positions:
            entries_skipped.append(_skip_entry(en, 'already_position'))
            continue
        if sym in forbidden_today:
            entries_skipped.append(_skip_entry(en, 'already_pending_exit'))
            continue

        # Legacy tests use timing=None with precomputed prices; keep that path
        # trusted while live pending entries use timing bmo/amc and are verified.
        if en.get('timing') in ('amc', 'bmo'):
            pre_open = df_for_verify.get_preopen_price(sym, today)
            if pre_open is None:
                entries_skipped.append(_skip_entry(en, 'no_preopen'))
                continue
            hist = df_for_verify.get_historical_data(
                sym,
                (pd.Timestamp(today) - pd.Timedelta(days=60)).strftime('%Y-%m-%d'),
                today,
            )
            prior = get_prior_bars(hist, today)
            if prior.empty:
                entries_skipped.append(_skip_entry(en, 'no_history'))
                continue
            close_col = 'Close' if 'Close' in prior.columns else 'close'
            prev_close = float(prior.iloc[-1][close_col])
            gap = (float(pre_open) - prev_close) / prev_close * 100 if prev_close > 0 else 0
            avg_volume = compute_avg_volume_20d(hist, today)
            pre_change = compute_pre_earnings_change(hist, today)

            if gap < 0 or gap > DEFAULTS.max_gap_percent:
                entries_skipped.append(_skip_entry(en, f'gap_out_of_range_{gap:.2f}'))
                continue
            if float(pre_open) < DEFAULTS.screener_price_min:
                entries_skipped.append(_skip_entry(en, 'price_below_min'))
                continue
            if avg_volume is None:
                entries_skipped.append(_skip_entry(en, 'insufficient_history'))
                continue
            if avg_volume < DEFAULTS.min_volume_20d:
                entries_skipped.append(_skip_entry(en, 'volume_below_min'))
                continue
            if pre_change is None:
                entries_skipped.append(_skip_entry(en, 'insufficient_history'))
                continue
            if pre_change < DEFAULTS.pre_earnings_change:
                entries_skipped.append(_skip_entry(en, 'pre_change_below_min'))
                continue

            en['_entry_price'] = float(pre_open)
            en['_prev_close'] = prev_close
            en['_gap'] = gap
            print(f"  VERIFIED {sym}: gap={gap:.1f}%, pre_open=${float(pre_open):.2f}")
        else:
            price = float(en.get('entry_price_est') or en.get('prev_close') or 0)
            if price <= 0:
                entries_skipped.append(_skip_entry(en, 'no_preopen'))
                continue
            en['_entry_price'] = price

        survivors.append(en)

    survivors.sort(key=_sort_surprise, reverse=True)
    dropped = survivors[DEFAULTS.top_n_per_day:]
    survivors = survivors[:DEFAULTS.top_n_per_day]
    for en in dropped:
        entries_skipped.append(_skip_entry(en, 'top_n_cap'))

    if not check_risk_gate(trades, portfolio_value, today):
        for en in survivors:
            entries_skipped.append(_skip_entry(en, 'risk_gate'))
        survivors = []

    print(f"Entry plan: {len(survivors)} buys")

    # ===== Phase 5: Place entries (no lock) =====
    margin_room = portfolio_value * DEFAULTS.margin_ratio - total_position_value
    placed_entries: List[Dict[str, Any]] = []
    for en in survivors:
        entry_price = float(en['_entry_price'])
        if margin_room <= 0:
            entries_skipped.append(_skip_entry(en, 'margin_limit'))
            continue
        shares = AlpacaOrderManager.calculate_position_size(
            portfolio_value, DEFAULTS.position_size, entry_price, DEFAULTS.slippage,
        )
        if shares <= 0:
            entries_skipped.append(_skip_entry(en, 'zero_shares'))
            continue
        estimated_value = shares * entry_price
        if estimated_value > margin_room:
            shares = int(margin_room / entry_price)
            if shares <= 0:
                entries_skipped.append(_skip_entry(en, 'margin_caps_to_zero'))
                continue
        cid = AlpacaOrderManager.make_client_order_id(
            en['symbol'], today, f"entry_{en.get('timing')}", 'buy'
        )
        result, filled_shares, outcome, skip_reason = _submit_with_reconciliation(
            mgr, en['symbol'], shares, 'buy', cid, reference_price=entry_price,
        )
        if outcome not in ('filled_full', 'filled_partial'):
            en['_submission'] = {
                'cid': cid,
                'submitted_shares': shares,
                'submitted_reference_price': entry_price,
                'outcome': outcome,
            }
            entries_skipped.append(_skip_entry(en, skip_reason or outcome))
            continue
        fill_price = float(result['filled_avg_price'])
        actual_shares = int(filled_shares)
        placed_entries.append({
            'entry': en,
            'symbol': en['symbol'],
            'shares': actual_shares,
            'entry_price_est': entry_price,
            'fill_price': fill_price,
            'result': result,
        })
        margin_room -= actual_shares * fill_price
        print(f"  BOUGHT {en['symbol']} {actual_shares} shares (fill ${fill_price:.2f})")

    # ===== Phase 6: State update (short lock) =====
    exits_placed: List[Dict[str, Any]] = []
    exits_skipped: List[Dict[str, Any]] = []
    with lock:
        trades_now = load_json(paths.trades)
        pending_exits_now = load_json(paths.pending_exits)
        pending_entries_now = load_json(paths.pending_entries)

        for er in exit_results:
            ex = er['exit']
            if er['outcome'] not in ('filled_full', 'filled_partial'):
                exits_skipped.append(_skip_exit(ex, er.get('skip_reason') or er['outcome']))
                if er['outcome'] == 'pending_unfilled':
                    for p in pending_exits_now:
                        if _pending_exit_matches(p, ex):
                            p['submitted_client_order_id'] = er['cid']
                            p['submitted_shares'] = er['submitted_shares']
                            p['submitted_reference_price'] = er['submitted_reference_price']
                            p['submitted_at'] = datetime.utcnow().isoformat() + 'Z'
                            p['submission_status'] = 'pending'
                continue

            fill_price = float(er['result']['filled_avg_price'])
            filled_shares = int(er['filled_shares'])
            matched = False
            pnl = 0.0
            for t in trades_now:
                if t.get('symbol') == ex.get('symbol') and t.get('status') == 'open':
                    pnl = (fill_price - float(t.get('entry_price', 0))) * filled_shares
                    t.setdefault('legs', []).append({
                        'date': today,
                        'action': f"exit_{ex.get('reason', 'unknown')}",
                        'shares': filled_shares,
                        'price': fill_price,
                        'pnl': round(pnl, 2),
                        'reason': ex.get('reason', ''),
                        'order_id': er['result'].get('id', ''),
                        'client_order_id': er['result'].get('client_order_id', ''),
                    })
                    t['remaining_shares'] = int(t.get('remaining_shares', 0)) - filled_shares
                    if t['remaining_shares'] <= 0:
                        t['status'] = 'closed'
                    matched = True
                    break
            if not matched:
                exits_skipped.append(_skip_exit(ex, 'no_matching_open_trade'))
                continue
            pending_exits_now = [
                p for p in pending_exits_now if not _pending_exit_matches(p, ex)
            ]
            exits_placed.append({
                'exit': ex,
                'symbol': ex.get('symbol'),
                'shares': filled_shares,
                'fill_price': fill_price,
                'pnl': round(pnl, 2),
                'result': er['result'],
            })

        for pe in placed_entries:
            en = pe['entry']
            fill_price = pe['fill_price']
            shares = int(pe['shares'])
            stop_price = fill_price * (1 - DEFAULTS.stop_loss / 100)
            trades_now.append({
                'symbol': en['symbol'],
                'entry_date': today,
                'entry_price': fill_price,
                'initial_shares': shares,
                'remaining_shares': shares,
                'stop_loss_price': round(stop_price, 2),
                'screener_score': en.get('score', _sort_surprise(en)),
                'eps_surprise_percent': en.get('eps_surprise_percent', en.get('eps_surprise')),
                'gap_percent': en.get('_gap', en.get('gap_percent')),
                'timing': en.get('timing', ''),
                'status': 'open',
                'legs': [{
                    'date': today,
                    'action': 'entry',
                    'shares': shares,
                    'price': fill_price,
                    'order_id': pe['result'].get('id', ''),
                    'client_order_id': pe['result'].get('client_order_id', ''),
                }],
            })
            pending_entries_now = [
                p for p in pending_entries_now if not _pending_entry_matches(p, en)
            ]

        for s in entries_skipped:
            if s.get('reason') != 'not_filled':
                continue
            en = s['entry']
            sub = en.get('_submission', {})
            for p in pending_entries_now:
                if _pending_entry_matches(p, en):
                    p['submitted_client_order_id'] = sub.get('cid')
                    p['submitted_shares'] = sub.get('submitted_shares')
                    p['submitted_reference_price'] = sub.get('submitted_reference_price')
                    p['submitted_at'] = datetime.utcnow().isoformat() + 'Z'
                    p['submission_status'] = 'pending'

        skip_keys = {
            (s.get('symbol'), s.get('trade_date') or _entry_date(s.get('entry', {})), s.get('timing'))
            for s in entries_skipped
            if _cleanup_eligible(str(s.get('reason', '')))
        }
        pending_entries_now = [
            p for p in pending_entries_now
            if _entry_key(p) not in skip_keys
        ]

        cutoff = (datetime.strptime(today, '%Y-%m-%d') - timedelta(days=7)).strftime('%Y-%m-%d')
        pending_entries_now = [
            p for p in pending_entries_now
            if (p.get('trade_date') or p.get('date') or today) >= cutoff
            or p.get('submission_status') == 'pending'
        ]
        pending_exits_now = [
            p for p in pending_exits_now
            if p.get('detected_at', today) >= cutoff
            or p.get('submission_status') == 'pending'
        ]

        save_json_atomic(paths.trades, trades_now)
        save_json_atomic(paths.pending_exits, pending_exits_now)
        save_json_atomic(paths.pending_entries, pending_entries_now)

    print(f"\n=== Summary ===")
    print(f"Exits: {len(exits_placed)}/{len(exit_results)} successful")
    print(f"Entries: {len(placed_entries)}/{len(survivors)} successful")
    return {
        'entries_planned': survivors,
        'entries_placed': placed_entries,
        'entries_skipped': entries_skipped,
        'exits_planned': pending_exits,
        'exits_placed': exits_placed,
        'exits_skipped': exits_skipped,
    }


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
                        help='Use dry-run state with deterministic fills; no broker orders')
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
