"""Tests for robust parameter sweep tooling."""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.parameter_sweep import (
    Period,
    iter_parameter_grid,
    parse_float_list,
    parse_period,
    run_sweep,
    summarize_combination,
    write_csv,
)


def test_parse_float_list_accepts_comma_separated_values():
    assert parse_float_list('5, 7.5,10') == [5.0, 7.5, 10.0]


def test_parse_period_accepts_named_date_range():
    period = parse_period('y2025:2025-01-01:2025-12-31')
    assert period == Period('y2025', '2025-01-01', '2025-12-31')


def test_iter_parameter_grid_expands_all_dimensions():
    grid = iter_parameter_grid(
        min_surprises=[5, 10],
        max_gaps=[8],
        pre_earnings_changes=[0, 5],
        stop_losses=[8, 10],
        position_sizes=[10, 15],
    )
    assert len(grid) == 16
    assert grid[0] == {
        'min_surprise': 5.0,
        'max_gap': 8.0,
        'pre_earnings_change': 0.0,
        'stop_loss': 8.0,
        'position_size': 10.0,
    }


def test_summarize_combination_uses_worst_period_first():
    row = summarize_combination(
        1,
        {
            'min_surprise': 5.0,
            'max_gap': 10.0,
            'pre_earnings_change': 0.0,
            'stop_loss': 10.0,
            'position_size': 15.0,
        },
        {
            '2024': {
                'number_of_trades': 80,
                'total_return_pct': 45.0,
                'profit_factor': 2.7,
                'max_drawdown_pct': 3.0,
                'win_rate': 68.0,
            },
            '2025': {
                'number_of_trades': 100,
                'total_return_pct': -4.0,
                'profit_factor': 0.9,
                'max_drawdown_pct': 16.0,
                'win_rate': 54.0,
            },
        },
    )
    assert row['worst_return_pct'] == -4.0
    assert row['avg_return_pct'] == 20.5
    assert row['worst_profit_factor'] == 0.9
    assert row['max_drawdown_pct'] == 16.0
    assert row['total_trades'] == 180
    assert row['2024_return_pct'] == 45.0
    assert row['2025_return_pct'] == -4.0


def test_run_sweep_ranks_by_worst_return_before_average():
    periods = [
        Period('good', '2024-01-01', '2024-12-31'),
        Period('bad', '2025-01-01', '2025-12-31'),
    ]
    grid = [
        {
            'min_surprise': 5.0,
            'max_gap': 10.0,
            'pre_earnings_change': 0.0,
            'stop_loss': 10.0,
            'position_size': 15.0,
        },
        {
            'min_surprise': 10.0,
            'max_gap': 8.0,
            'pre_earnings_change': 0.0,
            'stop_loss': 8.0,
            'position_size': 10.0,
        },
    ]

    def runner(period, params):
        if params['min_surprise'] == 5.0:
            ret = 50.0 if period.name == 'good' else -10.0
        else:
            ret = 20.0 if period.name == 'good' else 2.0
        return {
            'number_of_trades': 10,
            'total_return_pct': ret,
            'profit_factor': 1.5,
            'max_drawdown_pct': 5.0,
            'win_rate': 60.0,
        }

    rows = run_sweep(periods, grid, runner=runner)
    assert rows[0]['min_surprise'] == 10.0
    assert rows[0]['rank'] == 1


def test_write_csv_includes_dynamic_period_columns(tmp_path):
    rows = [{
        'rank': 1,
        'combo_id': 1,
        'min_surprise': 5.0,
        '2024_return_pct': 12.3,
    }]
    output = tmp_path / 'sweep.csv'
    write_csv(rows, output)
    with output.open() as f:
        loaded = list(csv.DictReader(f))
    assert loaded[0]['2024_return_pct'] == '12.3'
