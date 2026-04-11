"""Tests for src.universe_builder.build_target_universe()"""

import pytest
from unittest.mock import Mock

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.universe_builder import build_target_universe


def _make_data_fetcher(fmp_symbols=None, sp500=None, mid_small=None):
    """Helper to create a mock DataFetcher."""
    df = Mock()
    if fmp_symbols is not None:
        df.fmp_fetcher = Mock()
        df.fmp_fetcher.stock_screener.return_value = fmp_symbols
    else:
        df.fmp_fetcher = None
    df.get_sp500_symbols.return_value = sp500 or []
    df.get_mid_small_symbols.return_value = mid_small or []
    return df


class TestFMPScreenerDefaultPath:

    def test_calls_stock_screener_for_each_exchange(self):
        fetcher = _make_data_fetcher(fmp_symbols=['AAPL', 'MSFT'])
        result = build_target_universe(fetcher)
        assert result is not None
        assert 'AAPL' in result
        assert 'MSFT' in result
        assert fetcher.fmp_fetcher.stock_screener.call_count == 3

    def test_passes_screener_params_correctly(self):
        fetcher = _make_data_fetcher(fmp_symbols=['TEST'])
        build_target_universe(
            fetcher,
            screener_price_min=50.0,
            min_market_cap=10e9,
            screener_volume_min=500_000,
        )
        call_kwargs = fetcher.fmp_fetcher.stock_screener.call_args_list[0].kwargs
        assert call_kwargs['price_more_than'] == 50.0
        assert call_kwargs['market_cap_more_than'] == 10e9
        assert call_kwargs['volume_more_than'] == 500_000

    def test_max_market_cap_passed_when_below_threshold(self):
        fetcher = _make_data_fetcher(fmp_symbols=['X'])
        build_target_universe(fetcher, max_market_cap=50e9)
        call_kwargs = fetcher.fmp_fetcher.stock_screener.call_args_list[0].kwargs
        assert call_kwargs['market_cap_less_than'] == 50e9

    def test_max_market_cap_none_when_zero(self):
        fetcher = _make_data_fetcher(fmp_symbols=['X'])
        build_target_universe(fetcher, max_market_cap=0)
        call_kwargs = fetcher.fmp_fetcher.stock_screener.call_args_list[0].kwargs
        assert call_kwargs['market_cap_less_than'] is None

    def test_deduplicates_across_exchanges(self):
        fetcher = _make_data_fetcher(fmp_symbols=['AAPL'])
        result = build_target_universe(fetcher)
        # stock_screener returns ['AAPL'] 3 times, but set deduplicates
        assert result == {'AAPL'}


class TestSP500OnlyPath:

    def test_returns_sp500_symbols(self):
        fetcher = _make_data_fetcher(sp500=['AAPL', 'GOOG'])
        result = build_target_universe(fetcher, sp500_only=True)
        assert result == {'AAPL', 'GOOG'}

    def test_does_not_call_stock_screener(self):
        fetcher = _make_data_fetcher(fmp_symbols=['X'], sp500=['AAPL'])
        build_target_universe(fetcher, sp500_only=True)
        fetcher.fmp_fetcher.stock_screener.assert_not_called()


class TestMidSmallOnlyPath:

    def test_returns_mid_small_symbols(self):
        fetcher = _make_data_fetcher(mid_small=['SMID1', 'SMID2'])
        result = build_target_universe(fetcher, mid_small_only=True)
        assert result == {'SMID1', 'SMID2'}

    def test_passes_market_cap_params(self):
        fetcher = _make_data_fetcher(mid_small=['X'])
        build_target_universe(
            fetcher, mid_small_only=True,
            min_market_cap=2e9, max_market_cap=10e9,
        )
        fetcher.get_mid_small_symbols.assert_called_once_with(
            min_market_cap=2e9, max_market_cap=10e9,
        )


class TestEdgeCases:

    def test_returns_none_when_no_symbols_found(self):
        fetcher = _make_data_fetcher(fmp_symbols=[])
        result = build_target_universe(fetcher)
        assert result is None

    def test_returns_none_on_fmp_api_exception(self):
        fetcher = _make_data_fetcher(fmp_symbols=['X'])
        fetcher.fmp_fetcher.stock_screener.side_effect = Exception("API down")
        result = build_target_universe(fetcher)
        assert result is None

    def test_returns_none_when_no_fmp_fetcher(self):
        fetcher = _make_data_fetcher()  # fmp_fetcher = None
        result = build_target_universe(fetcher)
        assert result is None

    def test_returns_none_when_sp500_returns_empty(self):
        fetcher = _make_data_fetcher(sp500=[])
        result = build_target_universe(fetcher, sp500_only=True)
        assert result is None
