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
import math
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd

# プロジェクトパス追加
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.finviz_csv import (  # noqa: E402
    ALWAYS_REQUIRED,
    ALWAYS_REQUIRED_FIELDS,
    FinvizCsvError,
    add_csv_line_numbers,
    parse_columns,
    parse_percent,
    validate_columns,
)

# -----------------------------------------------------------------------------
# ヘルパー
# -----------------------------------------------------------------------------
# 列と単位の契約は docs/finviz_csv_contract.md と src/finviz_csv.py を参照。


def _filter_specs(*, min_eps, min_price, max_gap, min_volume, min_market_cap_b,
                  pre_change, min_perf1h, max_ps_ratio, max_pe_ratio,
                  min_profit_margin, min_roa, max_volatility_week, min_perf_week,
                  max_perf_week, max_perf_month, max_rsi14, max_pb_ratio):
    """有効なフィルタごとに (ラベル, 必要フィールド, 条件関数) を返す。

    閾値が None のフィルタは無効で、対応する列も要求しない。
    条件関数は欠損 (NaN) を常に False として扱う (欠損は 0 とみなさない)。
    """
    specs = []

    def add(threshold, label, keys, fn):
        if threshold is not None:
            specs.append((label, tuple(keys), fn))

    add(min_eps, f"EPS Surprise >= {min_eps}%", ["_eps"], lambda d: d["_eps"] >= min_eps)
    add(min_price, f"Price >= ${min_price}", ["_price"], lambda d: d["_price"] >= min_price)
    add(min_volume, f"Avg Volume >= {min_volume}K", ["_vol"],
        lambda d: d["_vol"] >= min_volume * 1_000)
    add(max_gap, f"0 <= Gap <= {max_gap}%", ["_gap"],
        lambda d: (d["_gap"] >= 0) & (d["_gap"] <= max_gap))
    add(pre_change, f"Pre Change >= {pre_change}%", ["_perf_m", "_change"],
        lambda d: (d["_perf_m"] - d["_change"]) >= pre_change)
    add(min_perf1h, f"Perf 1H >= {min_perf1h}%", ["_perf1h"], lambda d: d["_perf1h"] >= min_perf1h)
    add(min_market_cap_b, f"MktCap >= {min_market_cap_b}B", ["_mcap"],
        lambda d: d["_mcap"] >= min_market_cap_b * 1e9)
    add(max_ps_ratio, f"P/S <= {max_ps_ratio}", ["_ps"], lambda d: d["_ps"] <= max_ps_ratio)
    add(max_pe_ratio, f"P/E <= {max_pe_ratio}", ["_pe"], lambda d: d["_pe"] <= max_pe_ratio)
    add(min_profit_margin, f"Profit Margin >= {min_profit_margin}%", ["_profit_margin"],
        lambda d: d["_profit_margin"] >= min_profit_margin)
    add(min_roa, f"ROA >= {min_roa}%", ["_roa"], lambda d: d["_roa"] >= min_roa)
    add(max_volatility_week, f"Vol(Week) <= {max_volatility_week}%", ["_vol_week"],
        lambda d: d["_vol_week"] <= max_volatility_week)
    add(min_perf_week, f"Perf(Week) >= {min_perf_week}%", ["_perf_week"],
        lambda d: d["_perf_week"] >= min_perf_week)
    add(max_perf_week, f"Perf(Week) <= {max_perf_week}%", ["_perf_week"],
        lambda d: d["_perf_week"] <= max_perf_week)
    add(max_perf_month, f"Perf(Month) <= {max_perf_month}%", ["_perf_m"],
        lambda d: d["_perf_m"] <= max_perf_month)
    add(max_rsi14, f"RSI(14) <= {max_rsi14}", ["_rsi14"], lambda d: d["_rsi14"] <= max_rsi14)
    add(max_pb_ratio, f"P/B <= {max_pb_ratio}", ["_pb"], lambda d: d["_pb"] <= max_pb_ratio)
    return specs


def filter_dataframe(df: pd.DataFrame, *, min_eps: float | None = 5.0,
                     min_price: float | None = 10.0,
                     max_gap: float | None = 10.0, min_volume: float | None = 200,
                     min_market_cap_b: float | None = None,
                     pre_change: float | None = 0.0,
                     min_perf1h: float | None = 0.0,
                     max_ps_ratio: float | None = None,
                     max_pe_ratio: float | None = None,
                     min_profit_margin: float | None = None,
                     min_roa: float | None = None,
                     max_volatility_week: float | None = None,
                     min_perf_week: float | None = None,
                     # 追加: 上限フィルタ（除外条件）
                     max_perf_week: float | None = None,
                     max_perf_month: float | None = None,
                     max_rsi14: float | None = None,
                     max_pb_ratio: float | None = None,
                     max_trades_per_day: int | None = 5,
                     debug: bool = False) -> pd.DataFrame:
    """aggregated_screen.csv の DataFrame に対して DataFilter 相当の条件で絞り込みを行う。

    - 有効なフィルタに必要な列が無い場合は、候補選定の前に FinvizCsvError を送出する。
    - 値が欠損している行は、その行が必要とするフィルタで不合格とし、件数を報告する。
      測定値の 0 (例: ``0%``, ``0``) は欠損と区別し、通常の値として評価する。
    """
    df = df.copy()
    df.columns = df.columns.str.strip()

    specs = _filter_specs(
        min_eps=min_eps, min_price=min_price, max_gap=max_gap, min_volume=min_volume,
        min_market_cap_b=min_market_cap_b, pre_change=pre_change, min_perf1h=min_perf1h,
        max_ps_ratio=max_ps_ratio, max_pe_ratio=max_pe_ratio,
        min_profit_margin=min_profit_margin, min_roa=min_roa,
        max_volatility_week=max_volatility_week, min_perf_week=min_perf_week,
        max_perf_week=max_perf_week, max_perf_month=max_perf_month,
        max_rsi14=max_rsi14, max_pb_ratio=max_pb_ratio,
    )
    required = {"EPS Surprise ranking": ALWAYS_REQUIRED_FIELDS}
    required.update({label: keys for label, keys, _ in specs})
    resolved = validate_columns(df, required)
    df = parse_columns(df, resolved)

    total = len(df)
    cond = pd.Series(True, index=df.index)
    missing_report = {}
    if debug:
        print("[DEBUG] 条件別通過数:")
    for label, keys, fn in specs:
        missing = df[list(keys)].isna().any(axis=1)
        passed = fn(df).fillna(False).astype(bool) & ~missing
        if missing.any():
            missing_report[label] = int(missing.sum())
        if debug:
            print(f"  {label:<28}: {int(passed.sum())}/{total}")
        cond &= passed

    # 識別子と、順位付けに使う EPS Surprise が欠損している行も除外する。
    # min_eps フィルタが有効なら EPS の欠損はそこで報告済みなので二重に数えない。
    eps_reported = any("_eps" in keys for _, keys, _ in specs)
    base_missing = {
        "Trade Date": df["Trade Date"].isna(),
        "Ticker": df["Ticker"].isna() | (df["Ticker"].astype(str).str.strip() == ""),
        "EPS Surprise ranking": df["_eps"].isna(),
    }
    for label, missing in base_missing.items():
        if missing.any() and not (label == "EPS Surprise ranking" and eps_reported):
            missing_report[label] = int(missing.sum())
        cond &= ~missing

    for label, n in missing_report.items():
        print(f"[WARN] 欠損値のため除外: {label} -> {n}/{total} 行")
    df.attrs["missing_report"] = missing_report

    filtered = df[cond].reset_index(drop=True)
    filtered.attrs["missing_report"] = missing_report

    # 日付ごとに EPS サプライズ上位N銘柄を選択 (Nは max_trades_per_day)
    if max_trades_per_day is not None and max_trades_per_day > 0:
        before_n = len(filtered)
        filtered = (
            filtered.sort_values("_eps", ascending=False, kind="mergesort")
                    .groupby("Trade Date", as_index=False, group_keys=False)
                    .head(max_trades_per_day)
                    .reset_index(drop=True)
        )
        filtered.attrs["missing_report"] = missing_report
        if debug:
            print(f"[DEBUG] 日付ごと上位{max_trades_per_day}抽出: {len(filtered)}/{before_n}")

    return filtered


def build_candidates_from_csv(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """フィルタ後 DF から TradeExecutor 向け candidate dict を生成する。

    ``percent`` と ``gap`` はパーセントポイント。filter_dataframe が付けた
    ``_eps`` / ``_gap`` 列が無い場合は、同じ契約で生の列を解析する。

    TradeExecutor はリストの順に資金とマージンを計算するため、候補は
    Trade Date の昇順に並べる。同じ日の中では入力の順 (EPS 降順) を保つ。
    """
    missing = [c for c in ALWAYS_REQUIRED if c not in df.columns]
    if missing:
        raise FinvizCsvError(f"CSV must include columns: {missing}")

    ordered = df.assign(_trade_dt=pd.to_datetime(df["Trade Date"]))
    ordered = ordered.sort_values("_trade_dt", kind="mergesort")

    candidates: List[Dict[str, Any]] = []
    for _, row in ordered.iterrows():
        if pd.isna(row["_trade_dt"]) or pd.isna(row["Ticker"]):
            continue
        trade_date = row["_trade_dt"].strftime("%Y-%m-%d")
        symbol = str(row["Ticker"]).strip()
        if not symbol:
            continue
        percent = row["_eps"] if "_eps" in row else parse_percent(row.get("EPS Surprise"))
        if pd.isna(percent):
            raise FinvizCsvError(f"{symbol} {trade_date}: EPS Surprise is missing")
        gap = row["_gap"] if "_gap" in row else parse_percent(row.get("Gap"))
        candidates.append({
            "code": symbol,
            "trade_date": trade_date,
            "report_date": trade_date,  # 便宜上同じ
            "price": None,  # TradeExecutor が当日の寄付 (Open) を使う
            # 欠損時は None を渡し、TradeExecutor に価格データから計算させる
            "gap": None if pd.isna(gap) else float(gap),
            "percent": float(percent),
        })
    return candidates

# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def _optional_float(text: str) -> float | None:
    """数値、または "none" / "off" (フィルタ無効) を受け付ける。"""
    if text.strip().lower() in {"none", "off"}:
        return None
    return float(text)


def parse_args():
    p = argparse.ArgumentParser(description="Aggregated CSV からバックテストを実行し、フィルタ条件を適用する。"
                                "min/max 系の閾値は none で無効にでき、無効なフィルタの列は不要になる",
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("aggregated_csv", type=Path, help="aggregated_screen.csv のパス")
    p.add_argument("--start_date", type=str, required=True, help="バックテスト開始日 (YYYY-MM-DD)")
    p.add_argument("--end_date", type=str, required=True, help="バックテスト終了日 (YYYY-MM-DD)")
    p.add_argument("--output", type=Path, default=Path("aggregated_backtest_results.json"), help="結果 JSON の出力先")

    # フィルタパラメータ (DataFilter 相当)
    p.add_argument("--min_eps", type=_optional_float, default=0, help="最低 EPS サプライズ率 (%%)")
    p.add_argument("--min_price", type=_optional_float, default=30.0, help="最低株価 ($)")
    p.add_argument("--max_gap", type=_optional_float, default=10.0, help="最大ギャップ率 (%%)")
    p.add_argument("--min_volume", type=_optional_float, default=200, help="最低平均出来高 (千株単位)")
    p.add_argument("--min_market_cap", type=_optional_float, default=5, help="最低時価総額 ($B 単位)")
    p.add_argument("--position_size", type=float, default=10.0, help="ポジションサイズ (総資産に対する%%比率)")
    p.add_argument("--margin_ratio", type=float, default=1.5, help="最大総ポジション額の倍率制限")
    p.add_argument("--pre_change", type=_optional_float, default=0.0, help="決算前30日間の価格変化率下限 (%%)")
    p.add_argument("--min_perf1h", type=_optional_float, default=-10.0, help="Performance (1 Hour) の下限 (%%)")
    p.add_argument("--sp500_only", action="store_true", help="S&P500 採用銘柄のみ対象")
    p.add_argument("--debug", action="store_true", help="フィルタリング過程のデバッグ情報を表示")
    p.add_argument("--max_trades_per_day", type=int, default=5,
                   help="一日あたりの最大トレード銘柄数 (Noneや0で制限なし)")
    
    # XGBoost分析で重要と判明した追加パラメータ
    p.add_argument("--max_ps_ratio", type=float, default=None, help="最大 P/S 比率")
    p.add_argument("--max_pe_ratio", type=float, default=None, help="最大 P/E 比率")
    p.add_argument("--min_profit_margin", type=float, default=None, help="最低利益率 (%%)")
    p.add_argument("--min_roa", type=float, default=None, help="最低 ROA (%%)")
    p.add_argument("--max_volatility_week", type=float, default=None, help="最大週次ボラティリティ (%%)")
    p.add_argument("--min_perf_week", type=float, default=None, help="最低週次パフォーマンス (%%)")
    # 追加: 除外用の上限しきい値
    p.add_argument("--max_perf_week", type=float, default=None, help="最大週次パフォーマンス (%%)")
    p.add_argument("--max_perf_month", type=float, default=None, help="最大月次パフォーマンス (%%)")
    p.add_argument("--max_rsi14", type=float, default=None, help="最大 RSI(14)")
    p.add_argument("--max_pb_ratio", type=float, default=None, help="最大 P/B 比率")
    
    # パフォーマンス改善パラメータ
    p.add_argument("--stop_loss", type=float, default=6.0, help="ストップロス率 (%%)")

    return p.parse_args()


# -----------------------------------------------------------------------------
# メイン
# -----------------------------------------------------------------------------

def main():
    args = parse_args()
    try:
        _run(args)
    except FinvizCsvError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(2)


def _run(args):
    # バックテスト本体は重い依存 (plotly 等) を持つため、ここで遅延 import する
    from src.main import EarningsBacktest
    from src.config import BacktestConfig
    from src.data_fetcher import DataFetcher

    # ---------------------- データ読み込み & フィルタ ----------------------
    df_raw = add_csv_line_numbers(pd.read_csv(args.aggregated_csv))
    df_raw.columns = df_raw.columns.str.strip()
    print(f"[INFO] 読み込み行数: {len(df_raw)}")

    # 日付範囲フィルタ
    missing = [c for c in ALWAYS_REQUIRED if c not in df_raw.columns]
    if missing:
        raise FinvizCsvError(f"CSV に必須列がありません: {missing}")
    df_raw["Trade Date"] = pd.to_datetime(df_raw["Trade Date"])
    start_dt = pd.to_datetime(args.start_date)
    end_dt   = pd.to_datetime(args.end_date)
    df_raw = df_raw[(df_raw["Trade Date"] >= start_dt) & (df_raw["Trade Date"] <= end_dt)].reset_index(drop=True)
    print(f"[INFO] 期間フィルタ後行数: {len(df_raw)}")

    df_filtered = filter_dataframe(
        df_raw,
        min_eps=args.min_eps,
        min_price=args.min_price,
        max_gap=args.max_gap,
        min_volume=args.min_volume,
        min_market_cap_b=args.min_market_cap,
        pre_change=args.pre_change,
        min_perf1h=args.min_perf1h,
        max_ps_ratio=args.max_ps_ratio,
        max_pe_ratio=args.max_pe_ratio,
        min_profit_margin=args.min_profit_margin,
        min_roa=args.min_roa,
        max_volatility_week=args.max_volatility_week,
        min_perf_week=args.min_perf_week,
        max_perf_week=args.max_perf_week,
        max_perf_month=args.max_perf_month,
        max_rsi14=args.max_rsi14,
        max_pb_ratio=args.max_pb_ratio,
        max_trades_per_day=args.max_trades_per_day,
        debug=args.debug,
    )
    # S&P500 フィルタ (オプション)
    if args.sp500_only:
        before = len(df_filtered)
        sp500_set = set(DataFetcher().get_sp500_symbols())
        if "Index" in df_filtered.columns:
            mask_index = df_filtered["Index"].str.contains("S&P 500", na=False)
            mask_now   = df_filtered["Ticker"].isin(sp500_set)
            df_filtered = df_filtered[mask_index | mask_now].reset_index(drop=True)
        else:
            df_filtered = df_filtered[df_filtered["Ticker"].isin(sp500_set)].reset_index(drop=True)
        print(f"[INFO] S&P500 フィルタ: {len(df_filtered)}/{before} 通過")

    print(f"[INFO] フィルタ通過行数: {len(df_filtered)} (通過率 {len(df_filtered)/len(df_raw)*100:.1f}%)")

    if df_filtered.empty:
        print("[WARN] フィルタ条件を満たす行がありません。バックテストをスキップします。")
        return

    candidates = build_candidates_from_csv(df_filtered)
    symbols = {c["code"] for c in candidates}

    # ---------------------- BacktestConfig & Backtest 実行 ----------------------
    config = BacktestConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        target_symbols=symbols,
        # 無効 (None) にしたフィルタは、設定の記録上は制限なしとして渡す
        max_gap_percent=math.inf if args.max_gap is None else args.max_gap,
        screener_price_min=0.0 if args.min_price is None else args.min_price,
        min_market_cap=0.0 if args.min_market_cap is None else args.min_market_cap * 1e9,
        position_size=args.position_size,
        margin_ratio=args.margin_ratio,
        pre_earnings_change=-math.inf if args.pre_change is None else args.pre_change,
        sp500_only=args.sp500_only,
        stop_loss=args.stop_loss,
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