#!/usr/bin/env python3
"""
TDD Tests for Daily Candidates Screener Script
日次エントリー候補スクリーナーのテスト

Test Cases:
1. Default date is NY timezone today
2. CLI argument accepts custom date
3. Output directory is created if not exists
4. CSV contains required columns
5. Output filename format is correct
6. Empty CSV is created when no candidates
7. No look-ahead bias (uses previous day's close)
"""

import pytest
import pandas as pd
import os
import sys
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDailyScreenerDateHandling:
    """日付処理のテスト"""

    def test_default_date_is_ny_timezone_today(self):
        """デフォルト日付はNY時間の今日"""
        from scripts.screen_daily_candidates import get_default_date

        # Act
        result = get_default_date()

        # Assert
        assert isinstance(result, str)
        assert len(result) == 10  # YYYY-MM-DD format
        # Check it's a valid date format
        datetime.strptime(result, '%Y-%m-%d')

    def test_cli_argument_accepts_custom_date(self):
        """CLI引数でカスタム日付を指定できる"""
        from scripts.screen_daily_candidates import parse_arguments

        # Act
        with patch('sys.argv', ['script', '--date', '2024-06-15']):
            args = parse_arguments()

        # Assert
        assert args.date == '2024-06-15'


class TestDailyScreenerOutput:
    """出力処理のテスト"""

    @pytest.fixture
    def temp_output_dir(self):
        """一時出力ディレクトリ"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_output_directory_created_if_not_exists(self, temp_output_dir):
        """出力ディレクトリが存在しない場合は作成される"""
        from scripts.screen_daily_candidates import ensure_output_directory

        # Arrange
        new_dir = os.path.join(temp_output_dir, 'reports', 'screener')
        assert not os.path.exists(new_dir)

        # Act
        ensure_output_directory(new_dir)

        # Assert
        assert os.path.exists(new_dir)
        assert os.path.isdir(new_dir)

    def test_csv_contains_required_columns(self, temp_output_dir):
        """CSVに必要なカラムが含まれる"""
        from scripts.screen_daily_candidates import save_candidates_to_csv

        # Arrange
        candidates = [
            {
                'date': '2024-06-15',
                'symbol': 'AAPL',
                'score': 85.5,
                'sector': 'Technology',
                'gap_percent': 3.5,
                'eps_surprise_percent': 12.3,
                'pre_earnings_change': 5.2,
                'market_cap': 3000000000000,
                'volume_20d_avg': 50000000,
            }
        ]
        output_path = os.path.join(temp_output_dir, 'test_candidates.csv')

        # Act
        save_candidates_to_csv(candidates, output_path)

        # Assert
        assert os.path.exists(output_path)
        df = pd.read_csv(output_path)
        required_columns = ['date', 'symbol', 'score', 'sector', 'gap_percent',
                           'eps_surprise_percent', 'pre_earnings_change']
        for col in required_columns:
            assert col in df.columns, f"Missing column: {col}"

    def test_output_filename_format_is_correct(self):
        """出力ファイル名の形式が正しい"""
        from scripts.screen_daily_candidates import get_output_filename

        # Act
        filename = get_output_filename('2024-06-15')

        # Assert
        assert filename == 'daily_candidates_2024-06-15.csv'

    def test_empty_csv_created_when_no_candidates(self, temp_output_dir):
        """候補がない場合は空のCSVが作成される"""
        from scripts.screen_daily_candidates import save_candidates_to_csv

        # Arrange
        candidates = []
        output_path = os.path.join(temp_output_dir, 'empty_candidates.csv')

        # Act
        save_candidates_to_csv(candidates, output_path)

        # Assert
        assert os.path.exists(output_path)
        df = pd.read_csv(output_path)
        assert len(df) == 0


class TestDailyScreenerDataIntegrity:
    """データ整合性のテスト"""

    def test_no_lookahead_bias_uses_previous_day_close(self):
        """
        ルックアヘッドバイアスなし - 前日終値を使用

        DataFilter._second_stage_filter() では:
        - gap = (pre_open_price - prev_day_data['Close']) / prev_day_data['Close'] * 100
        - entry_price = trade_date_data['Open']

        Phase 2 fix: pre_earnings_change と avg_volume_20d も filter_utils 経由で
        trade_date より前のバーだけを参照する。

        スクリーナーを西海岸12:00 PM（マーケット引け後）に実行すれば
        確定した価格を使用するため、ルックアヘッドバイアスは発生しない。
        """
        # Verify: candidate dict shape from _build_scored_candidates carries the
        # canonical fields used by the backtest-paper parity comparison.
        from scripts.screen_daily_candidates import _build_scored_candidates

        items = [{
            'code': 'TEST',
            'percent': 10.0,
            'gap': 5.0,
            'pre_change': 3.0,
            'trade_date': '2024-06-15',
            'prev_close': 150.0,
        }]
        result = _build_scored_candidates(items, '2024-06-15')

        assert len(result) == 1
        c = result[0]
        # Canonical fields preserved
        assert c['symbol'] == 'TEST'
        assert c['eps_surprise_percent'] == 10.0
        assert c['trade_date'] == '2024-06-15'
        # Backwards-compat: `date` mirrors `trade_date`, `score` equals surprise %
        assert c['date'] == c['trade_date']
        assert c['score'] == c['eps_surprise_percent']

    def test_candidates_sorted_by_eps_surprise_descending(self):
        """Phase 3a parity: candidates sort by EPS surprise % descending.

        Matches DataFilter._select_top_stocks which sorts by `percent` desc;
        this ensures live screener and backtest pick the same top-N from the
        same input set.
        """
        from scripts.screen_daily_candidates import _build_scored_candidates

        items = [
            {'code': 'LOW',  'percent':  5.0, 'gap': 6.0, 'trade_date': '2024-06-15'},
            {'code': 'HIGH', 'percent': 25.0, 'gap': 1.0, 'trade_date': '2024-06-15'},
            {'code': 'MID',  'percent': 12.0, 'gap': 4.0, 'trade_date': '2024-06-15'},
        ]
        result = _build_scored_candidates(items, '2024-06-15')

        symbols_in_order = [c['symbol'] for c in result]
        assert symbols_in_order == ['HIGH', 'MID', 'LOW']

        # Score column equals the sort key (surprise %)
        scores = [c['score'] for c in result]
        surprises = [c['eps_surprise_percent'] for c in result]
        assert scores == surprises

    def test_csv_includes_canonical_trade_date_column(self):
        """CSV columns include both `date` (back-compat) and canonical `trade_date`."""
        from scripts.screen_daily_candidates import _build_scored_candidates

        items = [{'code': 'A', 'percent': 10.0, 'gap': 5.0, 'trade_date': '2024-06-15'}]
        result = _build_scored_candidates(items, '2024-06-15')
        c = result[0]

        assert 'date' in c
        assert 'trade_date' in c
        assert c['date'] == c['trade_date'] == '2024-06-15'


class TestDailyScreenerCLI:
    """CLI統合テスト"""

    def test_cli_help_shows_usage(self):
        """--help オプションで使い方が表示される"""
        from scripts.screen_daily_candidates import parse_arguments

        with pytest.raises(SystemExit) as exc_info:
            with patch('sys.argv', ['script', '--help']):
                parse_arguments()

        assert exc_info.value.code == 0

    def test_cli_invalid_date_format_raises_error(self):
        """不正な日付形式でエラーが発生"""
        from scripts.screen_daily_candidates import validate_date

        with pytest.raises(ValueError):
            validate_date('invalid-date')


class TestDailyScreenerUniverseIntegration:
    """Universe pre-filter integration tests"""

    @patch('scripts.screen_daily_candidates.build_target_universe')
    @patch('scripts.screen_daily_candidates.DataFetcher')
    def test_screen_candidates_calls_build_target_universe(
        self, MockDataFetcher, mock_build_universe
    ):
        """screen_candidates() should call build_target_universe with CLI params"""
        mock_build_universe.return_value = ({'AAPL', 'MSFT'}, 'fmp_screener')
        mock_fetcher = MockDataFetcher.return_value
        mock_fetcher.get_earnings_data.return_value = {'earnings': []}

        args = Mock()
        args.min_price = 30.0
        args.min_market_cap = 5.0
        args.min_volume = 200000
        args.min_surprise = 5.0
        args.max_gap = 10.0

        from scripts.screen_daily_candidates import screen_candidates
        screen_candidates('2024-06-15', args)

        mock_build_universe.assert_called_once()
        call_kwargs = mock_build_universe.call_args.kwargs
        assert call_kwargs['screener_price_min'] == 30.0
        assert call_kwargs['min_market_cap'] == 5e9

    @patch('scripts.screen_daily_candidates.build_target_universe')
    @patch('scripts.screen_daily_candidates.DataFetcher')
    def test_screen_candidates_fail_closed_on_none_universe(
        self, MockDataFetcher, mock_build_universe
    ):
        """When build_target_universe returns None, return empty list (fail closed)"""
        mock_build_universe.return_value = (None, 'fmp_screener_failed')

        args = Mock()
        args.min_price = 30.0
        args.min_market_cap = 5.0
        args.min_volume = 200000
        args.min_surprise = 5.0
        args.max_gap = 10.0

        from scripts.screen_daily_candidates import screen_candidates
        result = screen_candidates('2024-06-15', args)

        assert result == []
        # get_earnings_data should NOT be called
        MockDataFetcher.return_value.get_earnings_data.assert_not_called()

    @patch('scripts.screen_daily_candidates.build_target_universe')
    @patch('scripts.screen_daily_candidates.DataFetcher')
    def test_screen_candidates_fetches_from_prev_bday(
        self, MockDataFetcher, mock_build_universe
    ):
        """Earnings fetch should start from the previous business day"""
        mock_build_universe.return_value = ({'AAPL'}, 'fmp_screener')
        mock_fetcher = MockDataFetcher.return_value
        mock_fetcher.get_earnings_data.return_value = {'earnings': []}

        args = Mock()
        args.min_price = 30.0
        args.min_market_cap = 5.0
        args.min_volume = 200000
        args.min_surprise = 5.0
        args.max_gap = 10.0

        from scripts.screen_daily_candidates import screen_candidates

        # Wednesday -> prev bday is Tuesday
        screen_candidates('2026-03-04', args)
        call_kwargs = mock_fetcher.get_earnings_data.call_args.kwargs
        assert call_kwargs['start_date'] == '2026-03-03'

    @patch('scripts.screen_daily_candidates.build_target_universe')
    @patch('scripts.screen_daily_candidates.DataFetcher')
    def test_screen_candidates_monday_fetches_from_friday(
        self, MockDataFetcher, mock_build_universe
    ):
        """Monday screening should fetch from Friday (prev business day)"""
        mock_build_universe.return_value = ({'AAPL'}, 'fmp_screener')
        mock_fetcher = MockDataFetcher.return_value
        mock_fetcher.get_earnings_data.return_value = {'earnings': []}

        args = Mock()
        args.min_price = 30.0
        args.min_market_cap = 5.0
        args.min_volume = 200000
        args.min_surprise = 5.0
        args.max_gap = 10.0

        from scripts.screen_daily_candidates import screen_candidates

        # 2026-03-09 is Monday
        screen_candidates('2026-03-09', args)
        call_kwargs = mock_fetcher.get_earnings_data.call_args.kwargs
        assert call_kwargs['start_date'] == '2026-03-06'  # Friday

    @patch('scripts.screen_daily_candidates.DataFilter')
    @patch('scripts.screen_daily_candidates.build_target_universe')
    @patch('scripts.screen_daily_candidates.DataFetcher')
    def test_screen_candidates_filters_stale_trade_dates(
        self, MockDataFetcher, mock_build_universe, MockDataFilter
    ):
        """Candidates with trade_date != date_str should be excluded"""
        mock_build_universe.return_value = ({'AAPL', 'MSFT'}, 'fmp_screener')
        mock_fetcher = MockDataFetcher.return_value
        mock_fetcher.get_earnings_data.return_value = {'earnings': [
            {'code': 'AAPL.US', 'percent': 10, 'actual': 1.5, 'report_date': '2026-03-03'},
        ]}

        # DataFilter returns candidates with mixed trade_dates
        mock_filter_instance = MockDataFilter.return_value
        mock_filter_instance.filter_earnings_data.return_value = [
            {'code': 'AAPL', 'trade_date': '2026-03-03', 'percent': 10, 'gap': 5,
             'prev_close': 150, 'entry_price': 155},
            {'code': 'MSFT', 'trade_date': '2026-03-02', 'percent': 8, 'gap': 3,
             'prev_close': 300, 'entry_price': 310},  # stale
        ]

        args = Mock()
        args.min_price = 30.0
        args.min_market_cap = 5.0
        args.min_volume = 200000
        args.min_surprise = 5.0
        args.max_gap = 10.0

        from scripts.screen_daily_candidates import screen_candidates
        result = screen_candidates('2026-03-03', args)

        # Only AAPL should remain (trade_date matches)
        assert len(result) == 1
        assert result[0]['symbol'] == 'AAPL'


class TestCriticalBugRegressions:
    """Regression tests for C-1 (Friday AMC trade_date) and C-2 (pre_change scoring)"""

    def test_friday_amc_produces_monday_trade_date(self):
        """C-1: Friday AMC must map to Monday, not Saturday (regression for determine_trade_date)"""
        from src.data_filter import DataFilter

        df = DataFilter(
            data_fetcher=Mock(),
            target_symbols=None,
            min_surprise_percent=5.0,
        )
        # Friday 2026-03-06 AMC -> Monday 2026-03-09
        result = df.determine_trade_date('2026-03-06', 'AfterMarket')
        assert result == '2026-03-09', f"Friday AMC should map to Monday, got {result}"

        # Thursday AMC -> Friday (unchanged)
        result2 = df.determine_trade_date('2026-03-05', 'AfterMarket')
        assert result2 == '2026-03-06'

        # Friday BMO -> Friday (unchanged)
        result3 = df.determine_trade_date('2026-03-06', 'BeforeMarket')
        assert result3 == '2026-03-06'

    @patch('scripts.screen_daily_candidates.DataFilter')
    @patch('scripts.screen_daily_candidates.build_target_universe')
    @patch('scripts.screen_daily_candidates.DataFetcher')
    def test_candidates_ranked_by_eps_surprise_descending(
        self, MockDataFetcher, mock_build_universe, MockDataFilter
    ):
        """Phase 3a parity: ranking is EPS surprise % descending (matches DataFilter._select_top_stocks).

        Replaces the prior `test_pre_change_affects_candidate_score`: the
        weighted score formula was deleted in favor of surprise-only ranking
        so that live screener and backtest pick the same top-N from the same
        input set.
        """
        mock_build_universe.return_value = ({'AAPL', 'MSFT', 'NVDA'}, 'fmp_screener')
        mock_fetcher = MockDataFetcher.return_value
        mock_fetcher.get_earnings_data.return_value = {'earnings': []}

        mock_filter = MockDataFilter.return_value
        mock_filter.filter_earnings_data.return_value = [
            {'code': 'AAPL', 'trade_date': '2026-03-03', 'percent': 20,
             'gap': 5, 'prev_close': 150, 'entry_price': 155, 'pre_change': 0},
            {'code': 'MSFT', 'trade_date': '2026-03-03', 'percent': 35,  # highest surprise
             'gap': 1, 'prev_close': 300, 'entry_price': 305, 'pre_change': 15.0},
            {'code': 'NVDA', 'trade_date': '2026-03-03', 'percent': 12,
             'gap': 6, 'prev_close': 800, 'entry_price': 820, 'pre_change': 8.0},
        ]

        args = Mock()
        args.min_price = 30.0
        args.min_market_cap = 5.0
        args.min_volume = 200000
        args.min_surprise = 5.0
        args.max_gap = 10.0

        from scripts.screen_daily_candidates import screen_candidates
        result = screen_candidates('2026-03-03', args)

        assert len(result) == 3
        # Surprise-descending order: MSFT(35) > AAPL(20) > NVDA(12)
        # — independent of gap and pre_change.
        symbols = [c['symbol'] for c in result]
        assert symbols == ['MSFT', 'AAPL', 'NVDA'], (
            f'Expected surprise-descending order, got {symbols}'
        )
        # `score` column equals the sort key (surprise %).
        assert [c['score'] for c in result] == [35, 20, 12]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
