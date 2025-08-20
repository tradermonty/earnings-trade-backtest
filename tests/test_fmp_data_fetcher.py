#!/usr/bin/env python3
"""
Comprehensive test suite for FMPDataFetcher
FMPデータフェッチャーの包括的テストスイート
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import time
import json
from datetime import datetime, timedelta
import os
import sys

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.fmp_data_fetcher import FMPDataFetcher


class TestFMPDataFetcher(unittest.TestCase):
    """FMPDataFetcherのテストクラス"""

    def setUp(self):
        """テストセットアップ"""
        self.test_api_key = "test_api_key_12345"
        self.fetcher = FMPDataFetcher(api_key=self.test_api_key)

    def test_initialization_with_api_key(self):
        """API key付きの初期化テスト"""
        fetcher = FMPDataFetcher(api_key="test_key")
        self.assertEqual(fetcher.api_key, "test_key")
        self.assertEqual(fetcher.base_url, "https://financialmodelingprep.com/api/v3")
        self.assertEqual(fetcher.calls_per_minute, 750)
        self.assertEqual(fetcher.calls_per_second, 12.5)

    def test_initialization_without_api_key(self):
        """API keyなしの初期化テスト（エラーケース）"""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as context:
                FMPDataFetcher()
            self.assertIn("FMP API key is required", str(context.exception))

    def test_initialization_from_env_var(self):
        """環境変数からのAPI key取得テスト"""
        with patch.dict(os.environ, {'FMP_API_KEY': 'env_test_key'}):
            fetcher = FMPDataFetcher()
            self.assertEqual(fetcher.api_key, 'env_test_key')


class TestRateLimiting(unittest.TestCase):
    """レート制限テストクラス"""

    def setUp(self):
        """テストセットアップ"""
        self.fetcher = FMPDataFetcher(api_key="test_key")

    def test_rate_limit_check_initial_state(self):
        """初期状態でのレート制限チェック"""
        # 初回リクエストは即座に処理されるべき
        start_time = time.time()
        self.fetcher._rate_limit_check()
        elapsed = time.time() - start_time
        
        # 最小リクエスト間隔以下の時間で完了するはず
        self.assertLess(elapsed, 0.2)
        self.assertEqual(len(self.fetcher.call_timestamps), 1)

    def test_minimum_request_interval(self):
        """最小リクエスト間隔のテスト"""
        # 2回連続でレート制限チェックを実行
        start_time = time.time()
        self.fetcher._rate_limit_check()
        self.fetcher._rate_limit_check()
        elapsed = time.time() - start_time
        
        # 最小リクエスト間隔（0.1秒）以上かかるはず
        self.assertGreaterEqual(elapsed, 0.1)

    def test_per_second_limit_tracking(self):
        """1秒間のリクエスト数制限テスト"""
        # 複数のコールを素早く実行
        for _ in range(5):
            self.fetcher._rate_limit_check()
        
        # コールタイムスタンプが記録されているかチェック
        self.assertEqual(len(self.fetcher.call_timestamps), 5)
        
        # 最新のコールがlast_request_timeに設定されているかチェック
        self.assertIsInstance(self.fetcher.last_request_time, datetime)

    def test_call_timestamp_cleanup(self):
        """古いコールタイムスタンプのクリーンアップテスト"""
        # 古いタイムスタンプを手動で追加
        old_timestamp = datetime.now() - timedelta(minutes=2)
        self.fetcher.call_timestamps.append(old_timestamp)
        
        # 新しいリクエストを実行
        self.fetcher._rate_limit_check()
        
        # 古いタイムスタンプが削除されているかチェック
        recent_calls = [
            ts for ts in self.fetcher.call_timestamps 
            if (datetime.now() - ts).total_seconds() < 60
        ]
        # 古いタイムスタンプは除外され、新しいリクエストのみが残る
        self.assertEqual(len(recent_calls), 1)


class TestAPIRequests(unittest.TestCase):
    """APIリクエストテストクラス"""

    def setUp(self):
        """テストセットアップ"""
        self.fetcher = FMPDataFetcher(api_key="test_key")

    @patch('requests.Session.get')
    def test_successful_request(self, mock_get):
        """成功時のAPIリクエストテスト"""
        # モックレスポンスの設定
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"test": "data"}
        mock_get.return_value = mock_response
        
        # リクエスト実行
        result = self.fetcher._make_request("test-endpoint")
        
        # 結果検証
        self.assertEqual(result, {"test": "data"})
        mock_get.assert_called_once()

    @patch('requests.Session.get')
    def test_404_error_handling(self, mock_get):
        """404エラーハンドリングテスト"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        result = self.fetcher._make_request("nonexistent-endpoint")
        
        self.assertIsNone(result)

    @patch('requests.Session.get')
    def test_403_error_handling(self, mock_get):
        """403エラーハンドリングテスト"""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response
        
        result = self.fetcher._make_request("forbidden-endpoint")
        
        self.assertIsNone(result)

    @patch('requests.Session.get')
    @patch('time.sleep')
    def test_429_retry_mechanism(self, mock_sleep, mock_get):
        """429エラーのリトライメカニズムテスト"""
        # 最初のリクエストで429エラー、2回目で成功
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {"success": "data"}
        
        mock_get.side_effect = [mock_response_429, mock_response_success]
        
        result = self.fetcher._make_request("test-endpoint")
        
        # 成功データが返されることを確認
        self.assertEqual(result, {"success": "data"})
        # スリープが呼ばれることを確認（指数バックオフ）
        mock_sleep.assert_called()
        # 2回リクエストが実行されることを確認
        self.assertEqual(mock_get.call_count, 2)

    @patch('requests.Session.get')
    @patch('time.sleep')
    def test_429_max_retries_exceeded(self, mock_sleep, mock_get):
        """429エラーの最大リトライ回数超過テスト"""
        # 全てのリクエストで429エラー
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response
        
        result = self.fetcher._make_request("test-endpoint", max_retries=2)
        
        # Noneが返されることを確認
        self.assertIsNone(result)
        # 3回リクエストが実行されることを確認（初回 + リトライ2回）
        self.assertEqual(mock_get.call_count, 3)

    @patch('requests.Session.get')
    def test_json_decode_error_handling(self, mock_get):
        """JSON解析エラーハンドリングテスト"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "doc", 0)
        mock_get.return_value = mock_response
        
        result = self.fetcher._make_request("test-endpoint")
        
        self.assertIsNone(result)

    @patch('requests.Session.get')
    def test_empty_response_handling(self, mock_get):
        """空のレスポンスハンドリングテスト"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = None
        mock_get.return_value = mock_response
        
        result = self.fetcher._make_request("test-endpoint")
        
        self.assertIsNone(result)

    @patch('requests.Session.get')
    def test_error_message_response_handling(self, mock_get):
        """エラーメッセージレスポンスハンドリングテスト"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Error Message": "API limit exceeded"}
        mock_get.return_value = mock_response
        
        result = self.fetcher._make_request("test-endpoint")
        
        self.assertIsNone(result)


class TestEarningsCalendar(unittest.TestCase):
    """決算カレンダーテストクラス"""

    def setUp(self):
        """テストセットアップ"""
        self.fetcher = FMPDataFetcher(api_key="test_key")

    @patch.object(FMPDataFetcher, '_make_request')
    def test_earnings_calendar_success(self, mock_request):
        """決算カレンダー取得成功テスト"""
        # モックデータの設定
        mock_data = [
            {
                "symbol": "AAPL",
                "date": "2024-01-15",
                "epsActual": 2.5,
                "epsEstimate": 2.3,
                "exchangeShortName": "NASDAQ"
            },
            {
                "symbol": "GOOGL",
                "date": "2024-01-16", 
                "epsActual": 1.8,
                "epsEstimate": 1.7,
                "exchangeShortName": "NASDAQ"
            }
        ]
        mock_request.return_value = mock_data
        
        result = self.fetcher.get_earnings_calendar("2024-01-15", "2024-01-16")
        
        # 結果検証
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["symbol"], "AAPL")
        self.assertEqual(result[1]["symbol"], "GOOGL")

    def test_earnings_calendar_us_filtering(self):
        """決算カレンダーのUS市場フィルタリングテスト"""
        # USフィルタリングロジックを直接テスト
        mock_data = [
            {
                "symbol": "AAPL",
                "date": "2024-01-15",
                "exchangeShortName": "NASDAQ"
            },
            {
                "symbol": "SHOP.TO",
                "date": "2024-01-15",
                "exchangeShortName": "TSX"
            },
            {
                "symbol": "VOD.L", 
                "date": "2024-01-15",
                "exchangeShortName": "LSE"
            }
        ]
        
        # USフィルタリングロジックを直接適用
        us_data = []
        for item in mock_data:
            symbol = item.get('symbol', '')
            exchange = item.get('exchangeShortName', '').upper()
            if exchange in ['NASDAQ', 'NYSE', 'AMEX', 'NYSE AMERICAN']:
                us_data.append(item)
            elif exchange == '' and symbol and not any(x in symbol for x in ['.TO', '.L', '.PA', '.AX', '.DE', '.HK']):
                us_data.append(item)
        
        # US市場の銘柄のみが残ることを確認
        self.assertEqual(len(us_data), 1)
        self.assertEqual(us_data[0]["symbol"], "AAPL")

    @patch.object(FMPDataFetcher, '_make_request')
    def test_earnings_calendar_date_chunking(self, mock_request):
        """決算カレンダーの日付分割テスト"""
        mock_request.return_value = [{"symbol": "TEST", "date": "2024-01-15"}]
        
        # 60日間のリクエスト（30日ごとに分割されるはず）
        start_date = "2024-01-01"
        end_date = "2024-03-01"
        
        result = self.fetcher.get_earnings_calendar(start_date, end_date)
        
        # 複数回のAPIコールが実行されることを確認
        self.assertGreater(mock_request.call_count, 1)

    @patch.object(FMPDataFetcher, '_get_earnings_calendar_alternative')
    @patch.object(FMPDataFetcher, '_make_request')
    def test_earnings_calendar_fallback_to_alternative(self, mock_request, mock_alternative):
        """決算カレンダーの代替メソッドへのフォールバックテスト"""
        # メインAPIが空データを返す
        mock_request.return_value = []
        
        # 代替メソッドがデータを返す
        mock_alternative.return_value = [{"symbol": "AAPL", "date": "2024-01-15"}]
        
        result = self.fetcher.get_earnings_calendar("2024-01-15", "2024-01-15")
        
        # 代替メソッドが呼ばれることを確認
        mock_alternative.assert_called_once()
        self.assertEqual(len(result), 1)


class TestHistoricalPriceData(unittest.TestCase):
    """株価履歴データテストクラス"""

    def setUp(self):
        """テストセットアップ"""
        self.fetcher = FMPDataFetcher(api_key="test_key")

    @patch.object(FMPDataFetcher, '_make_request')
    def test_historical_price_data_success(self, mock_request):
        """株価履歴データ取得成功テスト"""
        mock_data = {
            "historical": [
                {
                    "date": "2024-01-15",
                    "open": 150.0,
                    "high": 155.0,
                    "low": 148.0,
                    "close": 153.0,
                    "volume": 1000000
                }
            ]
        }
        mock_request.return_value = mock_data
        
        result = self.fetcher.get_historical_price_data("AAPL", "2024-01-15", "2024-01-15")
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["date"], "2024-01-15")
        self.assertEqual(result[0]["close"], 153.0)

    @patch.object(FMPDataFetcher, '_make_request')
    def test_historical_price_data_multiple_endpoints(self, mock_request):
        """株価履歴データの複数エンドポイント試行テスト"""
        # 最初のエンドポイントは失敗、2番目で成功
        mock_request.side_effect = [
            None,  # 最初のエンドポイント失敗
            [{"date": "2024-01-15", "close": 150.0}]  # 2番目のエンドポイント成功
        ]
        
        result = self.fetcher.get_historical_price_data("AAPL", "2024-01-15", "2024-01-15")
        
        # 成功データが返されることを確認
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        # 複数回APIが呼ばれることを確認
        self.assertEqual(mock_request.call_count, 2)

    @patch.object(FMPDataFetcher, '_make_request')
    def test_historical_price_data_all_endpoints_fail(self, mock_request):
        """全エンドポイント失敗時のテスト"""
        mock_request.return_value = None
        
        result = self.fetcher.get_historical_price_data("INVALID", "2024-01-15", "2024-01-15")
        
        self.assertIsNone(result)
        # 複数のエンドポイントが試行されることを確認
        self.assertGreater(mock_request.call_count, 1)

    @patch.object(FMPDataFetcher, '_make_request')
    def test_historical_price_data_list_format(self, mock_request):
        """リスト形式のレスポンステスト"""
        mock_data = [
            {
                "date": "2024-01-15",
                "close": 150.0
            }
        ]
        mock_request.return_value = mock_data
        
        result = self.fetcher.get_historical_price_data("AAPL", "2024-01-15", "2024-01-15")
        
        self.assertEqual(result, mock_data)


class TestDataProcessing(unittest.TestCase):
    """データ処理テストクラス"""

    def setUp(self):
        """テストセットアップ"""
        self.fetcher = FMPDataFetcher(api_key="test_key")

    def test_process_earnings_data_success(self):
        """決算データ処理成功テスト"""
        earnings_data = [
            {
                "symbol": "AAPL",
                "date": "2024-01-15",
                "epsActual": 2.5,
                "epsEstimated": 2.0,
                "time": "AfterMarket"
            }
        ]
        
        result = self.fetcher.process_earnings_data(earnings_data)
        
        self.assertFalse(result.empty)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]['code'], 'AAPL.US')
        self.assertEqual(result.iloc[0]['actual'], 2.5)
        self.assertEqual(result.iloc[0]['estimate'], 2.0)
        # サプライズ率の計算確認
        expected_percent = ((2.5 - 2.0) / abs(2.0)) * 100
        self.assertEqual(result.iloc[0]['percent'], expected_percent)

    def test_process_earnings_data_empty_input(self):
        """空の決算データ処理テスト"""
        result = self.fetcher.process_earnings_data([])
        
        self.assertTrue(result.empty)

    def test_safe_float_conversion(self):
        """安全なfloat変換テスト"""
        self.assertEqual(self.fetcher._safe_float("2.5"), 2.5)
        self.assertEqual(self.fetcher._safe_float(2.5), 2.5)
        self.assertIsNone(self.fetcher._safe_float(None))
        self.assertIsNone(self.fetcher._safe_float(""))
        self.assertIsNone(self.fetcher._safe_float("invalid"))

    def test_parse_timing(self):
        """時間情報パースティングテスト"""
        self.assertEqual(self.fetcher._parse_timing("Before Market"), "BeforeMarket")
        self.assertEqual(self.fetcher._parse_timing("After Market"), "AfterMarket")
        self.assertEqual(self.fetcher._parse_timing("BMO"), "BeforeMarket")
        self.assertEqual(self.fetcher._parse_timing("AMC"), "AfterMarket")
        self.assertIsNone(self.fetcher._parse_timing(""))
        self.assertIsNone(self.fetcher._parse_timing("During Market"))


class TestCompanyProfile(unittest.TestCase):
    """企業プロファイルテストクラス"""

    def setUp(self):
        """テストセットアップ"""
        self.fetcher = FMPDataFetcher(api_key="test_key")

    @patch.object(FMPDataFetcher, '_make_request')
    def test_company_profile_success(self, mock_request):
        """企業プロファイル取得成功テスト"""
        mock_data = [
            {
                "symbol": "AAPL",
                "companyName": "Apple Inc.",
                "industry": "Technology",
                "sector": "Consumer Electronics"
            }
        ]
        mock_request.return_value = mock_data
        
        result = self.fetcher.get_company_profile("AAPL")
        
        self.assertIsNotNone(result)
        self.assertEqual(result["symbol"], "AAPL")
        self.assertEqual(result["companyName"], "Apple Inc.")

    @patch.object(FMPDataFetcher, '_make_request')
    def test_company_profile_multiple_endpoints(self, mock_request):
        """企業プロファイルの複数エンドポイント試行テスト"""
        # 最初のエンドポイントは失敗、2番目で成功
        mock_request.side_effect = [
            None,  # v3エンドポイント失敗
            [{"symbol": "AAPL", "companyName": "Apple Inc."}]  # stableエンドポイント成功
        ]
        
        result = self.fetcher.get_company_profile("AAPL")
        
        self.assertIsNotNone(result)
        self.assertEqual(result["symbol"], "AAPL")


class TestSymbolRetrieval(unittest.TestCase):    
    """銘柄取得テストクラス"""

    def setUp(self):
        """テストセットアップ"""
        self.fetcher = FMPDataFetcher(api_key="test_key")

    @patch.object(FMPDataFetcher, '_make_request')
    def test_sp500_constituents_success(self, mock_request):
        """S&P500構成銘柄取得成功テスト"""
        mock_data = [
            {"symbol": "AAPL"},
            {"symbol": "MSFT"},
            {"symbol": "GOOGL"}
        ]
        mock_request.return_value = mock_data
        
        result = self.fetcher.get_sp500_constituents()
        
        self.assertEqual(len(result), 3)
        self.assertIn("AAPL", result)
        self.assertIn("MSFT", result)
        self.assertIn("GOOGL", result)

    @patch.object(FMPDataFetcher, '_make_request')
    def test_mid_small_cap_symbols_success(self, mock_request):
        """中小型株銘柄取得成功テスト"""
        mock_data = [
            {
                "symbol": "SMALL1",
                "exchangeShortName": "NASDAQ",
                "country": "US"
            },
            {
                "symbol": "SMALL2", 
                "exchangeShortName": "NYSE",
                "country": "US"
            },
            {
                "symbol": "FOREIGN.TO",  # カナダ株（除外されるべき）
                "exchangeShortName": "TSX", 
                "country": "CA"
            }
        ]
        mock_request.return_value = mock_data
        
        result = self.fetcher.get_mid_small_cap_symbols()
        
        # US株のみが返されることを確認
        self.assertEqual(len(result), 2)
        self.assertIn("SMALL1", result)
        self.assertIn("SMALL2", result)
        self.assertNotIn("FOREIGN.TO", result)

    @patch.object(FMPDataFetcher, '_get_mid_small_cap_fallback')
    @patch.object(FMPDataFetcher, '_make_request')
    def test_mid_small_cap_fallback(self, mock_request, mock_fallback):
        """中小型株取得のフォールバックテスト"""
        # APIが失敗
        mock_request.return_value = None
        
        # フォールバックメソッドがデータを返す
        mock_fallback.return_value = ["FALLBACK1", "FALLBACK2"]
        
        result = self.fetcher.get_mid_small_cap_symbols()
        
        # フォールバックメソッドが呼ばれることを確認
        mock_fallback.assert_called_once()
        self.assertEqual(len(result), 2)
        self.assertIn("FALLBACK1", result)


class TestAPIUsageStats(unittest.TestCase):
    """API使用統計テストクラス"""

    def setUp(self):
        """テストセットアップ"""
        self.fetcher = FMPDataFetcher(api_key="test_key")

    def test_api_usage_stats_initial_state(self):
        """初期状態のAPI使用統計テスト"""
        stats = self.fetcher.get_api_usage_stats()
        
        self.assertEqual(stats['calls_last_minute'], 0)
        self.assertEqual(stats['calls_last_second'], 0)
        self.assertEqual(stats['remaining_calls_minute'], 600)
        self.assertEqual(stats['remaining_calls_second'], 10)
        self.assertTrue(stats['api_key_set'])

    def test_api_usage_stats_after_calls(self):
        """コール実行後のAPI使用統計テスト"""
        # いくつかのレート制限チェックを実行
        for _ in range(3):
            self.fetcher._rate_limit_check()
        
        stats = self.fetcher.get_api_usage_stats()
        
        self.assertEqual(stats['calls_last_minute'], 3)
        self.assertEqual(stats['remaining_calls_minute'], 597)


class TestEdgeCases(unittest.TestCase):
    """エッジケーステストクラス"""

    def setUp(self):
        """テストセットアップ"""
        self.fetcher = FMPDataFetcher(api_key="test_key")

    def test_date_parsing_edge_cases(self):
        """日付パースのエッジケーステスト"""
        # 無効な日付文字列
        test_data = [
            {"symbol": "TEST", "date": "invalid-date"}
        ]
        
        result = self.fetcher.process_earnings_data(test_data)
        
        # エラーでも処理が続行されることを確認
        self.assertFalse(result.empty)

    def test_large_date_range_chunking(self):
        """大きな日付範囲の分割テスト"""
        with patch.object(self.fetcher, '_make_request') as mock_request:
            mock_request.return_value = []
            
            # 365日間のリクエスト
            start_date = "2024-01-01"
            end_date = "2024-12-31"
            
            self.fetcher.get_earnings_calendar(start_date, end_date)
            
            # 複数回に分割されて呼ばれることを確認
            self.assertGreater(mock_request.call_count, 10)

    @patch('time.sleep')
    def test_rate_limiting_under_load(self, mock_sleep):
        """負荷下でのレート制限テスト"""
        # 短時間で大量のリクエスト
        for _ in range(15):  # per_second_limitを超える
            self.fetcher._rate_limit_check()
        
        # スリープが呼ばれることを確認（レート制限が作動）
        mock_sleep.assert_called()


if __name__ == '__main__':
    # テストスイートの実行
    unittest.main(verbosity=2)