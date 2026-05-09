"""Phase 5 parity test: filter_utils helpers (look-ahead-safe pre-earnings change and volume).

Asserts:
- None / empty input never raises.
- ``get_prior_bars`` excludes ``trade_date`` whether or not it's in the index.
- ``compute_pre_earnings_change`` preserves the original 19-position distance.
- Insufficient history → None propagation through callers.
- Both DatetimeIndex and 'date'-column variants produce identical results.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.filter_utils import (
    compute_avg_volume_20d,
    compute_pre_earnings_change,
    get_prior_bars,
    normalize_to_date_index,
)


@pytest.fixture
def synthetic_df():
    dates = pd.date_range('2025-01-02', periods=30, freq='B')
    return pd.DataFrame(
        {
            'Close': [100.0 + i for i in range(30)],
            'Volume': [1_000 + i for i in range(30)],
        },
        index=dates,
    )


class TestNoneInputSafety:
    def test_normalize_returns_empty_for_none(self):
        assert normalize_to_date_index(None).empty

    def test_normalize_returns_empty_for_empty_df(self):
        assert normalize_to_date_index(pd.DataFrame()).empty

    def test_get_prior_bars_handles_none(self):
        assert get_prior_bars(None, '2025-01-15').empty

    def test_compute_pre_change_returns_none_for_none(self):
        assert compute_pre_earnings_change(None, '2025-01-15') is None

    def test_compute_avg_volume_returns_none_for_none(self):
        assert compute_avg_volume_20d(None, '2025-01-15') is None


class TestPriorBarsContract:
    def test_excludes_trade_date_when_present(self, synthetic_df):
        td = synthetic_df.index[20].strftime('%Y-%m-%d')
        prior = get_prior_bars(synthetic_df, td)
        assert prior.index.max() < synthetic_df.index[20]
        assert len(prior) == 20

    def test_returns_all_when_trade_date_not_in_index(self, synthetic_df):
        # 2025-12-31 is far past the last bar
        prior = get_prior_bars(synthetic_df, '2025-12-31')
        assert len(prior) == 30


class TestPreEarningsChangeWindow:
    def test_19_position_distance_preserved(self, synthetic_df):
        # Trade date = 21st bar. Prior has 20 bars.
        # iloc[-1] = Close[19] = 119; iloc[-20] = Close[0] = 100; diff = 19
        td = synthetic_df.index[20].strftime('%Y-%m-%d')
        v = compute_pre_earnings_change(synthetic_df, td)
        assert v == pytest.approx(19.0, abs=1e-6)

    def test_insufficient_history_returns_none(self, synthetic_df):
        td = synthetic_df.index[10].strftime('%Y-%m-%d')
        # Only 10 prior bars; need 20
        assert compute_pre_earnings_change(synthetic_df, td) is None

    def test_exactly_20_prior_bars_returns_value(self, synthetic_df):
        # Need 20 prior bars. Bar at index 20 has 20 prior.
        td = synthetic_df.index[20].strftime('%Y-%m-%d')
        v = compute_pre_earnings_change(synthetic_df, td)
        assert v is not None

    def test_19_prior_bars_returns_none(self, synthetic_df):
        # 19 prior bars is one short.
        td = synthetic_df.index[19].strftime('%Y-%m-%d')
        assert compute_pre_earnings_change(synthetic_df, td) is None


class TestAvgVolumeWindow:
    def test_excludes_trade_date_volume(self, synthetic_df):
        td = synthetic_df.index[20].strftime('%Y-%m-%d')
        v = compute_avg_volume_20d(synthetic_df, td)
        # Mean of Volume[0..19] = (1000 + ... + 1019) / 20 = 1009.5
        assert v == pytest.approx(1009.5, abs=1e-6)

    def test_insufficient_history_returns_none(self, synthetic_df):
        td = synthetic_df.index[10].strftime('%Y-%m-%d')
        assert compute_avg_volume_20d(synthetic_df, td) is None


class TestDateColumnVariant:
    def test_date_column_matches_index_variant(self, synthetic_df):
        df_col = synthetic_df.reset_index().rename(columns={'index': 'date'})
        td = synthetic_df.index[20].strftime('%Y-%m-%d')
        v_col = compute_pre_earnings_change(df_col, td)
        v_idx = compute_pre_earnings_change(synthetic_df, td)
        assert v_col == pytest.approx(v_idx, abs=1e-9)

    def test_date_column_avg_volume_matches(self, synthetic_df):
        df_col = synthetic_df.reset_index().rename(columns={'index': 'date'})
        td = synthetic_df.index[20].strftime('%Y-%m-%d')
        assert compute_avg_volume_20d(df_col, td) == pytest.approx(
            compute_avg_volume_20d(synthetic_df, td), abs=1e-9,
        )


class TestLowercaseColumnNames:
    """Some FMP responses use 'close'/'volume' instead of 'Close'/'Volume'."""

    def test_lowercase_close_column(self, synthetic_df):
        df_lc = synthetic_df.rename(columns={'Close': 'close', 'Volume': 'volume'})
        td = synthetic_df.index[20].strftime('%Y-%m-%d')
        v = compute_pre_earnings_change(df_lc, td)
        assert v == pytest.approx(19.0, abs=1e-6)
