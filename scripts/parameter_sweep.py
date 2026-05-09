#!/usr/bin/env python3
"""Run multi-period parameter sweeps for the earnings strategy.

The goal is not to overfit one good year. This script evaluates each
parameter combination across multiple periods and ranks combinations by
worst-period return first, then average return, then drawdown.

Examples:
    python scripts/parameter_sweep.py --dry-run
    python scripts/parameter_sweep.py \
        --min-surprise 5,7.5,10 \
        --max-gap 8,10 \
        --pre-earnings-change 0,5 \
        --stop-loss 8,10,12 \
        --position-size 10,15 \
        --output reports/parameter_sweep_summary.csv
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python <3.9 fallback
    ZoneInfo = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from src.config import BacktestConfig, DEFAULTS
from src.main import EarningsBacktest


@dataclass(frozen=True)
class Period:
    name: str
    start_date: str
    end_date: str


ParamSet = Dict[str, float]
MetricsRunner = Callable[[Period, ParamSet], Dict[str, Any]]


def today_et() -> str:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d')
    return datetime.now().strftime('%Y-%m-%d')


def default_periods() -> List[Period]:
    return [
        Period('2024', '2024-01-01', '2024-12-31'),
        Period('2025', '2025-01-01', '2025-12-31'),
        Period('2026_ytd', '2026-01-01', today_et()),
    ]


def parse_float_list(raw: str) -> List[float]:
    values: List[float] = []
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        values.append(float(part))
    if not values:
        raise argparse.ArgumentTypeError('expected at least one numeric value')
    return values


def parse_period(raw: str) -> Period:
    parts = raw.split(':')
    if len(parts) != 3:
        raise argparse.ArgumentTypeError('period must be name:start_date:end_date')
    name, start_date, end_date = parts
    for value in (start_date, end_date):
        try:
            datetime.strptime(value, '%Y-%m-%d')
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f'invalid date {value!r}; expected YYYY-MM-DD'
            ) from exc
    if start_date >= end_date:
        raise argparse.ArgumentTypeError('period start_date must be before end_date')
    return Period(name=name, start_date=start_date, end_date=end_date)


def iter_parameter_grid(
    *,
    min_surprises: Iterable[float],
    max_gaps: Iterable[float],
    pre_earnings_changes: Iterable[float],
    stop_losses: Iterable[float],
    position_sizes: Iterable[float],
) -> List[ParamSet]:
    grid = []
    for min_surprise, max_gap, pre_change, stop_loss, position_size in product(
        min_surprises, max_gaps, pre_earnings_changes, stop_losses, position_sizes,
    ):
        grid.append({
            'min_surprise': float(min_surprise),
            'max_gap': float(max_gap),
            'pre_earnings_change': float(pre_change),
            'stop_loss': float(stop_loss),
            'position_size': float(position_size),
        })
    return grid


def run_backtest_period(
    period: Period,
    params: ParamSet,
    *,
    use_fmp_data: bool,
    target_symbols: Optional[Iterable[str]] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    config = BacktestConfig(
        start_date=period.start_date,
        end_date=period.end_date,
        min_surprise_percent=params['min_surprise'],
        max_gap_percent=params['max_gap'],
        pre_earnings_change=params['pre_earnings_change'],
        stop_loss=params['stop_loss'],
        position_size=params['position_size'],
        use_fmp_data=use_fmp_data,
        target_symbols=set(target_symbols) if target_symbols else None,
        generate_reports=False,
    )
    backtest = EarningsBacktest(config)
    stream = contextlib.nullcontext()
    if not verbose:
        stream = contextlib.redirect_stdout(io.StringIO())
    with stream:
        result = backtest.execute_backtest()
    return result.get('metrics', {})


def _metric(metrics: Dict[str, Any], key: str, default: float = 0.0) -> float:
    value = metrics.get(key, default)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(value):
        return default
    return value


def summarize_combination(
    combo_id: int,
    params: ParamSet,
    period_metrics: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    returns = [
        _metric(metrics, 'total_return_pct')
        for metrics in period_metrics.values()
    ]
    profit_factors = [
        _metric(metrics, 'profit_factor')
        for metrics in period_metrics.values()
    ]
    drawdowns = [
        _metric(metrics, 'max_drawdown_pct')
        for metrics in period_metrics.values()
    ]
    trades = [
        int(_metric(metrics, 'number_of_trades', _metric(metrics, 'total_trades')))
        for metrics in period_metrics.values()
    ]

    row: Dict[str, Any] = {
        'combo_id': combo_id,
        **params,
        'period_count': len(period_metrics),
        'total_trades': sum(trades),
        'worst_return_pct': round(min(returns) if returns else 0.0, 2),
        'avg_return_pct': round(sum(returns) / len(returns), 2) if returns else 0.0,
        'worst_profit_factor': round(min(profit_factors) if profit_factors else 0.0, 2),
        'max_drawdown_pct': round(max(drawdowns) if drawdowns else 0.0, 2),
    }

    # Transparent ranking helper: prioritize robustness, not one-year upside.
    row['robust_score'] = round(
        row['worst_return_pct'] + 0.5 * row['avg_return_pct'] - row['max_drawdown_pct'],
        2,
    )

    for name, metrics in period_metrics.items():
        prefix = name.replace('-', '_')
        row[f'{prefix}_trades'] = int(
            _metric(metrics, 'number_of_trades', _metric(metrics, 'total_trades'))
        )
        row[f'{prefix}_return_pct'] = _metric(metrics, 'total_return_pct')
        row[f'{prefix}_profit_factor'] = _metric(metrics, 'profit_factor')
        row[f'{prefix}_max_drawdown_pct'] = _metric(metrics, 'max_drawdown_pct')
        row[f'{prefix}_win_rate'] = _metric(metrics, 'win_rate')

    return row


def run_sweep(
    periods: List[Period],
    grid: List[ParamSet],
    *,
    runner: MetricsRunner,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for idx, params in enumerate(grid, start=1):
        metrics_by_period = {
            period.name: runner(period, params)
            for period in periods
        }
        rows.append(summarize_combination(idx, params, metrics_by_period))

    rows.sort(
        key=lambda row: (
            row['worst_return_pct'],
            row['avg_return_pct'],
            -row['max_drawdown_pct'],
            row['worst_profit_factor'],
        ),
        reverse=True,
    )
    for rank, row in enumerate(rows, start=1):
        row['rank'] = rank
    return rows


def write_csv(rows: List[Dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with output.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run robust multi-period parameter sweeps.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('--period', action='append', type=parse_period,
                        help='Period as name:start_date:end_date. Repeatable.')
    parser.add_argument('--min-surprise', type=parse_float_list,
                        default=[DEFAULTS.min_surprise_percent],
                        help='Comma-separated EPS surprise thresholds.')
    parser.add_argument('--max-gap', type=parse_float_list,
                        default=[DEFAULTS.max_gap_percent],
                        help='Comma-separated max opening gap percentages.')
    parser.add_argument('--pre-earnings-change', type=parse_float_list,
                        default=[DEFAULTS.pre_earnings_change],
                        help='Comma-separated minimum pre-earnings change percentages.')
    parser.add_argument('--stop-loss', type=parse_float_list,
                        default=[DEFAULTS.stop_loss],
                        help='Comma-separated stop-loss percentages.')
    parser.add_argument('--position-size', type=parse_float_list,
                        default=[DEFAULTS.position_size],
                        help='Comma-separated position size percentages.')
    parser.add_argument('--target-symbols', default='',
                        help='Optional comma-separated symbol subset for smoke runs.')
    parser.add_argument('--use-eodhd', action='store_true',
                        help='Use EODHD instead of FMP.')
    parser.add_argument('--limit', type=int, default=0,
                        help='Limit combinations after grid expansion (0 = no limit).')
    parser.add_argument('--output', type=Path,
                        default=Path('reports/parameter_sweep_summary.csv'))
    parser.add_argument('--dry-run', action='store_true',
                        help='Print planned combinations without running backtests.')
    parser.add_argument('--verbose', action='store_true',
                        help='Do not suppress per-backtest output.')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    periods = args.period or default_periods()
    grid = iter_parameter_grid(
        min_surprises=args.min_surprise,
        max_gaps=args.max_gap,
        pre_earnings_changes=args.pre_earnings_change,
        stop_losses=args.stop_loss,
        position_sizes=args.position_size,
    )
    if args.limit and args.limit > 0:
        grid = grid[:args.limit]

    print(f'Periods: {", ".join(p.name for p in periods)}')
    print(f'Combinations: {len(grid)}')
    if args.dry_run:
        for idx, params in enumerate(grid, start=1):
            print(f'{idx}: {params}')
        return 0

    target_symbols = [
        s.strip().upper()
        for s in args.target_symbols.split(',')
        if s.strip()
    ] or None

    def runner(period: Period, params: ParamSet) -> Dict[str, Any]:
        print(f'Running combo={params} period={period.name}...')
        return run_backtest_period(
            period,
            params,
            use_fmp_data=not args.use_eodhd,
            target_symbols=target_symbols,
            verbose=args.verbose,
        )

    rows = run_sweep(periods, grid, runner=runner)
    write_csv(rows, args.output)
    print(f'Wrote {len(rows)} ranked combinations to {args.output}')
    if rows:
        print('Top combination:')
        top = rows[0]
        print(
            f"rank=1 combo_id={top['combo_id']} "
            f"worst_return={top['worst_return_pct']} "
            f"avg_return={top['avg_return_pct']} "
            f"max_dd={top['max_drawdown_pct']} "
            f"params={{min_surprise={top['min_surprise']}, max_gap={top['max_gap']}, "
            f"pre_change={top['pre_earnings_change']}, stop_loss={top['stop_loss']}, "
            f"position_size={top['position_size']}}}"
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
