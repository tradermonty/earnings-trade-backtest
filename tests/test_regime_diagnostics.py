"""Tests for offline regime diagnostics."""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.analyze_regime_diagnostics import (
    InputSpec,
    build_breakdowns,
    build_markdown,
    load_trades,
    normalize_trades,
    parse_input_spec,
    summarize_label,
)


def test_parse_input_spec_requires_label_and_path():
    spec = parse_input_spec('2025=reports/trades.csv')
    assert spec == InputSpec('2025', spec.path)
    assert str(spec.path) == 'reports/trades.csv'


def test_normalize_trades_renames_ticker_and_adds_entry_month():
    df = normalize_trades(pd.DataFrame({
        'ticker': ['AAPL'],
        'entry_date': ['2025-01-15'],
        'exit_date': ['2025-02-01'],
        'pnl': ['10.5'],
        'pnl_rate': ['2.0'],
        'holding_period': ['12'],
        'exit_reason': [None],
    }))
    assert 'symbol' in df.columns
    assert df['symbol'].iloc[0] == 'AAPL'
    assert df['entry_month'].iloc[0] == '2025-01'
    assert df['exit_reason'].iloc[0] == 'unknown'
    assert df['pnl'].iloc[0] == 10.5


def test_summarize_label_counts_stop_loss_and_trailing_stop_rates():
    df = pd.DataFrame({
        'label': ['2025', '2025', '2025', '2025'],
        'pnl': [100.0, -50.0, -25.0, 75.0],
        'pnl_rate': [5.0, -3.0, -2.0, 4.0],
        'holding_period': [10, 3, 1, 20],
        'exit_reason': ['trailing_stop', 'stop_loss', 'stop_loss_intraday', 'partial_profit'],
    })
    summary = summarize_label(df, initial_capital=1000.0)
    assert summary['trades'] == 4
    assert summary['win_rate'] == 50.0
    assert summary['profit_factor'] == 2.33
    assert summary['total_return_pct'] == 10.0
    assert summary['stop_loss_count'] == 2
    assert summary['stop_loss_rate'] == 50.0
    assert summary['trailing_stop_count'] == 1


def test_build_breakdowns_uses_only_available_dimensions():
    df = pd.DataFrame({
        'label': ['2024', '2024', '2025'],
        'pnl': [100.0, -50.0, -25.0],
        'pnl_rate': [5.0, -3.0, -2.0],
        'holding_period': [10, 3, 1],
        'exit_reason': ['trailing_stop', 'stop_loss', 'stop_loss'],
        'market_cap_category': ['large', 'large', 'mid'],
    })
    breakdowns = build_breakdowns(df, ['exit_reason', 'market_cap_category', 'sector'])
    assert set(breakdowns['dimension']) == {'exit_reason', 'market_cap_category'}
    assert {'2024', '2025'} == set(breakdowns['label'])


def test_load_trades_reads_csv_and_labels_rows(tmp_path):
    csv_path = tmp_path / 'trades.csv'
    csv_path.write_text(
        'entry_date,exit_date,ticker,pnl,pnl_rate,holding_period,exit_reason\n'
        '2025-01-01,2025-01-10,AAPL,100,5,9,trailing_stop\n'
    )
    df = load_trades(InputSpec('sample', csv_path))
    assert df['label'].iloc[0] == 'sample'
    assert df['symbol'].iloc[0] == 'AAPL'


def test_build_markdown_contains_summary_and_exit_reason_table():
    summary = pd.DataFrame([{
        'label': '2025',
        'trades': 1,
        'win_rate': 0.0,
        'profit_factor': 0.0,
        'max_drawdown_pct': 1.0,
        'total_return_pct': -1.0,
        'avg_pnl_rate': -1.0,
        'avg_holding_period': 1.0,
        'stop_loss_count': 1,
        'stop_loss_rate': 100.0,
        'trailing_stop_count': 0,
        'trailing_stop_rate': 0.0,
    }])
    breakdowns = pd.DataFrame([{
        'label': '2025',
        'dimension': 'exit_reason',
        'bucket': 'stop_loss',
        'trades': 1,
        'total_return_pct': -1.0,
        'win_rate': 0.0,
        'profit_factor': 0.0,
        'stop_loss_rate': 100.0,
        'trailing_stop_rate': 0.0,
    }])
    text = build_markdown(summary, breakdowns)
    assert '# Regime Diagnostics' in text
    assert 'stop_loss' in text
