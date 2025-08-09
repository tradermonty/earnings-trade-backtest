"""Quick sanity check for FMP stock_screener() fundamental filters.

Usage:
    python scripts/test_screener_filter.py \
        --price_min 30 --cap_min 5 --ps 10 --pe 75 --npm 3

Requires:
    • FMP Premium API KEY set in environment variable `FMP_API_KEY`
    • src.fmp_data_fetcher.FMPDataFetcher is importable (project root)

What it does:
    1. 呼び出し① 価格・時価総額のみ（ファンダメンタル無）
    2. 呼び出し② 価格・時価総額 + PS / PE / NetProfitMargin 条件
    3. 取得件数と重複・差分を表示

This is **not** part of production; just a troubleshooting helper.
"""

import argparse
import os
import sys
from pathlib import Path

# Optional: load .env if present
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except ImportError:
    # dotenv is optional; fallback to env vars only
    pass

# Allow `src` to be importable when executed from project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.fmp_data_fetcher import FMPDataFetcher  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(description="Test FMP stock_screener fundamental filters")
    p.add_argument("--price_min", type=float, default=30, help="priceMoreThan")
    p.add_argument("--cap_min", type=float, default=5, help="min market cap in billions USD")
    p.add_argument("--ps", type=float, default=None, help="max P/S ratio")
    p.add_argument("--pe", type=float, default=None, help="max P/E ratio")
    p.add_argument("--npm", type=float, default=None, help="min net profit margin (%)")
    p.add_argument("--limit", type=int, default=5000)
    return p.parse_args()


def main():
    args = parse_args()

    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        print("❌  Set FMP_API_KEY in environment variables (Premium key)")
        sys.exit(1)

    fetcher = FMPDataFetcher(api_key=api_key)

    base_symbols = fetcher.stock_screener(
        price_more_than=args.price_min,
        market_cap_more_than=args.cap_min * 1e9,
        limit=args.limit,
        # fundamental filters disabled
    )
    print(f"[BASE] symbols without fundamental filters: {len(base_symbols)}")

    # Financial Ratios フィルタリング
    filt_symbols = []
    skipped = 0
    for sym in base_symbols:
        ratios = fetcher.get_latest_financial_ratios(sym)
        if ratios is None:
            skipped += 1
            continue
        ps = ratios.get('priceToSalesRatio')
        pe = ratios.get('priceToEarningsRatio')
        npm = ratios.get('netProfitMargin')
        npm_pct = npm * 100 if npm is not None else None
        cond = True
        if args.ps is not None and (ps is None or ps > args.ps):
            cond = False
        if args.pe is not None and (pe is None or pe > args.pe):
            cond = False
        if args.npm is not None and (npm_pct is None or npm_pct < args.npm):
            cond = False
        if cond:
            filt_symbols.append(sym)

    print(f"[FILTER] symbols with fundamental filters: {len(filt_symbols)} (skipped {skipped})")

    missing = set(base_symbols) - set(filt_symbols)
    print(f"Symbols removed by filters: {len(missing)} (show up to 20): {sorted(list(missing))[:20]}")

    if len(base_symbols) == len(filt_symbols):
        print("⚠️  Filter did NOT reduce the universe. Please double-check ratios.")
    else:
        print("✅  Filter is reducing universe as expected.")


if __name__ == "__main__":
    main()
