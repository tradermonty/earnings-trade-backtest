"""scripts/run_backtest_from_aggregated.py
集約済み CSV を読み込み、各行の『Trade Date』『Ticker』をもとに
EarningsBacktest の TradeExecutor を利用して一括バックテストを行う。
スクリーナーフィルタはスキップし、集約 CSV に記載の銘柄・日付のみを対象とする。

Usage:
python scripts/run_backtest_from_aggregated.py aggregated_screen.csv \
       --start_date 2024-09-01 --end_date 2025-07-29
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd

# プロジェクトパス追加
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.main import EarningsBacktest  # noqa: E402
from src.config import BacktestConfig  # noqa: E402

# -----------------------------------------------------------------------------
# ヘルパー
# -----------------------------------------------------------------------------

def build_candidates_from_csv(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """集約 CSV から TradeExecutor 向け candidate dict を生成"""
    required_cols = {"Trade Date", "Ticker"}
    if not required_cols.issubset(df.columns):
        raise ValueError(f"CSV must include columns: {required_cols}")

    candidates: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        trade_date = str(row["Trade Date"]).split(" ")[0]
        symbol = str(row["Ticker"]).strip()
        if not symbol:
            continue
        # percent (EPS Surprise %) が存在すれば使用、なければ 0
        percent = float(row.get("EPS Surprise", 0.0)) if "EPS Surprise" in row else 0.0
        candidates.append({
            "code": symbol,
            "trade_date": trade_date,
            "report_date": trade_date,  # 便宜上同じ
            "price": None,  # 後で取得
            "gap": None,
            "percent": percent,
        })
    return candidates

# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Aggregated CSV からバックテストを実行")
    p.add_argument("aggregated_csv", type=Path)
    p.add_argument("--start_date", type=str, required=True)
    p.add_argument("--end_date", type=str, required=True)
    p.add_argument("--output", type=Path, default=Path("aggregated_backtest_results.json"))
    return p.parse_args()


# -----------------------------------------------------------------------------
# メイン
# -----------------------------------------------------------------------------

def main():
    args = parse_args()

    df = pd.read_csv(args.aggregated_csv)
    candidates = build_candidates_from_csv(df)
    symbols = {c["code"] for c in candidates}

    config = BacktestConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        target_symbols=symbols,
    )

    backtest = EarningsBacktest(config)

    # TradeExecutor を直接呼び出して candidates を渡す
    trades = backtest.trade_executor.execute_backtest(candidates)
    metrics = backtest.metrics_calculator.calculate_metrics(trades)

    # レポート生成
    daily_positions = backtest.trade_executor.get_daily_positions_data()
    html_path = backtest.report_generator.generate_html_report(
        trades,
        metrics,
        backtest._get_config_dict(),
        daily_positions,
    )
    csv_path = backtest.report_generator.generate_csv_report(
        trades,
        backtest._get_config_dict(),
    )

    results = {
        "trades": trades,
        "metrics": metrics,
        "config": backtest._get_config_dict(),
        "html_report": str(html_path),
        "csv_report": str(csv_path),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    # DataFrame や numpy 型をシリアライズできるよう変換
    import numpy as np

    def _default(o):
        import pandas as pd  # local import
        if isinstance(o, pd.DataFrame):
            return o.to_dict(orient="records")
        if isinstance(o, pd.Series):
            return o.to_dict()
        if isinstance(o, (np.integer, np.floating)):
            return float(o)
        return str(o)

    with args.output.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=_default)

    print(f"[INFO] Backtest finished. Trades: {len(trades)}")
    print(f"        HTML report -> {html_path}")
    print(f"        CSV  report -> {csv_path}")
    print(f"        JSON results -> {args.output}")


if __name__ == "__main__":  # pragma: no cover
    main() 