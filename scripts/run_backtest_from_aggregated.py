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
from src.data_fetcher import DataFetcher  # noqa: E402

# -----------------------------------------------------------------------------
# ヘルパー
# -----------------------------------------------------------------------------

import re


from typing import Optional


def _to_float(val: Any) -> Optional[float]:
    """数値を含む文字列を float に変換。変換不可の場合は None を返す"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        s = str(val).strip()
        # % や $ 、カンマを除去
        s = re.sub(r"[%,\$]", "", s)
        if s == "":
            return None
        return float(s)
    except Exception:
        return None


def _parse_market_cap(text: str | float | int | None) -> Optional[float]:
    """文字列の Market Cap ('12.3B', '450M' etc.) をドル単位の float に変換"""
    if text is None:
        return None
    try:
        s = str(text).strip().upper().replace("$", "")
        if s.endswith("B"):
            return float(s[:-1]) * 1e9
        if s.endswith("M"):
            return float(s[:-1]) * 1e6
        if s.endswith("K"):
            return float(s[:-1]) * 1e3
        # 接尾辞なし = Finviz million 単位とみなす
        return float(s) * 1e6
    except Exception:
        return None


def filter_dataframe(df: pd.DataFrame, *, min_eps: float = 5.0, min_price: float = 10.0,
                      max_gap: float = 10.0, min_volume: int = 200_000,
                      min_market_cap_b: float | None = None,
                      pre_change: float = 0.0,
                      min_perf1h: float = 0.0,
                      max_ps_ratio: float | None = None,
                      max_pe_ratio: float | None = None,
                      min_profit_margin: float | None = None,
                      min_roa: float | None = None,
                      max_volatility_week: float | None = None,
                      min_perf_week: float | None = None,
                      max_pb_ratio: float | None = None,
                      debug: bool = False) -> pd.DataFrame:
    """aggregated_screen.csv の DataFrame に対して DataFilter 相当の条件で絞り込みを行う"""
    # 必要な列の標準化
    df = df.copy()
    df.columns = df.columns.str.strip()

    # EPS Surprise
    if "EPS Surprise" in df.columns:
        def _eps_transform(x):
            v = _to_float(x)
            if v is None:
                return 0.0
            # Finviz は 0.1234 = 12.34% の形式。|v|<1 の場合パーセントに換算
            return v * 100 if abs(v) < 1 else v
        df["_eps"] = df["EPS Surprise"].apply(_eps_transform)
    else:
        df["_eps"] = 0.0

    # Price (Open/Close などがあり得る)
    price_col = None
    for col in ["Price", "Open", "Close", "Entry Price", "Entry"]:
        if col in df.columns:
            price_col = col
            break
    if price_col:
        df["_price"] = df[price_col].apply(_to_float)
    else:
        df["_price"] = None

    # Gap (Finviz: 0.0218 = 2.18%)
    _percent_transform = lambda x: (lambda v: (v*100 if abs(v)<1 else v) if v is not None else None)(_to_float(x))
    if "Gap" in df.columns:
        df["_gap"] = df["Gap"].apply(_percent_transform)
    else:
        df["_gap"] = None

    # Performance (Month) & Change
    if "Performance (Month)" in df.columns:
        df["_perf_m"] = df["Performance (Month)"].apply(_percent_transform).fillna(0)
    else:
        df["_perf_m"] = 0.0
    if "Change" in df.columns:
        df["_change"] = df["Change"].apply(_percent_transform).fillna(0)
    else:
        df["_change"] = 0.0
    import numpy as np
    df["_pre_change"] = np.where(df["_perf_m"].notna() & df["_change"].notna(), df["_perf_m"] - df["_change"], np.nan)

    # Performance (1 Hour)
    if "Performance (1 Hour)" in df.columns:
        df["_perf1h"] = df["Performance (1 Hour)"].apply(_percent_transform).fillna(0)
    else:
        df["_perf1h"] = 0.0

    # Market Cap
    if "Market Cap" in df.columns:
        df["_mcap"] = df["Market Cap"].apply(_parse_market_cap)
    else:
        df["_mcap"] = None

    # Avg Volume
    vol_col = None
    for col in ["Avg Vol", "Avg Vol (3 month)", "Average Volume", "Volume"]:
        if col in df.columns:
            vol_col = col
            break
    if vol_col:
        df["_vol"] = df[vol_col].apply(_to_float) * 1_000
    else:
        df["_vol"] = None

    # XGBoost分析で重要と判明した追加パラメーター
    # P/S Ratio
    if "P/S" in df.columns:
        df["_ps"] = df["P/S"].apply(_to_float)
    else:
        df["_ps"] = None
    
    # P/E Ratio
    if "P/E" in df.columns:
        df["_pe"] = df["P/E"].apply(_to_float)
    else:
        df["_pe"] = None
    
    # Profit Margin
    if "Profit Margin" in df.columns:
        df["_profit_margin"] = df["Profit Margin"].apply(_percent_transform)
    else:
        df["_profit_margin"] = None
    
    # Return on Assets (ROA)
    if "Return on Assets" in df.columns:
        df["_roa"] = df["Return on Assets"].apply(_percent_transform)
    else:
        df["_roa"] = None
    
    # Volatility (Week)
    if "Volatility (Week)" in df.columns:
        df["_vol_week"] = df["Volatility (Week)"].apply(_percent_transform)
    else:
        df["_vol_week"] = None
    
    # Performance (Week)
    if "Performance (Week)" in df.columns:
        df["_perf_week"] = df["Performance (Week)"].apply(_percent_transform)
    else:
        df["_perf_week"] = None
    
    # P/B Ratio
    if "P/B" in df.columns:
        df["_pb"] = df["P/B"].apply(_to_float)
    else:
        df["_pb"] = None

    # --- 各条件を個別に評価 ---
    cond_eps = df["_eps"] >= min_eps
    cond_price = (df["_price"].isna()) | (df["_price"] >= min_price)
    cond_vol = (df["_vol"].isna()) | (df["_vol"] >= min_volume * 1_000)
    cond_gap = (df["_gap"].isna()) | ((df["_gap"] >= 0) & (df["_gap"] <= max_gap))
    cond_pre = (df["_pre_change"].isna()) | (df["_pre_change"] >= pre_change)
    cond_perf1h = (df["_perf1h"].isna()) | (df["_perf1h"] >= min_perf1h)
    cond_mcap = (min_market_cap_b is None) | (df["_mcap"].isna()) | (df["_mcap"] >= min_market_cap_b * 1e9)
    
    # 新しい条件（XGBoostで重要と判明）
    cond_ps = (max_ps_ratio is None) | (df["_ps"].isna()) | (df["_ps"] <= max_ps_ratio)
    cond_pe = (max_pe_ratio is None) | (df["_pe"].isna()) | (df["_pe"] <= max_pe_ratio)
    cond_profit = (min_profit_margin is None) | (df["_profit_margin"].isna()) | (df["_profit_margin"] >= min_profit_margin)
    cond_roa = (min_roa is None) | (df["_roa"].isna()) | (df["_roa"] >= min_roa)
    cond_vol_w = (max_volatility_week is None) | (df["_vol_week"].isna()) | (df["_vol_week"] <= max_volatility_week)
    cond_perf_w = (min_perf_week is None) | (df["_perf_week"].isna()) | (df["_perf_week"] >= min_perf_week)
    cond_pb = (max_pb_ratio is None) | (df["_pb"].isna()) | (df["_pb"] <= max_pb_ratio)

    if debug:
        total = len(df)
        print("[DEBUG] 条件別通過数:")
        print(f"  EPS >= {min_eps}%          : {cond_eps.sum()}/{total}")
        print(f"  Price >= ${min_price}       : {cond_price.sum()}/{total}")
        print(f"  Volume >= {min_volume}K     : {cond_vol.sum()}/{total}")
        print(f"  0<=Gap<={max_gap}%          : {cond_gap.sum()}/{total}")
        print(f"  Pre Change >= {pre_change}%   : {cond_pre.sum()}/{total}")
        print(f"  Perf 1H >= {min_perf1h}%      : {cond_perf1h.sum()}/{total}")
        if min_market_cap_b is not None:
            print(f"  MktCap >= {min_market_cap_b}B : {cond_mcap.sum()}/{total}")
        # 新条件のデバッグ出力
        if max_ps_ratio is not None:
            print(f"  P/S <= {max_ps_ratio}         : {cond_ps.sum()}/{total}")
        if max_pe_ratio is not None:
            print(f"  P/E <= {max_pe_ratio}         : {cond_pe.sum()}/{total}")
        if min_profit_margin is not None:
            print(f"  Profit Margin >= {min_profit_margin}% : {cond_profit.sum()}/{total}")
        if min_roa is not None:
            print(f"  ROA >= {min_roa}%             : {cond_roa.sum()}/{total}")
        if max_volatility_week is not None:
            print(f"  Vol(Week) <= {max_volatility_week}% : {cond_vol_w.sum()}/{total}")
        if min_perf_week is not None:
            print(f"  Perf(Week) >= {min_perf_week}% : {cond_perf_w.sum()}/{total}")
        if max_pb_ratio is not None:
            print(f"  P/B <= {max_pb_ratio}         : {cond_pb.sum()}/{total}")

    cond = cond_eps & cond_price & cond_vol & cond_gap & cond_pre & cond_perf1h & cond_mcap & \
           cond_ps & cond_pe & cond_profit & cond_roa & cond_vol_w & cond_perf_w & cond_pb

    filtered = df[cond].reset_index(drop=True)

    # 日付ごとに EPS サプライズ上位5銘柄を選択
    if "Trade Date" in filtered.columns:
        before_n = len(filtered)
        filtered = (
            filtered.sort_values("_eps", ascending=False)
                    .groupby("Trade Date", as_index=False, group_keys=False)
                    .head(5)
                    .reset_index(drop=True)
        )
        if debug:
            print(f"[DEBUG] 日付ごと上位5抽出: {len(filtered)}/{before_n}")

    return filtered


def build_candidates_from_csv(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """集約 CSV から TradeExecutor 向け candidate dict を生成 (フィルタ後 DF を想定)"""
    required_cols = {"Trade Date", "Ticker"}
    if not required_cols.issubset(df.columns):
        raise ValueError(f"CSV must include columns: {required_cols}")

    candidates: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        trade_date = str(row["Trade Date"]).split(" ")[0]
        symbol = str(row["Ticker"]).strip()
        if not symbol:
            continue
        # EPS Surprise (%). 変換済みの _eps 列があれば優先
        if "_eps" in row and not pd.isna(row["_eps"]):
            percent = float(row["_eps"])
        else:
            percent = _to_float(row.get("EPS Surprise")) or 0.0
            if percent < 1:  # Finviz CSV は小数表記(0.12)の場合がある
                percent *= 100
        # エントリー価格は TradeExecutor 内で当日の寄付(Open)を使用させる
        price = None
        # Gap は Finviz の値をそのまま利用（Open と prevClose の％差）
        gap = _to_float(row.get("Gap"))
        candidates.append({
            "code": symbol,
            "trade_date": trade_date,
            "report_date": trade_date,  # 便宜上同じ
            "price": price,
            "gap": gap,
            "percent": percent,
        })
    return candidates

# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Aggregated CSV からバックテストを実行し、フィルタ条件を適用する",
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("aggregated_csv", type=Path, help="aggregated_screen.csv のパス")
    p.add_argument("--start_date", type=str, required=True, help="バックテスト開始日 (YYYY-MM-DD)")
    p.add_argument("--end_date", type=str, required=True, help="バックテスト終了日 (YYYY-MM-DD)")
    p.add_argument("--output", type=Path, default=Path("aggregated_backtest_results.json"), help="結果 JSON の出力先")

    # フィルタパラメータ (DataFilter 相当)
    p.add_argument("--min_eps", type=float, default=5, help="最低 EPS サプライズ率 (%)")
    p.add_argument("--min_price", type=float, default=30.0, help="最低株価 ($)")
    p.add_argument("--max_gap", type=float, default=10.0, help="最大ギャップ率 (%)")
    p.add_argument("--min_volume", type=int, default=200, help="最低平均出来高 (千株単位)")
    p.add_argument("--min_market_cap", type=float, default=5, help="最低時価総額 ($B 単位)")
    p.add_argument("--position_size", type=float, default=10.0, help="ポジションサイズ (総資産に対する%比率)")
    p.add_argument("--margin_ratio", type=float, default=1.5, help="最大総ポジション額の倍率制限")
    p.add_argument("--pre_change", type=float, default=0.0, help="決算前30日間の価格変化率下限 (%)")
    p.add_argument("--min_perf1h", type=float, default=-10.0, help="Performance (1 Hour) の下限 (%)")
    p.add_argument("--sp500_only", action="store_true", help="S&P500 採用銘柄のみ対象")
    p.add_argument("--debug", action="store_true", help="フィルタリング過程のデバッグ情報を表示")
    
    # XGBoost分析で重要と判明した追加パラメータ
    p.add_argument("--max_ps_ratio", type=float, default=None, help="最大 P/S 比率")
    p.add_argument("--max_pe_ratio", type=float, default=None, help="最大 P/E 比率")
    p.add_argument("--min_profit_margin", type=float, default=None, help="最低利益率 (%)")
    p.add_argument("--min_roa", type=float, default=None, help="最低 ROA (%)")
    p.add_argument("--max_volatility_week", type=float, default=None, help="最大週次ボラティリティ (%)")
    p.add_argument("--min_perf_week", type=float, default=None, help="最低週次パフォーマンス (%)")
    p.add_argument("--max_pb_ratio", type=float, default=None, help="最大 P/B 比率")
    
    # パフォーマンス改善パラメータ
    p.add_argument("--stop_loss", type=float, default=6.0, help="ストップロス率 (%)")

    return p.parse_args()


# -----------------------------------------------------------------------------
# メイン
# -----------------------------------------------------------------------------

def main():
    args = parse_args()

    # ---------------------- データ読み込み & フィルタ ----------------------
    df_raw = pd.read_csv(args.aggregated_csv)
    print(f"[INFO] 読み込み行数: {len(df_raw)}")

    # 日付範囲フィルタ
    if "Trade Date" not in df_raw.columns:
        raise ValueError("CSV に 'Trade Date' 列がありません")
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
        max_pb_ratio=args.max_pb_ratio,
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
        max_gap_percent=args.max_gap,
        screener_price_min=args.min_price,
        screener_volume_min=args.min_volume,
        min_market_cap=args.min_market_cap * 1e9,
        position_size=args.position_size,
        margin_ratio=args.margin_ratio,
        pre_earnings_change=args.pre_change,
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