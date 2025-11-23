#!/usr/bin/env python3
"""
Pre-Open Gap vs Confirmed Open Gap Error Analysis
プレオープンギャップ vs 確定オープンギャップの誤差分析

このスクリプトは、バックテストにおける最大の問題点を検証します：
- バックテストでは寄り付き後のギャップを使って銘柄選定
- 実際には寄り付き前に銘柄選定が必要
- その誤差がどの程度あるかを測定

検証項目:
1. プレマーケット価格 (09:25 ET) vs 実際のOpen価格の乖離
2. ギャップフィルタ (0-10%) による銘柄選定への影響
3. 「選定されたが実際は対象外」「選定されなかったが実際は対象」のケース分析
"""

import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np

# プロジェクトルートをパスに追加
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from src.alpaca_data_fetcher import AlpacaDataFetcher
from src.data_fetcher import DataFetcher


def analyze_gap_error(
    symbols: List[str],
    trade_dates: List[str],
    prev_closes: Dict[str, Dict[str, float]],
    max_gap_percent: float = 10.0
) -> Dict[str, Any]:
    """
    プレオープンギャップと確定ギャップの誤差を分析

    Args:
        symbols: 分析対象銘柄リスト
        trade_dates: 各銘柄のトレード日 (YYYY-MM-DD)
        prev_closes: {symbol: {date: prev_close_price}}
        max_gap_percent: ギャップ上限 (%)

    Returns:
        分析結果の辞書
    """
    try:
        alpaca = AlpacaDataFetcher(account_type="live")
    except Exception as e:
        print(f"Alpaca API初期化エラー: {e}")
        return {"error": str(e)}

    results = []

    for symbol, trade_date in zip(symbols, trade_dates):
        try:
            prev_close = prev_closes.get(symbol, {}).get(trade_date)
            if prev_close is None:
                print(f"  {symbol} {trade_date}: prev_close不明、スキップ")
                continue

            # プレオープン価格を取得 (09:25 ET)
            preopen_price = alpaca.get_preopen_price(symbol, trade_date, "09:25:00")

            # 実際のOpen価格を取得 (09:30 ET)
            open_price = alpaca.get_preopen_price(symbol, trade_date, "09:30:00")

            if preopen_price is None or open_price is None:
                print(f"  {symbol} {trade_date}: 価格データ取得失敗")
                continue

            # ギャップ率を計算
            preopen_gap = (preopen_price - prev_close) / prev_close * 100
            confirmed_gap = (open_price - prev_close) / prev_close * 100
            gap_error = confirmed_gap - preopen_gap

            # 銘柄選定への影響を判定
            preopen_selected = 0 <= preopen_gap <= max_gap_percent
            confirmed_selected = 0 <= confirmed_gap <= max_gap_percent

            selection_status = "correct"
            if preopen_selected and not confirmed_selected:
                selection_status = "false_positive"  # 選定したが実際は対象外
            elif not preopen_selected and confirmed_selected:
                selection_status = "false_negative"  # 選定しなかったが実際は対象

            results.append({
                "symbol": symbol,
                "trade_date": trade_date,
                "prev_close": prev_close,
                "preopen_price": preopen_price,
                "open_price": open_price,
                "preopen_gap": preopen_gap,
                "confirmed_gap": confirmed_gap,
                "gap_error": gap_error,
                "gap_error_abs": abs(gap_error),
                "preopen_selected": preopen_selected,
                "confirmed_selected": confirmed_selected,
                "selection_status": selection_status,
            })

            print(f"  {symbol} {trade_date}: pre-gap={preopen_gap:.2f}%, open-gap={confirmed_gap:.2f}%, error={gap_error:.2f}%")

        except Exception as e:
            print(f"  {symbol} {trade_date}: エラー - {e}")
            continue

    if not results:
        return {"error": "分析可能なデータがありません"}

    df = pd.DataFrame(results)

    # 統計サマリー
    summary = {
        "total_samples": len(df),
        "gap_error_mean": df["gap_error"].mean(),
        "gap_error_std": df["gap_error"].std(),
        "gap_error_abs_mean": df["gap_error_abs"].mean(),
        "gap_error_abs_median": df["gap_error_abs"].median(),
        "gap_error_abs_p95": df["gap_error_abs"].quantile(0.95),
        "gap_error_abs_max": df["gap_error_abs"].max(),
        "false_positive_count": len(df[df["selection_status"] == "false_positive"]),
        "false_negative_count": len(df[df["selection_status"] == "false_negative"]),
        "correct_count": len(df[df["selection_status"] == "correct"]),
        "false_positive_rate": len(df[df["selection_status"] == "false_positive"]) / len(df) * 100,
        "false_negative_rate": len(df[df["selection_status"] == "false_negative"]) / len(df) * 100,
        "accuracy_rate": len(df[df["selection_status"] == "correct"]) / len(df) * 100,
    }

    return {
        "summary": summary,
        "details": df.to_dict(orient="records"),
        "df": df,
    }


def get_recent_trades_for_analysis(
    start_date: str = "2024-10-01",
    end_date: str = "2024-12-31",
    limit: int = 50
) -> Tuple[List[str], List[str], Dict[str, Dict[str, float]]]:
    """
    バックテストの過去トレードから分析対象を抽出

    直近のデータでAlpacaの1分足データが取得可能な範囲を対象とする
    """
    from src.config import BacktestConfig
    from src.main import EarningsBacktest

    print(f"\n=== バックテスト実行 ({start_date} to {end_date}) ===")

    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        min_surprise_percent=5.0,
        max_gap_percent=15.0,  # 広めに取得して分析
    )

    backtest = EarningsBacktest(config)
    backtest.execute_backtest()

    trades = backtest.trades

    symbols = []
    trade_dates = []
    prev_closes = {}

    for trade in trades[:limit]:
        symbol = trade.get("symbol")
        entry_date = trade.get("entry_date")
        entry_price = trade.get("entry_price")
        gap = trade.get("gap", 0)

        if symbol and entry_date and entry_price:
            # prev_closeを逆算
            prev_close = entry_price / (1 + gap / 100)

            symbols.append(symbol)
            trade_dates.append(entry_date)

            if symbol not in prev_closes:
                prev_closes[symbol] = {}
            prev_closes[symbol][entry_date] = prev_close

    print(f"分析対象: {len(symbols)} トレード")
    return symbols, trade_dates, prev_closes


def run_manual_analysis():
    """
    手動で指定した銘柄・日付で分析を実行
    """
    # テスト用のサンプルデータ（実際のバックテスト結果から抜粋）
    test_cases = [
        # (symbol, trade_date, prev_close) - 最近の決算銘柄
        ("NVDA", "2024-11-21", 145.0),
        ("CRM", "2024-12-04", 340.0),
        ("AVGO", "2024-12-06", 170.0),
        ("ORCL", "2024-12-10", 185.0),
        ("ADBE", "2024-12-12", 520.0),
    ]

    symbols = [t[0] for t in test_cases]
    trade_dates = [t[1] for t in test_cases]
    prev_closes = {t[0]: {t[1]: t[2]} for t in test_cases}

    print("\n=== 手動サンプル分析 ===")
    result = analyze_gap_error(symbols, trade_dates, prev_closes)

    return result


def main():
    """メイン実行関数"""
    print("=" * 70)
    print("Pre-Open Gap vs Confirmed Open Gap Error Analysis")
    print("プレオープンギャップ vs 確定ギャップ 誤差分析")
    print("=" * 70)

    # 方法1: 手動サンプル分析
    print("\n[1] 手動サンプル分析")
    manual_result = run_manual_analysis()

    if "error" not in manual_result:
        summary = manual_result["summary"]
        print("\n--- サマリー ---")
        print(f"サンプル数: {summary['total_samples']}")
        print(f"ギャップ誤差 平均: {summary['gap_error_mean']:.2f}%")
        print(f"ギャップ誤差 標準偏差: {summary['gap_error_std']:.2f}%")
        print(f"ギャップ誤差 絶対値平均: {summary['gap_error_abs_mean']:.2f}%")
        print(f"ギャップ誤差 絶対値95%ile: {summary['gap_error_abs_p95']:.2f}%")
        print(f"False Positive率: {summary['false_positive_rate']:.1f}%")
        print(f"False Negative率: {summary['false_negative_rate']:.1f}%")
        print(f"正解率: {summary['accuracy_rate']:.1f}%")
    else:
        print(f"エラー: {manual_result['error']}")

    # 方法2: バックテスト結果からの分析
    print("\n" + "=" * 70)
    print("[2] バックテスト結果からの分析 (直近3ヶ月)")
    print("=" * 70)

    try:
        symbols, trade_dates, prev_closes = get_recent_trades_for_analysis(
            start_date="2024-10-01",
            end_date="2024-12-31",
            limit=30
        )

        if symbols:
            backtest_result = analyze_gap_error(symbols, trade_dates, prev_closes)

            if "error" not in backtest_result:
                summary = backtest_result["summary"]
                print("\n--- バックテストトレードの誤差分析サマリー ---")
                print(f"サンプル数: {summary['total_samples']}")
                print(f"ギャップ誤差 平均: {summary['gap_error_mean']:.2f}%")
                print(f"ギャップ誤差 標準偏差: {summary['gap_error_std']:.2f}%")
                print(f"ギャップ誤差 絶対値平均: {summary['gap_error_abs_mean']:.2f}%")
                print(f"ギャップ誤差 絶対値中央値: {summary['gap_error_abs_median']:.2f}%")
                print(f"ギャップ誤差 絶対値95%ile: {summary['gap_error_abs_p95']:.2f}%")
                print(f"ギャップ誤差 絶対値最大: {summary['gap_error_abs_max']:.2f}%")
                print()
                print("銘柄選定への影響:")
                print(f"  False Positive (選定したが対象外): {summary['false_positive_count']}件 ({summary['false_positive_rate']:.1f}%)")
                print(f"  False Negative (選定しなかったが対象): {summary['false_negative_count']}件 ({summary['false_negative_rate']:.1f}%)")
                print(f"  正解: {summary['correct_count']}件 ({summary['accuracy_rate']:.1f}%)")

                # 詳細をCSVに保存
                df = backtest_result["df"]
                output_path = os.path.join(project_root, "reports", "gap_error_analysis.csv")
                df.to_csv(output_path, index=False)
                print(f"\n詳細をCSVに保存: {output_path}")
            else:
                print(f"エラー: {backtest_result['error']}")
        else:
            print("分析対象のトレードがありません")

    except Exception as e:
        print(f"バックテスト分析エラー: {e}")
        import traceback
        traceback.print_exc()

    # 結論と推奨事項
    print("\n" + "=" * 70)
    print("結論と推奨事項")
    print("=" * 70)
    print("""
1. ギャップ誤差の影響:
   - プレオープン価格と実際のOpen価格には誤差がある
   - この誤差により、銘柄選定の精度が低下する可能性

2. バックテストの限界:
   - ルックアヘッドバイアス（確定後の情報で選定）の影響
   - 実トレードではプレマーケット価格でしか判断できない

3. 推奨対応策:
   a) ギャップフィルタの緩和: 0-10% → 0-12% など余裕を持たせる
   b) プレマーケットデータの活用: 09:25 ETの価格で判断
   c) 複数段階のフィルタ:
      - Stage 1: EPSサプライズのみで事前選定
      - Stage 2: 寄り付き直後にギャップ確認してエントリー判断
   d) スリッページの増加: 0.3% → 0.5-1.0%
""")


if __name__ == "__main__":
    main()
