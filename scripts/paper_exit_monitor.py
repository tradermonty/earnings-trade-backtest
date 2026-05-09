#!/usr/bin/env python3
"""
Paper Trading Exit Monitor
日次 Exit 条件チェック（cron 16:05 ET で実行）

各オープンポジションに対して Exit 条件を判定し、
翌朝 9:30 のクローズ対象を pending_exits.json に保存する。

Exit 優先順位（trade_executor.py 準拠）:
  1. max_holding_days (90日)
  2. stop_loss (Low <= entry * (1 - 10%))
  3. trailing_stop (Close < MA21)
  4. partial_profit (+6% on day 1, floor(shares/2), skip if 0)

Usage:
  python scripts/paper_exit_monitor.py
  python scripts/paper_exit_monitor.py --dry-run
"""

import argparse
import json
import logging
import math
import os
import sys
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

import pandas as pd

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from filelock import FileLock
from src.data_fetcher import DataFetcher
from src.config import DEFAULTS

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(project_root, 'data')
TRADES_FILE = os.path.join(DATA_DIR, 'paper_trades.json')
PENDING_EXITS_FILE = os.path.join(DATA_DIR, 'pending_exits.json')
LOCK_FILE = os.path.join(DATA_DIR, '.paper_state.lock')

# Strategy parameters sourced from DEFAULTS (src/config.py); use DEFAULTS.* directly.


def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def save_json_atomic(path, data):
    """Atomic write: temp file → rename."""
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
    """Get today's date in NY timezone."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d')
    except ImportError:
        return datetime.now().strftime('%Y-%m-%d')


def check_exit_conditions(
    trade: Dict[str, Any],
    data_fetcher: DataFetcher,
    today: str,
) -> Optional[Dict[str, Any]]:
    """Check exit conditions for a single open position.

    Returns a pending exit action dict, or None if no exit triggered.
    Only one exit action per position (highest priority wins).
    """
    symbol = trade['symbol']
    entry_date = trade['entry_date']
    entry_price = trade['entry_price']
    remaining_shares = trade['remaining_shares']
    stop_loss_price = trade.get('stop_loss_price', entry_price * (1 - DEFAULTS.stop_loss / 100))

    # Fetch historical data
    start = (datetime.strptime(entry_date, '%Y-%m-%d') - timedelta(days=60)).strftime('%Y-%m-%d')
    stock_data = data_fetcher.get_historical_data(symbol, start, today)
    if stock_data is None or stock_data.empty:
        logger.warning("No price data for %s, skipping exit check", symbol)
        return None

    # Normalize columns
    if 'close' in stock_data.columns:
        stock_data = stock_data.rename(columns={
            'open': 'Open', 'high': 'High', 'low': 'Low',
            'close': 'Close', 'volume': 'Volume',
        })
    stock_data = stock_data.set_index('date')

    # Today's data
    try:
        today_data = stock_data.loc[today]
    except KeyError:
        logger.warning("No data for %s on %s", symbol, today)
        return None

    today_low = today_data['Low']
    today_close = today_data['Close']
    days_held = (datetime.strptime(today, '%Y-%m-%d') - datetime.strptime(entry_date, '%Y-%m-%d')).days

    # --- Priority 1: Max holding days ---
    if days_held >= DEFAULTS.max_holding_days:
        return {
            'symbol': symbol,
            'shares': remaining_shares,
            'reason': 'max_holding_days',
            'trigger_date': today,
            'trigger_price': today_close,
        }

    # --- Priority 2: Stop loss ---
    # Intraday stop: checked on entry day and beyond (Low <= stop)
    if today_low <= stop_loss_price:
        return {
            'symbol': symbol,
            'shares': remaining_shares,
            'reason': 'stop_loss',
            'trigger_date': today,
            'trigger_price': stop_loss_price,
        }

    # --- Priority 3: Trailing stop (Close < MA21) ---
    # Only from day 2 onward (trade_executor checks entry_idx + 1)
    if days_held > 0:
        ma_col = f'MA{DEFAULTS.trail_stop_ma}'
        if ma_col not in stock_data.columns:
            stock_data[ma_col] = stock_data['Close'].rolling(DEFAULTS.trail_stop_ma).mean()
        ma_value = stock_data.loc[today].get(ma_col) if today in stock_data.index else None
        if ma_value is not None and pd.notna(ma_value) and today_close < ma_value:
            return {
                'symbol': symbol,
                'shares': remaining_shares,
                'reason': 'trailing_stop',
                'trigger_date': today,
                'trigger_price': ma_value,
            }

    # --- Priority 4: Partial profit (day 1 only, +6%) ---
    if days_held == 0:
        profit_pct = (today_close - entry_price) / entry_price * 100
        if profit_pct >= DEFAULTS.partial_profit_threshold:
            half = math.floor(remaining_shares / 2)
            if half > 0:
                return {
                    'symbol': symbol,
                    'shares': half,
                    'reason': 'partial_profit',
                    'trigger_date': today,
                    'trigger_price': today_close,
                }

    return None


def run_exit_monitor(dry_run: bool = False):
    """Main exit monitor logic."""
    today = get_today_str()
    print(f"=== Paper Exit Monitor ({today}) ===")

    data_fetcher = DataFetcher(use_fmp=True)
    lock = FileLock(LOCK_FILE, timeout=30)

    with lock:
        trades = load_json(TRADES_FILE)
        existing_exits = load_json(PENDING_EXITS_FILE)

    open_trades = [t for t in trades if t.get('status') == 'open']
    print(f"Open positions: {len(open_trades)}")

    if not open_trades:
        print("No open positions. Nothing to check.")
        return

    # Already pending symbols (don't double-queue)
    pending_symbols = {e['symbol'] for e in existing_exits}

    new_exits = []
    for trade in open_trades:
        if trade['symbol'] in pending_symbols:
            print(f"  {trade['symbol']}: already in pending_exits, skipping")
            continue

        exit_action = check_exit_conditions(trade, data_fetcher, today)
        if exit_action:
            new_exits.append(exit_action)
            print(f"  {trade['symbol']}: EXIT → {exit_action['reason']} "
                  f"({exit_action['shares']} shares @ ${exit_action['trigger_price']:.2f})")
        else:
            print(f"  {trade['symbol']}: HOLD")

    if not new_exits:
        print("\nNo exits triggered.")
        return

    print(f"\nTotal exits to queue: {len(new_exits)}")

    if dry_run:
        print("(dry-run mode — not saving to pending_exits.json)")
        return

    # Save to pending_exits.json (re-read under lock to avoid race)
    with lock:
        existing_exits = load_json(PENDING_EXITS_FILE)
        existing_symbols = {e['symbol'] for e in existing_exits}
        deduped = [e for e in new_exits if e['symbol'] not in existing_symbols]
        if len(deduped) < len(new_exits):
            skipped = len(new_exits) - len(deduped)
            print(f"  Deduplicated: {skipped} exits already pending")
        existing_exits.extend(deduped)
        save_json_atomic(PENDING_EXITS_FILE, existing_exits)

    print(f"Saved {len(new_exits)} exits to pending_exits.json")


def main():
    parser = argparse.ArgumentParser(description='Paper trading exit monitor')
    parser.add_argument('--dry-run', action='store_true',
                        help='Check conditions without saving pending exits')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    run_exit_monitor(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
