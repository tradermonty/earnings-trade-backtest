#!/usr/bin/env python3
"""Print the backtest's `_select_top_stocks` output for a single trade_date.

`main.py` rejects ``start_date >= end_date`` (`main.py:122`), so a single-day
backtest invocation isn't supported. This helper runs the same DataFilter
pipeline over a small surrounding window and prints just the candidates
selected for the requested ``--trade-date``. Intended use: side-by-side
comparison with the live screener output for the same trade_date.

Usage:
    python scripts/show_filter_output.py --trade-date 2026-05-11

The output includes symbol, surprise %, gap %, and pre_change so a user can
verify that the live screener (`reports/screener/daily_candidates_<date>.csv`)
ranks the same symbols in the same order.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from src.config import DEFAULTS, BacktestConfig
from src.data_fetcher import DataFetcher
from src.data_filter import DataFilter
from src.universe_builder import build_target_universe


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Show backtest filter top-N output for a single trade date.')
    p.add_argument('--trade-date', required=True, help='YYYY-MM-DD')
    p.add_argument('--window-days', type=int, default=3,
                   help='Days before/after trade_date to fetch earnings (default: 3)')
    return p.parse_args()


def main() -> int:
    args = parse_args()
    trade_date = args.trade_date
    td = datetime.strptime(trade_date, '%Y-%m-%d')
    start = (td - timedelta(days=args.window_days)).strftime('%Y-%m-%d')
    end = (td + timedelta(days=args.window_days)).strftime('%Y-%m-%d')

    df = DataFetcher(use_fmp=True)
    target_symbols, _src = build_target_universe(
        df,
        screener_price_min=DEFAULTS.screener_price_min,
        min_market_cap=DEFAULTS.min_market_cap,
    )

    cfg = BacktestConfig(start_date=start, end_date=end)
    fil = DataFilter(
        data_fetcher=df,
        target_symbols=target_symbols,
        min_surprise_percent=cfg.min_surprise_percent,
        pre_earnings_change=cfg.pre_earnings_change,
        max_holding_days=cfg.max_holding_days,
        max_gap_percent=cfg.max_gap_percent,
        screener_price_min=cfg.screener_price_min,
        min_market_cap=cfg.min_market_cap,
    )
    earnings = df.get_earnings_data(
        start_date=start, end_date=end,
        target_symbols=list(target_symbols) if target_symbols else None,
    )
    selected = fil.filter_earnings_data(earnings)
    on_date = [c for c in selected if c.get('trade_date') == trade_date]
    on_date.sort(key=lambda c: float(c.get('percent', 0)), reverse=True)

    print(f'\n=== Backtest top-{DEFAULTS.top_n_per_day} for trade_date {trade_date} ===')
    if not on_date:
        print('(no candidates)')
        return 0
    for i, c in enumerate(on_date, 1):
        print(
            f"  {i}. {c['code']:<6s}  surprise={float(c.get('percent', 0)):>6.2f}%  "
            f"gap={float(c.get('gap', 0)):>5.2f}%  "
            f"pre_change={float(c.get('pre_change', 0)):>5.2f}%  "
            f"price=${float(c.get('entry_price', 0)):.2f}"
        )
    print(
        f"\nCompare to live screener output:\n"
        f"  reports/screener/daily_candidates_{trade_date}.csv"
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
