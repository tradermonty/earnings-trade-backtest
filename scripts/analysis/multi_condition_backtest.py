#!/usr/bin/env python3
"""
Multi-Condition Backtest Comparison Script
複数条件一括比較バックテストスクリプト

高EPSサプライズ & 低ギャップの仮説を検証するため、
複数のフィルタ条件を一括でバックテストし、結果を比較する。
"""

import argparse
import sys
import os
import json
from datetime import datetime
from typing import Dict, List, Any

import pandas as pd

# プロジェクトルートをパスに追加
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from src.config import BacktestConfig
from src.main import EarningsBacktest


# 比較対象条件の定義
CONDITIONS = [
    {"name": "baseline", "min_surprise": 5.0, "max_gap": 10.0},
    {"name": "condition_1", "min_surprise": 20.0, "max_gap": 3.0},
    {"name": "condition_2", "min_surprise": 20.0, "max_gap": 2.0},
    {"name": "condition_3", "min_surprise": 30.0, "max_gap": 1.0},
]


def create_config_from_condition(
    condition: Dict[str, Any],
    start_date: str,
    end_date: str,
    **kwargs
) -> BacktestConfig:
    """条件から BacktestConfig を生成する"""
    return BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        min_surprise_percent=condition["min_surprise"],
        max_gap_percent=condition["max_gap"],
        **kwargs
    )


def extract_metrics(
    condition_name: str,
    trades: List[Dict],
    metrics: Dict[str, Any]
) -> Dict[str, Any]:
    """バックテスト結果からメトリクスを抽出する

    metrics_calculator.py の出力キーに合わせてマッピング:
    - number_of_trades: トレード数
    - win_rate: 勝率
    - avg_win_loss_rate: 平均損益率 (%)
    - total_return_pct: 総リターン率 (%)
    - sharpe_ratio: シャープレシオ
    - max_drawdown_pct: 最大ドローダウン (%)
    """
    return {
        "condition": condition_name,
        "trades": metrics.get("number_of_trades", len(trades)),
        "win_rate": metrics.get("win_rate", 0.0),
        "avg_pnl": metrics.get("avg_win_loss_rate", 0.0),
        "total_return": metrics.get("total_return_pct", 0.0),
        "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
        "max_drawdown": metrics.get("max_drawdown_pct", 0.0),
    }


def compare_results(results: List[Dict[str, Any]]) -> pd.DataFrame:
    """複数条件の結果を比較用DataFrameに変換する"""
    return pd.DataFrame(results)


def format_comparison_table(df: pd.DataFrame) -> str:
    """比較結果をフォーマットされた文字列テーブルに変換する"""
    return df.to_string(index=False)


def parse_arguments():
    """コマンドライン引数をパースする"""
    parser = argparse.ArgumentParser(
        description='Multi-Condition Backtest Comparison',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # 日付設定
    default_start = "2024-01-01"
    default_end = datetime.now().strftime('%Y-%m-%d')

    parser.add_argument('--start_date', type=str, default=default_start,
                        help='Backtest start date (YYYY-MM-DD)')
    parser.add_argument('--end_date', type=str, default=default_end,
                        help='Backtest end date (YYYY-MM-DD)')
    parser.add_argument('--output_dir', type=str, default='reports',
                        help='Output directory for results')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose output')

    # バックテスト共通パラメータ
    parser.add_argument('--position_size', type=float, default=10.0,
                        help='Position size as percentage of capital')
    parser.add_argument('--margin_ratio', type=float, default=1.5,
                        help='Maximum margin ratio')
    parser.add_argument('--max_holding_days', type=int, default=90,
                        help='Maximum holding period in days')
    parser.add_argument('--screener_price_min', type=float, default=10.0,
                        help='Minimum stock price for screener')
    parser.add_argument('--min_market_cap', type=float, default=1.0,
                        help='Minimum market cap in billions USD')
    parser.add_argument('--stop_loss', type=float, default=6.0,
                        help='Stop loss percentage')

    return parser.parse_args()


def run_backtest_for_condition(
    condition: Dict[str, Any],
    start_date: str,
    end_date: str,
    verbose: bool = False,
    **extra_config
) -> Dict[str, Any]:
    """単一条件でバックテストを実行し、結果を返す"""
    condition_name = condition["name"]

    if verbose:
        print(f"\n--- Running backtest for: {condition_name} ---")
        print(f"  min_surprise: {condition['min_surprise']}%")
        print(f"  max_gap: {condition['max_gap']}%")

    try:
        # BacktestConfig を作成
        config = create_config_from_condition(
            condition,
            start_date=start_date,
            end_date=end_date,
            **extra_config
        )

        # バックテストを実行
        backtest = EarningsBacktest(config)
        backtest.execute_backtest()

        # メトリクスを抽出
        result = extract_metrics(
            condition_name,
            backtest.trades,
            backtest.metrics
        )

        if verbose:
            print(f"  Trades: {result['trades']}, Win Rate: {result['win_rate']:.1f}%")

        return result

    except Exception as e:
        print(f"Error running backtest for {condition_name}: {e}")
        return {
            "condition": condition_name,
            "trades": 0,
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "total_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "error": str(e)
        }


def run_all_backtests(
    conditions: List[Dict[str, Any]],
    start_date: str,
    end_date: str,
    verbose: bool = False,
    **extra_config
) -> List[Dict[str, Any]]:
    """すべての条件でバックテストを実行"""
    results = []
    for i, condition in enumerate(conditions, 1):
        print(f"\n[{i}/{len(conditions)}] Processing: {condition['name']}")
        result = run_backtest_for_condition(
            condition,
            start_date,
            end_date,
            verbose,
            **extra_config
        )
        results.append(result)
    return results


def save_results(
    df: pd.DataFrame,
    output_dir: str,
    start_date: str,
    end_date: str
) -> tuple:
    """結果をCSVとJSONで保存"""
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_name = f"multi_condition_comparison_{start_date}_{end_date}_{timestamp}"

    csv_path = os.path.join(output_dir, f"{base_name}.csv")
    json_path = os.path.join(output_dir, f"{base_name}.json")

    # CSV保存
    df.to_csv(csv_path, index=False)

    # JSON保存
    result_dict = {
        "period": {"start": start_date, "end": end_date},
        "conditions": df.to_dict(orient="records"),
        "generated_at": datetime.now().isoformat()
    }
    with open(json_path, 'w') as f:
        json.dump(result_dict, f, indent=2)

    return csv_path, json_path


def main():
    """メイン実行関数"""
    args = parse_arguments()

    print("=" * 60)
    print("Multi-Condition Backtest Comparison")
    print("=" * 60)
    print(f"Period: {args.start_date} to {args.end_date}")
    print(f"Conditions: {len(CONDITIONS)}")
    print(f"Position Size: {args.position_size}%")
    print(f"Stop Loss: {args.stop_loss}%")
    print(f"Max Holding Days: {args.max_holding_days}")
    print(f"Min Price: ${args.screener_price_min}")
    print(f"Min Market Cap: ${args.min_market_cap}B")
    print()

    # 追加パラメータを辞書にまとめる
    extra_config = {
        "position_size": args.position_size,
        "margin_ratio": args.margin_ratio,
        "max_holding_days": args.max_holding_days,
        "screener_price_min": args.screener_price_min,
        "min_market_cap": args.min_market_cap * 1e9,  # Convert to actual value
        "stop_loss": args.stop_loss,
    }

    # 全条件でバックテスト実行
    results = run_all_backtests(
        CONDITIONS,
        args.start_date,
        args.end_date,
        args.verbose,
        **extra_config
    )

    # 結果をDataFrameに変換
    df = compare_results(results)

    # 比較テーブルを表示
    print("\n" + "=" * 60)
    print("COMPARISON RESULTS")
    print("=" * 60)
    print()
    print(format_comparison_table(df))
    print()

    # 結果を保存
    csv_path, json_path = save_results(
        df,
        args.output_dir,
        args.start_date,
        args.end_date
    )

    print("=" * 60)
    print("OUTPUT FILES")
    print("=" * 60)
    print(f"CSV:  {csv_path}")
    print(f"JSON: {json_path}")
    print()


if __name__ == '__main__':
    main()
