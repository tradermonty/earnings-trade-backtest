#!/usr/bin/env python3
"""Analyze regime-specific backtest degradation from trade CSVs.

This is an offline diagnostic tool: it consumes existing
``reports/earnings_backtest_*.csv`` files and produces compact summary and
breakdown tables. It does not call FMP/Alpaca.

Examples:
    python scripts/analyze_regime_diagnostics.py
    python scripts/analyze_regime_diagnostics.py \
        --input 2024=reports/earnings_backtest_2024_01_01_2024_12_31.csv \
        --input 2025=reports/earnings_backtest_2025_01_01_2025_12_31.csv \
        --summary-out reports/regime_diagnostics_summary.csv \
        --breakdown-out reports/regime_diagnostics_breakdown.csv
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DEFAULTS


@dataclass(frozen=True)
class InputSpec:
    label: str
    path: Path


DEFAULT_INPUTS = [
    InputSpec('2024', PROJECT_ROOT / 'reports' / 'earnings_backtest_2024_01_01_2024_12_31.csv'),
    InputSpec('2025', PROJECT_ROOT / 'reports' / 'earnings_backtest_2025_01_01_2025_12_31.csv'),
    InputSpec('2026_ytd', PROJECT_ROOT / 'reports' / 'earnings_backtest_2026_01_01_2026_05_09.csv'),
]


def parse_input_spec(raw: str) -> InputSpec:
    if '=' not in raw:
        raise argparse.ArgumentTypeError('input must be LABEL=PATH')
    label, path = raw.split('=', 1)
    label = label.strip()
    path = path.strip()
    if not label or not path:
        raise argparse.ArgumentTypeError('input must be LABEL=PATH')
    return InputSpec(label, Path(path))


def normalize_trades(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if 'ticker' in df.columns and 'symbol' not in df.columns:
        df = df.rename(columns={'ticker': 'symbol'})
    for col in ('entry_date', 'exit_date'):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    for col in ('pnl', 'pnl_rate', 'holding_period', 'shares'):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    if 'exit_reason' not in df.columns:
        df['exit_reason'] = 'unknown'
    df['exit_reason'] = df['exit_reason'].fillna('unknown').astype(str)
    if 'entry_date' in df.columns:
        df['entry_month'] = df['entry_date'].dt.strftime('%Y-%m')
    return df


def load_trades(spec: InputSpec) -> pd.DataFrame:
    df = pd.read_csv(spec.path)
    df = normalize_trades(df)
    df['label'] = spec.label
    return df


def _profit_factor(pnl: pd.Series) -> float:
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = abs(pnl[pnl <= 0].sum())
    if gross_loss == 0:
        return math.inf if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def _max_drawdown_pct(pnl: pd.Series, initial_capital: float) -> float:
    equity = initial_capital + pnl.cumsum()
    running_max = equity.cummax()
    drawdown = (running_max - equity) / running_max * 100
    return float(drawdown.max() or 0.0)


def _is_stop_loss(reason: str) -> bool:
    return 'stop_loss' in str(reason)


def _is_trailing_stop(reason: str) -> bool:
    return str(reason) == 'trailing_stop'


def summarize_label(
    df: pd.DataFrame,
    *,
    initial_capital: float = DEFAULTS.initial_capital,
) -> Dict[str, object]:
    pnl = df['pnl'] if 'pnl' in df.columns else pd.Series(dtype=float)
    reasons = df['exit_reason'] if 'exit_reason' in df.columns else pd.Series(dtype=str)
    trades = int(len(df))
    wins = int((pnl > 0).sum())
    total_return = float(pnl.sum() / initial_capital * 100) if initial_capital else 0.0
    stop_loss_count = int(reasons.map(_is_stop_loss).sum())
    trailing_stop_count = int(reasons.map(_is_trailing_stop).sum())
    return {
        'label': str(df['label'].iloc[0]) if len(df) else '',
        'trades': trades,
        'win_rate': round((wins / trades * 100) if trades else 0.0, 2),
        'profit_factor': round(_profit_factor(pnl), 2),
        'max_drawdown_pct': round(_max_drawdown_pct(pnl, initial_capital), 2),
        'total_return_pct': round(total_return, 2),
        'avg_pnl_rate': round(float(df['pnl_rate'].mean()) if 'pnl_rate' in df else 0.0, 2),
        'avg_holding_period': round(float(df['holding_period'].mean()) if 'holding_period' in df else 0.0, 2),
        'stop_loss_count': stop_loss_count,
        'stop_loss_rate': round((stop_loss_count / trades * 100) if trades else 0.0, 2),
        'trailing_stop_count': trailing_stop_count,
        'trailing_stop_rate': round((trailing_stop_count / trades * 100) if trades else 0.0, 2),
    }


def summarize_group(
    df: pd.DataFrame,
    dimension: str,
    *,
    initial_capital: float = DEFAULTS.initial_capital,
) -> pd.DataFrame:
    if dimension not in df.columns:
        return pd.DataFrame()
    rows: List[Dict[str, object]] = []
    for (label, bucket), group in df.groupby(['label', dimension], dropna=False):
        summary = summarize_label(group, initial_capital=initial_capital)
        rows.append({
            'label': label,
            'dimension': dimension,
            'bucket': bucket if pd.notna(bucket) else 'missing',
            **{k: v for k, v in summary.items() if k != 'label'},
        })
    return pd.DataFrame(rows)


def build_breakdowns(df: pd.DataFrame, dimensions: Sequence[str]) -> pd.DataFrame:
    frames = [summarize_group(df, dimension) for dimension in dimensions]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return ''
    headers = [str(c) for c in df.columns]
    lines = [
        '| ' + ' | '.join(headers) + ' |',
        '| ' + ' | '.join(['---'] * len(headers)) + ' |',
    ]
    for _, row in df.iterrows():
        values = [str(row[col]) for col in df.columns]
        lines.append('| ' + ' | '.join(values) + ' |')
    return '\n'.join(lines)


def build_markdown(summary: pd.DataFrame, breakdowns: pd.DataFrame) -> str:
    lines = ['# Regime Diagnostics', '']
    lines.append('## Summary')
    lines.append(_markdown_table(summary))
    if not breakdowns.empty:
        lines.append('')
        lines.append('## Exit Reasons')
        exit_reasons = breakdowns[breakdowns['dimension'] == 'exit_reason']
        if not exit_reasons.empty:
            cols = [
                'label', 'bucket', 'trades', 'total_return_pct', 'win_rate',
                'profit_factor', 'stop_loss_rate', 'trailing_stop_rate',
            ]
            lines.append(_markdown_table(exit_reasons[cols]))
        lines.append('')
        lines.append('## Available Breakdowns')
        for dimension in sorted(breakdowns['dimension'].unique()):
            if dimension == 'exit_reason':
                continue
            part = breakdowns[breakdowns['dimension'] == dimension]
            cols = [
                'label', 'bucket', 'trades', 'total_return_pct', 'win_rate',
                'profit_factor', 'stop_loss_rate',
            ]
            lines.append(f'### {dimension}')
            lines.append(_markdown_table(part[cols]))
            lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def available_default_inputs() -> List[InputSpec]:
    return [spec for spec in DEFAULT_INPUTS if spec.path.exists()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Analyze regime-specific backtest trade CSVs.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('--input', action='append', type=parse_input_spec,
                        help='Trade CSV as LABEL=PATH. Repeatable.')
    parser.add_argument('--summary-out', type=Path,
                        default=Path('reports/regime_diagnostics_summary.csv'))
    parser.add_argument('--breakdown-out', type=Path,
                        default=Path('reports/regime_diagnostics_breakdown.csv'))
    parser.add_argument('--markdown-out', type=Path,
                        default=Path('reports/regime_diagnostics.md'))
    parser.add_argument('--dimension', action='append',
                        help='Additional breakdown dimension.')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    specs = args.input or available_default_inputs()
    if not specs:
        raise SystemExit('No input CSVs found. Pass --input LABEL=PATH.')

    trades = pd.concat([load_trades(spec) for spec in specs], ignore_index=True)
    summary = pd.DataFrame([
        summarize_label(group)
        for _, group in trades.groupby('label', sort=False)
    ])
    dimensions = [
        'exit_reason',
        'entry_month',
        'market_cap_category',
        'price_range_category',
        'sector',
        *(args.dimension or []),
    ]
    breakdowns = build_breakdowns(trades, dimensions)

    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.summary_out, index=False)
    breakdowns.to_csv(args.breakdown_out, index=False)
    args.markdown_out.write_text(build_markdown(summary, breakdowns))

    print(f'Inputs: {", ".join(spec.label for spec in specs)}')
    print(f'Wrote {args.summary_out}')
    print(f'Wrote {args.breakdown_out}')
    print(f'Wrote {args.markdown_out}')
    print(summary.to_string(index=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
