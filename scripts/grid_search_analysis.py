"""grid_search_analysis.py
既存バックテスト結果 CSV と aggregated_screen.csv を突合し、
指定した閾値グリッドでフィルタリングした場合の
勝率・平均損益率などを計算する簡易グリッドサーチ。

実行例:
python scripts/grid_search_analysis.py \
       --backtest reports/earnings_backtest_2024_09_01_2025_07_29_finviz_screener.csv \
       --aggregated aggregated_screen.csv \
       --output reports/grid_search_summary.csv
"""
from __future__ import annotations

import argparse
import itertools
from pathlib import Path
import pandas as pd
import numpy as np


def parse_args():
    p = argparse.ArgumentParser(description="Simple grid-search analysis on existing backtest results")
    p.add_argument("--backtest", type=Path, required=True, help="CSV with executed trades (backtest result)")
    p.add_argument("--aggregated", type=Path, required=True, help="aggregated_screen.csv path")
    p.add_argument("--output", type=Path, default=Path("grid_search_summary.csv"))
    p.add_argument("--verbose", action="store_true", help="Print filter pass counts for each grid item")
    return p.parse_args()


def load_and_merge(bt_path: Path, agg_path: Path) -> pd.DataFrame:
    bt = pd.read_csv(bt_path)
    agg = pd.read_csv(agg_path)
    bt.columns = bt.columns.str.strip()
    agg.columns = agg.columns.str.strip()

    # Standardise symbol/date columns
    agg["ticker"] = agg.get("Ticker", agg.columns[0]).astype(str)
    agg["trade_date"] = pd.to_datetime(agg["Trade Date"])
    # entry_date column may be 'entry_date' or 'Entry Date'
    if 'entry_date' in bt.columns:
        bt['entry_date'] = pd.to_datetime(bt['entry_date'])
    elif 'Entry Date' in bt.columns:
        bt['entry_date'] = pd.to_datetime(bt['Entry Date'])
    else:
        raise ValueError("Entry date column not found in backtest csv")

    # standardise symbol
    if 'ticker' not in bt.columns:
        bt['ticker'] = bt.get('symbol', bt.get('Symbol'))

    # create pnl_rate and pnl columns if missing
    if 'pnl_rate' not in bt.columns:
        if 'Return %' in bt.columns:
            bt['pnl_rate'] = bt['Return %'].astype(str).str.replace('%','').str.replace('(','-').str.replace(')','').astype(float)
        else:
            bt['pnl_rate'] = np.nan
    if 'pnl' not in bt.columns:
        if 'Return' in bt.columns:
            bt['pnl'] = bt['Return'].astype(str).str.replace('[\$,]','',regex=True).str.replace('(','-').str.replace(')','').astype(float)
        else:
            bt['pnl'] = bt['pnl_rate'] * 0  # placeholder

    merged = bt.merge(
        agg,
        left_on=["ticker", "entry_date"],
        right_on=["ticker", "trade_date"],
        how="left",
        suffixes=("", "_agg"),
    )
    merged["win"] = merged["pnl"] > 0
    return merged


def clean_num(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace(r"[%,\$]", "", regex=True)
        .replace({"nan": np.nan, "None": np.nan})
        .astype(float)
    )


def evaluate(df: pd.DataFrame) -> dict[str, float]:
    if len(df) == 0:
        return {"trades": 0, "win_rate": 0.0, "avg_pnl": 0.0}
    win_rate = df["win"].mean() * 100
    avg_pnl = df["pnl_rate"].mean()
    return {"trades": len(df), "win_rate": round(win_rate, 1), "avg_pnl": round(avg_pnl, 2)}


def main():
    args = parse_args()
    merged = load_and_merge(args.backtest, args.aggregated)

    # Pre-clean numeric columns once
    merged["eps"] = clean_num(merged.get("EPS Surprise", np.nan))
    merged["float_pct"] = clean_num(merged.get("Float %", np.nan))
    merged["quick"] = clean_num(merged.get("Quick Ratio", np.nan))
    merged["peg"] = clean_num(merged.get("PEG", np.nan))
    merged["gap"] = clean_num(merged.get("Gap", np.nan))

    # Grid definitions
    eps_min_list = [0.5, 1, 2, 3]
    float_max_list = [100, 90, 80, 70]
    quick_min_list = [0.5, 0.8, 1.0]
    gap_pair_list = [(0, 8), (1, 8), (0, 10), (1, 10)]

    records = []
    for eps_min, float_max, quick_min, (gmin, gmax) in itertools.product(
        eps_min_list, float_max_list, quick_min_list, gap_pair_list
    ):
        sub = merged.copy()
        initial=len(sub)
        sub = sub[(sub["eps"].isna()) | (sub["eps"] >= eps_min)]
        after_eps=len(sub)
        sub = sub[(sub["float_pct"].isna()) | (sub["float_pct"] <= float_max)]
        after_float=len(sub)
        sub = sub[(sub["quick"].isna()) | (sub["quick"] >= quick_min)]
        after_quick=len(sub)
        sub = sub[(sub["gap"].isna()) | ((sub["gap"] >= gmin) & (sub["gap"] <= gmax))]
        after_gap=len(sub)
        # Sectorと月制御 (オプションで追加可能)
        metrics = evaluate(sub)
        if args.verbose:
            print(f"eps≥{eps_min} float≤{float_max} quick≥{quick_min} gap {gmin}-{gmax}% | counts: start {initial}, eps {after_eps}, float {after_float}, quick {after_quick}, gap {after_gap}, final {metrics['trades']}")
        records.append({
            "eps_min": eps_min,
            "float_max": float_max,
            "quick_min": quick_min,
            "gap_min": gmin,
            "gap_max": gmax,
            **metrics,
        })

    summary = pd.DataFrame(records).sort_values(["win_rate", "avg_pnl"], ascending=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.output, index=False)

    # Markdown report
    md_lines = ["# Grid Search Summary\n", f"Generated from **{len(summary)}** parameter combinations\n"]
    md_lines.append("\n| eps_min | float_max | quick_min | gap_min | gap_max | trades | win_rate(%) | avg_pnl(%) |")
    md_lines.append("|---------|-----------|-----------|---------|---------|--------|-------------|-----------|")
    top10 = summary.head(10)
    for _, row in top10.iterrows():
        md_lines.append(
            f"| {int(row.eps_min)} | {int(row.float_max)} | {row.quick_min} | {row.gap_min} | {row.gap_max} | {row.trades} | {row.win_rate} | {row.avg_pnl} |"
        )
    md_path = args.output.with_suffix(".md")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"Summary CSV  -> {args.output}\nMarkdown table -> {md_path}")


if __name__ == "__main__":
    main() 