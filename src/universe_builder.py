"""
Shared stock universe construction.

Both the backtest engine (src/main.py) and the daily screener
(scripts/screen_daily_candidates.py) call build_target_universe()
to get the same pre-filtered symbol set from the FMP Stock Screener API.

NOTE: The screener uses a *current-day snapshot* of prices, volumes,
and market caps.  In backtest_mode, the screener criteria are relaxed
(price >= $10, mcap >= $1B) to cast a wider net, and DataFilter
performs point-in-time verification using historical price and
market cap data at the actual trade date.

Known limitations:
- Volume filtering is done downstream by DataFilter._check_final_conditions()
  with a hardcoded 200,000 threshold, not at the screener stage.
"""

import logging
from typing import Optional, Set, List, Tuple

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
    backtest_mode: bool = False,
    exchanges: Optional[List[str]] = None,
) -> Tuple[Optional[Set[str]], str]:
    """Build the target symbol universe.

    Returns (symbols, source_label):
      - symbols: set of ticker symbols, or None if no symbols found
      - source_label: which path was taken (authoritative, not re-derived)

    Source labels:
      'sp500'               — S&P 500 constituents
      'mid_small'           — mid/small cap via FMP screener
      'fmp_screener'        — FMP stock_screener (success or empty result)
      'fmp_screener_failed' — FMP stock_screener attempted but exception
      'none'                — no screener path applicable
    """
    symbols: Set[str] = set()

    if sp500_only:
        sp500 = data_fetcher.get_sp500_symbols()
        if sp500:
            symbols.update(sp500)
        return (symbols if symbols else None, 'sp500')

    elif mid_small_only:
        mid_small = data_fetcher.get_mid_small_symbols(
            min_market_cap=min_market_cap,
            max_market_cap=max_market_cap,
        )
        if mid_small:
            symbols.update(mid_small)
        return (symbols if symbols else None, 'mid_small')

    elif data_fetcher.has_fmp_screener:
        exchanges = exchanges or DEFAULT_EXCHANGES
        # In backtest mode, use relaxed criteria to cast a wider net.
        # Point-in-time verification happens in DataFilter using historical data.
        effective_price = 10.0 if backtest_mode else screener_price_min
        effective_mcap = 1e9 if backtest_mode else min_market_cap
        if backtest_mode:
            logger.info(
                "Backtest mode: relaxed screener (price>=$%.0f, mcap>=$%.0fB)",
                effective_price, effective_mcap / 1e9,
            )
        try:
            total = 0
            effective_max = (
                max_market_cap
                if max_market_cap and max_market_cap < 1e12
                else None
            )
            for ex in exchanges:
                lst = data_fetcher.fmp_fetcher.stock_screener(
                    price_more_than=effective_price,
                    market_cap_more_than=effective_mcap,
                    market_cap_less_than=effective_max,
                    limit=10000,
                    exchange=ex,
                )
                if lst:
                    logger.info("  %s: %d symbols", ex, len(lst))
                    symbols.update(lst)
                    total += len(lst)
            logger.info(
                "FMPスクリーナー合計取得数: %d (重複除外後 %d)",
                total, len(symbols),
            )
            return (symbols if symbols else None, 'fmp_screener')
        except Exception as e:
            logger.error("FMPスクリーナー取得失敗: %s", e)
            return (None, 'fmp_screener_failed')

    return (None, 'none')
