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
from typing import Dict, List, Any

import pandas as pd

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from filelock import FileLock
from src.alpaca_order_manager import AlpacaOrderManager

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(project_root, 'data')
TRADES_FILE = os.path.join(DATA_DIR, 'paper_trades.json')
PENDING_ENTRIES_FILE = os.path.join(DATA_DIR, 'pending_entries.json')
PENDING_EXITS_FILE = os.path.join(DATA_DIR, 'pending_exits.json')
LOCK_FILE = os.path.join(DATA_DIR, '.paper_state.lock')

# Strategy parameters
POSITION_SIZE_PCT = 15.0
SLIPPAGE_PCT = 0.3
STOP_LOSS_PCT = 10.0
MARGIN_RATIO = 1.5
RISK_LIMIT_PCT = 6.0


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


def check_risk_gate(trades: List[Dict], portfolio_value: float) -> bool:
    """Check if new entries are allowed based on recent P&L.

    Returns True if new entries are allowed.
    Matches RiskManager.check_risk_management() logic:
    block if realized losses in last 30 days exceed risk_limit_pct.
    """
    now = datetime.now()
    total_pnl = 0.0

    for trade in trades:
        for leg in trade.get('legs', []):
            if leg.get('action', '').startswith('exit'):
                leg_date = datetime.strptime(leg['date'], '%Y-%m-%d')
                if (now - leg_date).days <= 30:
                    total_pnl += leg.get('pnl', 0)

    if portfolio_value > 0:
        pnl_ratio = (total_pnl / portfolio_value) * 100
        if pnl_ratio < -RISK_LIMIT_PCT:
            print(f"RISK GATE: Recent 30-day P&L {pnl_ratio:.1f}% exceeds "
                  f"-{RISK_LIMIT_PCT}% limit. Blocking new entries.")
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
        existing.extend(entries)
        save_json_atomic(PENDING_ENTRIES_FILE, existing)

    print(f"\nSaved {len(entries)} entries to pending_entries.json")


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
            is_dup = result.get('status') == 'duplicate'
            exit_results.append({'exit': ex, 'result': result, 'success': not is_dup})
            if is_dup:
                print(f"  SKIP {ex['symbol']}: duplicate order (already submitted)")
            else:
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
    margin_room = portfolio_value * MARGIN_RATIO - total_position_value

    # Re-verify AMC candidates at entry time (gap/volume/price)
    # AMC candidates were screened without trade-date bars;
    # now that market is open we can check pre-open/open conditions.
    from src.data_fetcher import DataFetcher as DF
    df_for_verify = DF(use_fmp=True)

    verified_plan = []
    for en in entry_plan:
        if en.get('timing') == 'amc':
            sym = en['symbol']
            # Fetch today's data to check open price and gap
            hist = df_for_verify.get_historical_data(
                sym,
                (pd.Timestamp(today) - pd.Timedelta(days=5)).strftime('%Y-%m-%d'),
                today,
            )
            if hist is not None and not hist.empty:
                close_col = 'Close' if 'Close' in hist.columns else 'close'
                open_col = 'Open' if 'Open' in hist.columns else 'open'
                vol_col = 'Volume' if 'Volume' in hist.columns else 'volume'

                today_open = float(hist.iloc[-1][open_col]) if today in hist['date'].values or len(hist) > 0 else 0
                prev_close = float(hist.iloc[-2][close_col]) if len(hist) >= 2 else en['prev_close']
                avg_volume = float(hist[vol_col].tail(20).mean()) if len(hist) >= 2 else 0

                gap = (today_open - prev_close) / prev_close * 100 if prev_close > 0 else 0

                # Apply same filters as DataFilter._check_final_conditions
                if gap < 0:
                    print(f"  SKIP {sym}: negative gap ({gap:.1f}%)")
                    continue
                if gap > 10.0:
                    print(f"  SKIP {sym}: gap too large ({gap:.1f}%)")
                    continue
                if today_open < 30.0:
                    print(f"  SKIP {sym}: price ${today_open:.2f} < $30")
                    continue
                if avg_volume < 200000:
                    print(f"  SKIP {sym}: volume {avg_volume:.0f} < 200K")
                    continue

                # Update with actual prices
                en['prev_close'] = prev_close
                en['entry_price_est'] = today_open
                en['gap_percent'] = gap
                print(f"  VERIFIED {sym}: gap={gap:.1f}%, open=${today_open:.2f}")
            else:
                print(f"  SKIP {sym}: no price data available")
                continue
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
            portfolio_value, POSITION_SIZE_PCT,
            en['prev_close'], SLIPPAGE_PCT,
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
            is_dup = result.get('status') == 'duplicate'
            entry_results.append({'entry': en, 'result': result,
                                  'success': not is_dup, 'shares': shares})
            if is_dup:
                print(f"  SKIP {en['symbol']}: duplicate order (already submitted)")
            else:
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
                stop_price = fill_price * (1 - STOP_LOSS_PCT / 100) if fill_price else 0

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

        save_json_atomic(TRADES_FILE, trades)
        save_json_atomic(PENDING_EXITS_FILE, pending_exits)
        save_json_atomic(PENDING_ENTRIES_FILE, pending_entries)

    # Summary
    ok_exits = sum(1 for r in exit_results if r['success'])
    ok_entries = sum(1 for r in entry_results if r['success'])
    print(f"\n=== Summary ===")
    print(f"Exits: {ok_exits}/{len(pending_exits)} successful")
    print(f"Entries: {ok_entries}/{len(entry_plan)} successful")


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
