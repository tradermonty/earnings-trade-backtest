#!/usr/bin/env python3
"""
Daily Candidates Screener Script
日次エントリー候補スクリーナー

Usage:
    python scripts/screen_daily_candidates.py --date 2024-06-15
    python scripts/screen_daily_candidates.py  # Uses today's NY date

Output:
    ./reports/screener/daily_candidates_YYYY-MM-DD.csv
"""

import argparse
import os
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional

import pandas as pd

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'src'))

from src.config import BacktestConfig
from src.data_fetcher import DataFetcher
from src.data_filter import DataFilter


def get_default_date() -> str:
    """Get today's date in NY timezone (EST/EDT)"""
    try:
        from zoneinfo import ZoneInfo
        ny_tz = ZoneInfo('America/New_York')
        return datetime.now(ny_tz).strftime('%Y-%m-%d')
    except ImportError:
        # Fallback for Python < 3.9
        return datetime.now().strftime('%Y-%m-%d')


def validate_date(date_str: str) -> str:
    """Validate date format"""
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return date_str
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Screen daily entry candidates based on earnings surprise',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument('--date', type=str, default=None,
                        help='Target date (YYYY-MM-DD). Defaults to NY timezone today.')

    # Screening parameters
    parser.add_argument('--min_surprise', type=float, default=5.0,
                        help='Minimum EPS surprise percentage')
    parser.add_argument('--max_gap', type=float, default=10.0,
                        help='Maximum opening gap percentage')
    parser.add_argument('--min_price', type=float, default=30.0,
                        help='Minimum stock price')
    parser.add_argument('--min_market_cap', type=float, default=5.0,
                        help='Minimum market cap in billions')
    parser.add_argument('--min_volume', type=int, default=200000,
                        help='Minimum 20-day average volume')

    # Output options
    parser.add_argument('--output_dir', type=str,
                        default='./reports/screener',
                        help='Output directory for CSV files')
    parser.add_argument('--verbose', action='store_true',
                        help='Show detailed output')

    return parser.parse_args()


def ensure_output_directory(dir_path: str) -> None:
    """Ensure output directory exists, create if not"""
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)


def get_output_filename(date_str: str) -> str:
    """Get output filename for given date"""
    return f'daily_candidates_{date_str}.csv'


def calculate_candidate_score(candidate: Dict[str, Any]) -> float:
    """
    Calculate candidate quality score.
    Higher score = better quality candidate.

    Score components:
    - EPS surprise (weight: 40%)
    - Gap percentage (weight: 30%) - moderate gap is better
    - Pre-earnings momentum (weight: 30%)
    """
    score = 0.0

    # EPS surprise contribution (0-40 points)
    eps_surprise = candidate.get('eps_surprise_percent', 0)
    if eps_surprise > 0:
        # Cap at 50% surprise for scoring purposes
        capped_surprise = min(eps_surprise, 50)
        score += (capped_surprise / 50) * 40

    # Gap contribution (0-30 points)
    # Ideal gap is 3-7%, too small or too large is less desirable
    gap = candidate.get('gap_percent', 0)
    if 3 <= gap <= 7:
        score += 30
    elif 1 <= gap < 3:
        score += 20
    elif 7 < gap <= 10:
        score += 20
    elif 0 < gap < 1:
        score += 10

    # Pre-earnings momentum (0-30 points)
    pre_change = candidate.get('pre_earnings_change', 0)
    if pre_change > 0:
        # Positive pre-earnings trend is good, cap at 20%
        capped_pre = min(pre_change, 20)
        score += (capped_pre / 20) * 30

    return round(score, 1)


def screen_candidates(date_str: str, args) -> List[Dict[str, Any]]:
    """
    Screen for entry candidates on given date.
    Uses only data available BEFORE the screen date to avoid look-ahead bias.
    """
    print(f"Screening candidates for {date_str}...")

    # Initialize data fetcher
    data_fetcher = DataFetcher(use_fmp=True)

    # Get earnings data for the target date
    # We look at stocks that reported earnings on the previous trading day
    earnings_data = data_fetcher.get_earnings_data(
        start_date=date_str,
        end_date=date_str,
        target_symbols=None  # All symbols
    )

    if not earnings_data:
        print(f"No earnings data found for {date_str}")
        return []

    print(f"Found {len(earnings_data)} earnings reports on {date_str}")

    # Create config for filtering
    config = BacktestConfig(
        start_date=date_str,
        end_date=date_str,
        min_surprise_percent=args.min_surprise,
        max_gap_percent=args.max_gap,
        screener_price_min=args.min_price,
        min_market_cap=args.min_market_cap * 1e9,
        screener_volume_min=args.min_volume,
    )

    # Initialize data filter
    data_filter = DataFilter(
        data_fetcher=data_fetcher,
        target_symbols=None,
        min_surprise_percent=config.min_surprise_percent,
        pre_earnings_change=config.pre_earnings_change,
        max_holding_days=config.max_holding_days,
        max_gap_percent=config.max_gap_percent,
    )

    # Filter candidates
    filtered_candidates = data_filter.filter_earnings_data(earnings_data)
    print(f"After filtering: {len(filtered_candidates)} candidates")

    # Build candidate list with scores
    # Note: DataFilter returns data with keys: code, gap, percent, prev_close, entry_price, etc.
    candidates = []
    for item in filtered_candidates:
        candidate = {
            'date': item.get('trade_date', date_str),
            'symbol': item.get('code', ''),
            'eps_surprise_percent': item.get('percent', 0),
            'gap_percent': item.get('gap', 0),
            'pre_earnings_change': item.get('pre_change', 0),
            'sector': item.get('sector', ''),
            'market_cap': item.get('market_cap', 0),
            'volume_20d_avg': item.get('avg_volume', 0),
            'actual_eps': item.get('actual', 0),
            'estimate_eps': item.get('estimate', 0),
            'prev_close': item.get('prev_close', 0),
            'entry_price': item.get('entry_price', 0),
        }
        candidate['score'] = calculate_candidate_score(candidate)
        candidates.append(candidate)

    # Sort by score descending
    candidates.sort(key=lambda x: x['score'], reverse=True)

    return candidates


def save_candidates_to_csv(candidates: List[Dict[str, Any]], output_path: str) -> None:
    """Save candidates to CSV file"""
    if not candidates:
        # Create empty CSV with headers
        columns = ['date', 'symbol', 'score', 'sector', 'gap_percent',
                   'eps_surprise_percent', 'pre_earnings_change', 'market_cap',
                   'volume_20d_avg', 'actual_eps', 'estimate_eps', 'prev_close', 'entry_price']
        df = pd.DataFrame(columns=columns)
    else:
        df = pd.DataFrame(candidates)
        # Reorder columns
        column_order = ['date', 'symbol', 'score', 'sector', 'gap_percent',
                       'eps_surprise_percent', 'pre_earnings_change', 'market_cap',
                       'volume_20d_avg', 'actual_eps', 'estimate_eps', 'prev_close', 'entry_price']
        # Only include columns that exist
        df = df[[col for col in column_order if col in df.columns]]

    df.to_csv(output_path, index=False)


def main():
    """Main entry point"""
    args = parse_arguments()

    # Determine target date
    if args.date:
        target_date = validate_date(args.date)
    else:
        target_date = get_default_date()

    print(f"=== Daily Candidates Screener ===")
    print(f"Target Date: {target_date}")
    print(f"Parameters:")
    print(f"  Min EPS Surprise: {args.min_surprise}%")
    print(f"  Max Gap: {args.max_gap}%")
    print(f"  Min Price: ${args.min_price}")
    print(f"  Min Market Cap: ${args.min_market_cap}B")
    print("-" * 40)

    # Ensure output directory exists
    ensure_output_directory(args.output_dir)

    # Screen candidates
    candidates = screen_candidates(target_date, args)

    # Generate output path
    output_filename = get_output_filename(target_date)
    output_path = os.path.join(args.output_dir, output_filename)

    # Save to CSV
    save_candidates_to_csv(candidates, output_path)

    print(f"\n=== Results ===")
    print(f"Total candidates: {len(candidates)}")
    print(f"Output saved to: {output_path}")

    if candidates and args.verbose:
        print(f"\nTop 10 candidates:")
        for i, c in enumerate(candidates[:10], 1):
            print(f"  {i}. {c['symbol']}: Score={c['score']}, "
                  f"Surprise={c['eps_surprise_percent']:.1f}%, "
                  f"Gap={c['gap_percent']:.1f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
