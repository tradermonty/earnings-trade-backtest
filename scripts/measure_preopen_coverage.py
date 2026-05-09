#!/usr/bin/env python3
"""Phase 2 measurement: pre_open_price coverage on stage-2 / top-N / final-trade candidates.

Decides whether the daily-Open fallback in `src/data_filter.py:319-326` can be
removed without materially shrinking the candidate universe (>5% of candidates
losing pre_open data). Decision rule (from plan rev 12):

  - If stage-2 None% AND top-N None% are ≤5% → remove fallback; both backtest
    and live skip when pre_open is None.
  - If either is >5% → retain fallback; document drift in `docs/parity_notes.md`.

Usage:
    python scripts/measure_preopen_coverage.py --start_date 2025-01-01 --end_date 2025-12-31

Implementation notes:
- (a) **stage-2 candidates** = candidates that passed `_first_stage_filter` AND
  the gap/price/volume/pre_change conditions in `_second_stage_filter`, but
  BEFORE the top-N truncation. We capture these by monkey-patching
  `DataFilter._select_top_stocks` to record the per-date dict, then unwrapping.
- (b) **top-N candidates** = result of `filter_earnings_data()` (post `_select_top_stocks`).
- (c) **final trades** = (b) minus the None-pre_open subset. Under the planned
  fallback removal, (b) candidates with `pre_open is None` would skip; the
  remaining are what live execution would attempt. We report this as the
  implicit "after-removal universe size".

The script never modifies state. It logs execution date and DataFetcher source
so future drift is detectable.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime
from typing import Dict, List

# Project bootstrap
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from src.config import DEFAULTS, BacktestConfig
from src.data_fetcher import DataFetcher
from src.data_filter import DataFilter
from src.universe_builder import build_target_universe


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Measure pre_open_price coverage.')
    p.add_argument('--start_date', required=True)
    p.add_argument('--end_date', required=True)
    p.add_argument('--output', default='reports/preopen_coverage_report.json',
                   help='JSON output path (relative to project root)')
    return p.parse_args()


def measure(start_date: str, end_date: str) -> Dict:
    df = DataFetcher(use_fmp=True)
    target_symbols, _src = build_target_universe(
        df,
        screener_price_min=DEFAULTS.screener_price_min,
        min_market_cap=DEFAULTS.min_market_cap,
    )

    cfg = BacktestConfig(start_date=start_date, end_date=end_date)
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

    earnings_data = df.get_earnings_data(
        start_date=start_date, end_date=end_date,
        target_symbols=list(target_symbols) if target_symbols else None,
    )

    # Capture stage-2 (pre-top-N) candidates by monkey-patching _select_top_stocks.
    captured: Dict[str, list] = {}
    original_select = fil._select_top_stocks

    def capture_then_select(date_stocks):
        # Deep-copy BEFORE original_select() runs, since it sorts the per-date
        # lists in place. We want the pre-top-N (pre-sort) order intact.
        captured['date_stocks'] = copy.deepcopy(date_stocks)
        return original_select(date_stocks)

    fil._select_top_stocks = capture_then_select  # type: ignore[assignment]
    try:
        topn_candidates = fil.filter_earnings_data(earnings_data)
    finally:
        fil._select_top_stocks = original_select  # type: ignore[assignment]

    stage2_candidates: List[Dict] = []
    for _date, stocks in captured.get('date_stocks', {}).items():
        stage2_candidates.extend(stocks)

    def _measure(candidates: List[Dict], label: str) -> Dict:
        total = len(candidates)
        none_count = 0
        none_examples: List[Dict] = []
        for c in candidates:
            symbol = c.get('code') or c.get('symbol')
            trade_date = c.get('trade_date')
            if not symbol or not trade_date:
                continue
            pre_open = df.get_preopen_price(symbol, trade_date)
            if pre_open is None:
                none_count += 1
                if len(none_examples) < 20:
                    none_examples.append({'symbol': symbol, 'trade_date': trade_date})
        pct = (none_count / total * 100) if total else 0.0
        return {
            f'{label}_total': total,
            f'{label}_none_count': none_count,
            f'{label}_none_pct': round(pct, 2),
            f'{label}_none_examples': none_examples,
        }

    stage2_metrics = _measure(stage2_candidates, 'stage2')
    topn_metrics = _measure(topn_candidates, 'topn')

    # (c) Implicit "after-removal" universe size = top-N minus None subset.
    final_total = topn_metrics['topn_total'] - topn_metrics['topn_none_count']

    return {
        'execution_date': datetime.utcnow().isoformat() + 'Z',
        'data_source': 'FMP (DataFetcher.get_preopen_price); fallback to daily Open in current code',
        'window_start': start_date,
        'window_end': end_date,
        **stage2_metrics,
        **topn_metrics,
        'final_total_after_fallback_removal': final_total,
    }


def main() -> int:
    args = parse_args()
    result = measure(args.start_date, args.end_date)
    out_path = os.path.join(project_root, args.output)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(result, f, indent=2)

    print('\n=== Pre-open coverage report ===')
    keys_to_print = [
        'execution_date', 'data_source', 'window_start', 'window_end',
        'stage2_total', 'stage2_none_count', 'stage2_none_pct',
        'topn_total', 'topn_none_count', 'topn_none_pct',
        'final_total_after_fallback_removal',
    ]
    print(json.dumps({k: result[k] for k in keys_to_print}, indent=2))
    print(f'\nFull report (with examples) saved to: {out_path}')

    s2 = result['stage2_none_pct']
    tn = result['topn_none_pct']
    if s2 <= 5 and tn <= 5:
        decision = 'BOTH ≤5% (recommend removing fallback; both paths skip pre_open=None)'
    else:
        decision = (
            f'NOT both ≤5% (stage2={s2}%, topn={tn}%); '
            'retain fallback; document drift in docs/parity_notes.md'
        )
    print(f'\nDecision: {decision}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
