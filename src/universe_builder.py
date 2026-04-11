"""
Shared stock universe construction.

Both the backtest engine (src/main.py) and the daily screener
(scripts/screen_daily_candidates.py) call build_target_universe()
to get the same pre-filtered symbol set from the FMP Stock Screener API.

NOTE: The screener uses a *current-day snapshot* of prices, volumes,
and market caps.  For historical backtests this means the universe
reflects today's fundamentals, not point-in-time values.

Known limitations:
- screener_volume_min is accepted for interface compatibility but
  fmp_data_fetcher.stock_screener() intentionally ignores it.
  Volume filtering is done downstream by DataFilter._check_final_conditions()
  with a hardcoded 200,000 threshold.
"""

import logging
from typing import Optional, Set, List

from .data_fetcher import DataFetcher

logger = logging.getLogger(__name__)

DEFAULT_EXCHANGES: List[str] = ['NYSE', 'NASDAQ', 'AMEX']


def build_target_universe(
    data_fetcher: DataFetcher,
    *,
    sp500_only: bool = False,
    mid_small_only: bool = False,
    min_market_cap: float = 5e9,
    max_market_cap: float = 0,
    screener_price_min: float = 30.0,
    screener_volume_min: int = 200_000,
    exchanges: Optional[List[str]] = None,
) -> Optional[Set[str]]:
    """Build the target symbol universe.

    Returns a set of ticker symbols, or None when the universe
    could not be determined (callers should treat None as "all symbols"
    in backtest mode, or abort in screener mode).

    Three mutually-exclusive modes, checked in priority order:
      1. sp500_only     -- S&P 500 constituents
      2. mid_small_only -- mid/small cap via FMP screener
      3. (default)      -- FMP stock_screener with price/cap filters
    """
    symbols: Set[str] = set()

    if sp500_only:
        sp500 = data_fetcher.get_sp500_symbols()
        if sp500:
            symbols.update(sp500)

    elif mid_small_only:
        mid_small = data_fetcher.get_mid_small_symbols(
            min_market_cap=min_market_cap,
            max_market_cap=max_market_cap,
        )
        if mid_small:
            symbols.update(mid_small)

    elif getattr(data_fetcher, 'fmp_fetcher', None):
        exchanges = exchanges or DEFAULT_EXCHANGES
        try:
            total = 0
            effective_max = (
                max_market_cap
                if max_market_cap and max_market_cap < 1e12
                else None
            )
            for ex in exchanges:
                lst = data_fetcher.fmp_fetcher.stock_screener(
                    price_more_than=screener_price_min,
                    market_cap_more_than=min_market_cap,
                    market_cap_less_than=effective_max,
                    volume_more_than=screener_volume_min,
                    limit=10000,
                    exchange=ex,
                )
                if lst:
                    print(f"  {ex}: {len(lst)} symbols")
                    symbols.update(lst)
                    total += len(lst)
            print(
                f"FMPスクリーナー合計取得数: {total} "
                f"(重複除外後 {len(symbols)})"
            )
        except Exception as e:
            logger.error(f"FMPスクリーナー取得失敗: {e}")
            print(f"FMPスクリーナー取得失敗: {e}")

    return symbols if symbols else None
