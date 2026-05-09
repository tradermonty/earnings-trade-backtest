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
import copy
import csv
import io
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

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
PARAM_KEYS = (
    'min_surprise',
    'max_gap',
    'pre_earnings_change',
    'stop_loss',
    'position_size',
)


def _clone_cached_value(value: Any) -> Any:
    """Return a defensive copy for mutable cached API results."""
    if isinstance(value, (dict, list, set, tuple)):
        return copy.deepcopy(value)
    if hasattr(value, 'copy'):
        try:
            return value.copy(deep=True)
        except TypeError:
            try:
                return value.copy()
            except TypeError:
                pass
    return copy.deepcopy(value)


def _freeze(value: Any) -> Any:
    """Convert common containers into hashable cache-key fragments."""
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze(val)) for key, val in value.items()))
    if isinstance(value, (list, tuple, set)):
        return tuple(_freeze(val) for val in value)
    return value


class _MemoizingFMPFetcher:
    """Small proxy for FMP calls that bypass DataFetcher methods."""

    def __init__(self, wrapped: Any):
        self._wrapped = wrapped
        self._stock_screener_cache: Dict[Tuple[Any, ...], Any] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    def stock_screener(self, *args: Any, **kwargs: Any) -> Any:
        key = (_freeze(args), _freeze(kwargs))
        if key not in self._stock_screener_cache:
            self._stock_screener_cache[key] = self._wrapped.stock_screener(
                *args, **kwargs
            )
        return _clone_cached_value(self._stock_screener_cache[key])


class MemoizingDataFetcher:
    """In-process cache for repeated parameter-sweep backtests.

    The sweep runs the same periods many times while changing only strategy
    parameters.  This wrapper keeps the expensive market/earnings API calls in
    memory and returns defensive copies so downstream filters cannot mutate the
    cache across combinations.
    """

    def __init__(self, wrapped: Any):
        self._wrapped = wrapped
        self.use_fmp = getattr(wrapped, 'use_fmp', False)
        self.api_key = getattr(wrapped, 'api_key', '')
        wrapped_fmp = getattr(wrapped, 'fmp_fetcher', None)
        self.fmp_fetcher = (
            _MemoizingFMPFetcher(wrapped_fmp)
            if wrapped_fmp is not None
            else None
        )
        self.alpaca_fetcher = getattr(wrapped, 'alpaca_fetcher', None)
        self._earnings_cache: Dict[Tuple[Any, ...], Any] = {}
        self._historical_cache: Dict[Tuple[str, str, str], Any] = {}
        self._preopen_cache: Dict[Tuple[str, str], Any] = {}
        self._market_cap_cache: Dict[Tuple[str, str], Any] = {}
        self._sp500_cache: Optional[Any] = None
        self._mid_small_cache: Dict[Tuple[float, float], Any] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    @property
    def has_fmp_screener(self) -> bool:
        return self.fmp_fetcher is not None

    def get_sp500_symbols(self) -> List[str]:
        if self._sp500_cache is None:
            self._sp500_cache = self._wrapped.get_sp500_symbols()
        return _clone_cached_value(self._sp500_cache)

    def get_mid_small_symbols(
        self,
        min_market_cap: float = 1e9,
        max_market_cap: float = 50e9,
    ) -> List[str]:
        key = (float(min_market_cap), float(max_market_cap))
        if key not in self._mid_small_cache:
            self._mid_small_cache[key] = self._wrapped.get_mid_small_symbols(
                min_market_cap=min_market_cap,
                max_market_cap=max_market_cap,
            )
        return _clone_cached_value(self._mid_small_cache[key])

    def get_earnings_data(
        self,
        start_date: str,
        end_date: str,
        target_symbols: Optional[list] = None,
    ) -> Dict[str, Any]:
        symbols_key = tuple(sorted(target_symbols)) if target_symbols else None
        key = (start_date, end_date, symbols_key)
        if key not in self._earnings_cache:
            self._earnings_cache[key] = self._wrapped.get_earnings_data(
                start_date,
                end_date,
                target_symbols=target_symbols,
            )
        return _clone_cached_value(self._earnings_cache[key])

    def get_historical_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> Any:
        key = (symbol, start_date, end_date)
        if key not in self._historical_cache:
            self._historical_cache[key] = self._wrapped.get_historical_data(
                symbol,
                start_date,
                end_date,
            )
        return _clone_cached_value(self._historical_cache[key])

    def get_preopen_price(self, symbol: str, trade_date: str) -> Optional[float]:
        key = (symbol, trade_date)
        if key not in self._preopen_cache:
            self._preopen_cache[key] = self._wrapped.get_preopen_price(
                symbol,
                trade_date,
            )
        return self._preopen_cache[key]

    def get_historical_market_cap(
        self,
        symbol: str,
        date: str,
    ) -> Optional[float]:
        key = (symbol, date)
        if key not in self._market_cap_cache:
            self._market_cap_cache[key] = self._wrapped.get_historical_market_cap(
                symbol,
                date,
            )
        return self._market_cap_cache[key]


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
    data_fetcher: Optional[Any] = None,
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
    backtest = EarningsBacktest(
        config,
        data_fetcher=data_fetcher,
        target_symbols=set(target_symbols) if target_symbols else None,
    )
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


def _param_key(params: Dict[str, Any]) -> Tuple[str, ...]:
    return tuple(f'{float(params[key]):.10g}' for key in PARAM_KEYS)


def completed_param_keys(rows: List[Dict[str, Any]]) -> set[Tuple[str, ...]]:
    return {
        _param_key(row)
        for row in rows
        if all(key in row and row[key] != '' for key in PARAM_KEYS)
    }


def filter_rows_to_grid(
    rows: List[Dict[str, Any]],
    grid: List[ParamSet],
) -> List[Dict[str, Any]]:
    requested = {_param_key(params) for params in grid}
    return [
        row for row in rows
        if all(key in row and row[key] != '' for key in PARAM_KEYS)
        and _param_key(row) in requested
    ]


def rank_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows.sort(
        key=lambda row: (
            _metric(row, 'worst_return_pct'),
            _metric(row, 'avg_return_pct'),
            -_metric(row, 'max_drawdown_pct'),
            _metric(row, 'worst_profit_factor'),
        ),
        reverse=True,
    )
    for rank, row in enumerate(rows, start=1):
        row['rank'] = rank
    return rows


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

    return rank_rows(rows)


def read_csv_rows(output: Path) -> List[Dict[str, Any]]:
    if not output.exists():
        return []
    with output.open(newline='') as f:
        return list(csv.DictReader(f))


def run_sweep_incremental(
    periods: List[Period],
    grid: List[ParamSet],
    *,
    runner: MetricsRunner,
    output: Path,
    resume: bool = False,
) -> List[Dict[str, Any]]:
    """Run a sweep while writing a resumable CSV after each combination."""
    rows = filter_rows_to_grid(read_csv_rows(output), grid) if resume else []
    completed = completed_param_keys(rows)
    if rows:
        print(f'Resumed {len(rows)} completed combinations from {output}')

    for idx, params in enumerate(grid, start=1):
        key = _param_key(params)
        if key in completed:
            print(f'Skipping completed combo_id={idx}: {params}')
            continue
        metrics_by_period = {
            period.name: runner(period, params)
            for period in periods
        }
        rows.append(summarize_combination(idx, params, metrics_by_period))
        completed.add(key)
        write_csv(rank_rows(rows), output)
        print(f'Saved progress: {len(rows)}/{len(grid)} combinations -> {output}')

    return rank_rows(rows)


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


def print_top_combination(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
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


def build_shared_sweep_context(
    *,
    use_fmp_data: bool,
    explicit_target_symbols: Optional[List[str]],
) -> Tuple[MemoizingDataFetcher, Optional[List[str]], str]:
    """Create one cached data fetcher and, when possible, one shared universe."""
    from src.data_fetcher import DataFetcher
    from src.universe_builder import build_target_universe

    data_fetcher = MemoizingDataFetcher(DataFetcher(use_fmp=use_fmp_data))
    if explicit_target_symbols:
        return data_fetcher, explicit_target_symbols, 'explicit'

    base_config = BacktestConfig(
        start_date='2000-01-01',
        end_date='2000-01-02',
        use_fmp_data=use_fmp_data,
        generate_reports=False,
    )
    symbols, source = build_target_universe(
        data_fetcher,
        sp500_only=base_config.sp500_only,
        mid_small_only=base_config.mid_small_only,
        min_market_cap=base_config.min_market_cap,
        max_market_cap=base_config.max_market_cap,
        screener_price_min=base_config.screener_price_min,
        backtest_mode=True,
    )
    if symbols:
        return data_fetcher, sorted(symbols), source
    return data_fetcher, None, source


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
    parser.add_argument('--resume', action='store_true',
                        help='Resume from existing output CSV and skip completed parameter combinations.')
    parser.add_argument('--no-shared-data', action='store_true',
                        help='Disable shared DataFetcher/universe cache between combinations.')
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

    if args.resume:
        existing_rows = filter_rows_to_grid(read_csv_rows(args.output), grid)
        completed = completed_param_keys(existing_rows)
        if existing_rows and all(_param_key(params) in completed for params in grid):
            rows = rank_rows(existing_rows)
            write_csv(rows, args.output)
            print(f'All {len(grid)} combinations already completed in {args.output}')
            print_top_combination(rows)
            return 0

    shared_fetcher = None
    if not args.no_shared_data:
        shared_fetcher, target_symbols, source = build_shared_sweep_context(
            use_fmp_data=not args.use_eodhd,
            explicit_target_symbols=target_symbols,
        )
        if target_symbols:
            print(
                f'Shared data cache enabled; universe={source} '
                f'({len(target_symbols)} symbols)'
            )
        else:
            print(
                f'Shared data cache enabled; universe={source} '
                '(per-run universe fallback remains enabled)'
            )

    def runner(period: Period, params: ParamSet) -> Dict[str, Any]:
        print(f'Running combo={params} period={period.name}...')
        return run_backtest_period(
            period,
            params,
            use_fmp_data=not args.use_eodhd,
            data_fetcher=shared_fetcher,
            target_symbols=target_symbols,
            verbose=args.verbose,
        )

    rows = run_sweep_incremental(
        periods,
        grid,
        runner=runner,
        output=args.output,
        resume=args.resume,
    )
    write_csv(rows, args.output)
    print(f'Wrote {len(rows)} ranked combinations to {args.output}')
    print_top_combination(rows)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
