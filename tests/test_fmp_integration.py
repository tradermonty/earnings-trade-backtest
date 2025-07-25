#!/usr/bin/env python3
"""
FMP Data Fetcher Integration Tests
実際のFMP APIを使用した統合テスト（APIキーが必要）
"""

import unittest
import os
import time
from datetime import datetime, timedelta
import sys
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.fmp_data_fetcher import FMPDataFetcher
from src.data_fetcher import DataFetcher

@unittest.skipUnless(os.getenv('FMP_API_KEY'), "FMP API key required for integration tests")
class TestFMPIntegration(unittest.TestCase):
    """FMP API統合テストクラス"""

    @classmethod
    def setUpClass(cls):
        """テストクラスのセットアップ"""
        cls.api_key = os.getenv('FMP_API_KEY')
        if not cls.api_key:
            cls.skipTest("FMP_API_KEY environment variable not set")
        
        cls.fetcher = FMPDataFetcher(api_key=cls.api_key)
        print(f"\n=== FMP Integration Tests ===")
        print(f"API Key: {cls.api_key[:10]}...")
        print(f"Base URL: {cls.fetcher.base_url}")

    def test_rate_limiting_functionality(self):
        """レート制限機能の実機テスト"""
        print("\n--- Testing Rate Limiting ---")
        
        # API使用統計の初期状態を確認
        initial_stats = self.fetcher.get_api_usage_stats()
        print(f"Initial calls in last minute: {initial_stats['calls_last_minute']}")
        
        # 複数のリクエストを実行してレート制限をテスト
        start_time = time.time()
        
        for i in range(5):
            result = self.fetcher.get_company_profile("AAPL")
            self.assertIsNotNone(result, f"Request {i+1} should return data")
            print(f"Request {i+1}: {'Success' if result else 'Failed'}")
        
        elapsed = time.time() - start_time
        print(f"5 requests completed in {elapsed:.2f} seconds")
        
        # レート制限が適切に動作していることを確認
        self.assertGreaterEqual(elapsed, 0.5, "Rate limiting should enforce minimum intervals")
        
        # 最終統計を確認
        final_stats = self.fetcher.get_api_usage_stats()
        print(f"Final calls in last minute: {final_stats['calls_last_minute']}")
        self.assertGreaterEqual(final_stats['calls_last_minute'], 5)

    def test_earnings_calendar_real_data(self):
        """実際の決算カレンダーデータ取得テスト"""
        print("\n--- Testing Earnings Calendar ---")
        
        # 過去1週間のデータを取得
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        from_date = start_date.strftime('%Y-%m-%d')
        to_date = end_date.strftime('%Y-%m-%d')
        
        print(f"Fetching earnings data from {from_date} to {to_date}")
        
        result = self.fetcher.get_earnings_calendar(from_date, to_date, us_only=True)
        
        self.assertIsInstance(result, list, "Should return a list")
        print(f"Retrieved {len(result)} earnings records")
        
        if result:
            # データ構造の確認
            sample = result[0]
            required_fields = ['symbol', 'date']
            for field in required_fields:
                self.assertIn(field, sample, f"Should contain {field} field")
            
            print(f"Sample record: {sample['symbol']} on {sample['date']}")
            
            # US市場のみであることを確認
            for record in result[:5]:  # 最初の5件をチェック
                symbol = record.get('symbol', '')
                self.assertFalse(any(suffix in symbol for suffix in ['.TO', '.L', '.PA']), 
                               f"Should only contain US stocks, found: {symbol}")

    def test_historical_price_data_real(self):
        """実際の株価履歴データ取得テスト"""
        print("\n--- Testing Historical Price Data ---")
        
        # AAPL の過去5日間のデータを取得
        end_date = datetime.now()
        start_date = end_date - timedelta(days=10)
        
        from_date = start_date.strftime('%Y-%m-%d')
        to_date = end_date.strftime('%Y-%m-%d')
        
        print(f"Fetching AAPL price data from {from_date} to {to_date}")
        
        result = self.fetcher.get_historical_price_data("AAPL", from_date, to_date)
        
        self.assertIsNotNone(result, "Should return price data")
        self.assertIsInstance(result, list, "Should return a list")
        self.assertGreater(len(result), 0, "Should return at least one price record")
        
        print(f"Retrieved {len(result)} price records")
        
        # データ構造の確認
        sample = result[0]
        required_fields = ['date', 'close']
        for field in required_fields:
            self.assertIn(field, sample, f"Should contain {field} field")
        
        print(f"Sample price: {sample['date']} - Close: ${sample['close']}")

    def test_company_profile_real(self):
        """実際の企業プロファイル取得テスト"""
        print("\n--- Testing Company Profile ---")
        
        symbols_to_test = ["AAPL", "MSFT", "GOOGL"]
        
        for symbol in symbols_to_test:
            print(f"Fetching profile for {symbol}")
            
            result = self.fetcher.get_company_profile(symbol)
            
            if result:
                self.assertIsInstance(result, dict, "Should return a dictionary")
                self.assertEqual(result.get('symbol'), symbol, f"Should return data for {symbol}")
                
                # 基本的なフィールドの存在確認
                expected_fields = ['symbol', 'companyName']
                for field in expected_fields:
                    if field in result:
                        print(f"  {field}: {result[field]}")
            else:
                print(f"  No data returned for {symbol}")

    def test_data_processing_real(self):
        """実際のデータ処理テスト"""
        print("\n--- Testing Data Processing ---")
        
        # 実際の決算データを取得して処理
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        from_date = start_date.strftime('%Y-%m-%d')
        to_date = end_date.strftime('%Y-%m-%d')
        
        earnings_data = self.fetcher.get_earnings_calendar(from_date, to_date, us_only=True)
        
        if earnings_data:
            # データ処理テスト
            df = self.fetcher.process_earnings_data(earnings_data[:10])  # 最初の10件
            
            self.assertFalse(df.empty, "Processed data should not be empty")
            print(f"Processed {len(df)} earnings records")
            
            # 必要なカラムの存在確認
            required_columns = ['code', 'actual', 'estimate', 'percent']
            for col in required_columns:
                self.assertIn(col, df.columns, f"Should contain {col} column")
            
            # サンプルデータの表示
            if len(df) > 0:
                sample = df.iloc[0]
                print(f"Sample processed record: {sample['code']} - Surprise: {sample['percent']:.2f}%")

class TestDataFetcherIntegration(unittest.TestCase):
    """DataFetcher統合テストクラス"""

    @classmethod
    def setUpClass(cls):
        """テストクラスのセットアップ"""
        cls.api_key = os.getenv('FMP_API_KEY')
        if not cls.api_key:
            cls.skipTest("FMP_API_KEY environment variable not set")

    def test_data_fetcher_fmp_integration(self):
        """DataFetcher FMP統合テスト"""
        print("\n--- Testing DataFetcher FMP Integration ---")
        
        # FMP有効でDataFetcher初期化
        data_fetcher = DataFetcher(use_fmp=True)
        print("DataFetcher (FMP enabled) initialized successfully")
        
        # 決算データ取得テスト
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        print(f"Fetching earnings data ({start_date} to {end_date})")
        earnings_result = data_fetcher.get_earnings_data(start_date, end_date)
        
        earnings_list = earnings_result.get('earnings', [])
        print(f"Retrieved via DataFetcher: {len(earnings_list)} records")
        
        if earnings_list:
            sample_earning = earnings_list[0]
            print(f"Sample: {sample_earning.get('code', 'N/A')} - {sample_earning.get('data_source', 'N/A')}")
            
            # FMPデータの特徴確認
            fmp_count = sum(1 for e in earnings_list if e.get('data_source') == 'FMP')
            print(f"FMP source data: {fmp_count}/{len(earnings_list)}")
            
            # データ構造の確認
            required_fields = ['code', 'date', 'actual', 'estimate']
            for field in required_fields:
                self.assertIn(field, sample_earning, f"Should contain {field} field")

    def test_data_quality_comparison(self):
        """データ品質比較テスト"""
        print("\n--- Testing Data Quality Comparison ---")
        
        # EODHD vs FMP データ比較
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        print(f"Comparing data quality ({start_date} to {end_date})")
        
        # EODHDデータ取得
        eodhd_fetcher = DataFetcher(use_fmp=False) 
        eodhd_data = eodhd_fetcher.get_earnings_data(start_date, end_date)
        eodhd_earnings = eodhd_data.get('earnings', [])
        
        # FMPデータ取得  
        fmp_fetcher = DataFetcher(use_fmp=True)
        fmp_data = fmp_fetcher.get_earnings_data(start_date, end_date)
        fmp_earnings = fmp_data.get('earnings', [])
        
        print(f"EODHD earnings data: {len(eodhd_earnings)} records")
        print(f"FMP earnings data: {len(fmp_earnings)} records")
        
        # US株のみでフィルタして比較
        eodhd_us = [e for e in eodhd_earnings if e.get('code', '').endswith('.US')]
        fmp_us = [e for e in fmp_earnings if e.get('code', '')]  # FMPは全てUS株
        
        print(f"EODHD US stocks: {len(eodhd_us)} records")
        print(f"FMP US stocks: {len(fmp_us)} records")
        
        # データ品質指標
        if eodhd_us:
            eodhd_with_eps = sum(1 for e in eodhd_us if e.get('actual') is not None and e.get('estimate') is not None)
            eodhd_eps_rate = eodhd_with_eps / len(eodhd_us) * 100
            print(f"EODHD EPS completeness: {eodhd_eps_rate:.1f}%")
        
        if fmp_us:
            fmp_with_eps = sum(1 for e in fmp_us if e.get('actual') is not None and e.get('estimate') is not None)
            fmp_eps_rate = fmp_with_eps / len(fmp_us) * 100
            print(f"FMP EPS completeness: {fmp_eps_rate:.1f}%")

if __name__ == '__main__':
    # 環境変数チェック
    if not os.getenv('FMP_API_KEY'):
        print("Warning: FMP_API_KEY environment variable not set.")
        print("Integration tests will be skipped.")
        print("To run integration tests, set your FMP API key:")
        print("export FMP_API_KEY=your_api_key_here")
        print("Or create a .env file with: FMP_API_KEY=your_api_key_here")
    
    # テスト実行
    unittest.main(verbosity=2)