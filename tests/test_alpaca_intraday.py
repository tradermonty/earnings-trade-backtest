"""Quick test script to verify Alpaca intraday data access

Example:
    python scripts/test_alpaca_intraday.py --symbol DKS --date 2024-09-05 --time 09:25:00 --account paper

Environment:
    ALPACA_API_KEY_PAPER / ALPACA_SECRET_KEY_PAPER or live equivalents must be set.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

# Allow "src" to be importable when running from project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.alpaca_data_fetcher import AlpacaDataFetcher  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(description="Alpaca intraday data sanity test")
    p.add_argument("--symbol", required=True, help="Ticker symbol e.g. AAPL")
    p.add_argument("--date", required=True, help="Trade date YYYY-MM-DD (ET)")
    p.add_argument("--time", default="09:25:00", help="Target time HH:MM:SS ET (default 09:25:00)")
    p.add_argument("--account", choices=["live", "paper"], default="paper", help="Alpaca account type")
    return p.parse_args()


def main():
    args = parse_args()

    fetcher = AlpacaDataFetcher(account_type=args.account)
    price = fetcher.get_preopen_price(args.symbol, args.date, pre_open_time=args.time)

    if price is None:
        print(f"❌  No bar found for {args.symbol} {args.date} {args.time} ET")
    else:
        print(f"✅  {args.symbol} {args.date} {args.time} open price: {price}")


if __name__ == "__main__":
    main()
