"""scripts/aggregate_screen_files.py
スクリーン結果 (screen_*.csv.gz) を読み込み、
日付ごとに先頭から最大 N 件 (Ticker) を抽出して 1 つの CSV にまとめる。
追加列:
- Trade Date : 決算発表時間が 9:30 以降なら +1 日、それ以外は発表日
- Source File: 元の screen ファイル名

Usage:
python scripts/aggregate_screen_files.py <screen_dir> --top_n 5 --output aggregated.csv
"""

from __future__ import annotations

import argparse
import gzip
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import List

import pandas as pd

# -----------------------------------------------------------------------------
# ユーティリティ
# -----------------------------------------------------------------------------

def calc_trade_date(earnings_datetime: datetime) -> datetime.date:
    """決算発表日時からトレード日を計算。
    9:30 以降を After とみなして +1 日。
    """
    market_open = time(9, 30)
    if earnings_datetime.time() >= market_open:
        return (earnings_datetime + timedelta(days=1)).date()
    return earnings_datetime.date()


def extract_rows(screen_path: Path, top_n: int) -> pd.DataFrame:
    """gzip 圧縮された screen_*.csv から先頭 top_n 行を抽出し、Trade Date を算出。"""
    with gzip.open(screen_path, "rt", encoding="utf-8") as f:
        df = pd.read_csv(f)

    if top_n > 0:
        df = df.head(top_n)

    # Earnings Date カラムが存在しない場合はスキップ
    if "Earnings Date" in df.columns:
        dt_series = pd.to_datetime(df["Earnings Date"], errors="coerce")
        trade_dates = dt_series.apply(lambda d: calc_trade_date(d) if pd.notnull(d) else None)
        df.insert(0, "Trade Date", trade_dates.astype(str))
    else:
        df.insert(0, "Trade Date", "")

    df.insert(1, "Source File", screen_path.name)
    return df

# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def parse_args():
    p = argparse.ArgumentParser(
        description="screen_*.csv(.gz) を集約して 1 つの CSV にまとめる",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("screen_dir", type=Path, help="screen ファイルがあるディレクトリ")
    p.add_argument("--top_n", type=int, default=5, help="各ファイルから抽出する最大行数 (0=無制限)")
    p.add_argument(
        "--output",
        type=Path,
        default=Path("aggregated_screen.csv"),
        help="出力 CSV パス",
    )
    return p.parse_args()


def main():
    args = parse_args()

    if not args.screen_dir.is_dir():
        print(f"[ERROR] Directory not found: {args.screen_dir}", file=sys.stderr)
        sys.exit(1)

    aggregated_rows: List[pd.DataFrame] = []
    for csv_gz in sorted(args.screen_dir.glob("screen_*.csv")):
        try:
            rows = extract_rows(csv_gz, args.top_n)
            aggregated_rows.append(rows)
            print(f"[INFO] {csv_gz.name}: {len(rows)} rows added")
        except Exception as e:
            print(f"[WARN] failed to process {csv_gz.name}: {e}")

    if not aggregated_rows:
        print("[ERROR] No data aggregated", file=sys.stderr)
        sys.exit(1)

    agg_df = pd.concat(aggregated_rows, ignore_index=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    agg_df.to_csv(args.output, index=False)
    print(f"[INFO] Aggregated CSV saved to {args.output} ({len(agg_df)} rows)")


if __name__ == "__main__":
    main() 