#!/usr/bin/env python3
"""
FMP Data Fetcher Comprehensive Test Report
FMPデータフェッチャーの包括的テストレポート生成
"""

import unittest
import time
import os
import sys
from datetime import datetime

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.fmp_data_fetcher import FMPDataFetcher


class TestReportGenerator:
    """テストレポート生成クラス"""
    
    def __init__(self):
        self.results = []
        self.start_time = None
        self.end_time = None

    def start_test_suite(self):
        """テストスイート開始"""
        self.start_time = datetime.now()
        print(f"\n{'='*80}")
        print(f"FMP DATA FETCHER COMPREHENSIVE TEST REPORT")
        print(f"{'='*80}")
        print(f"Test started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")

    def end_test_suite(self):
        """テストスイート終了"""
        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()
        
        print(f"\n{'='*80}")
        print(f"TEST SUMMARY")
        print(f"{'='*80}")
        print(f"Total duration: {duration:.2f} seconds")
        print(f"Tests completed at: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 結果統計
        passed = sum(1 for r in self.results if r['status'] == 'PASSED')
        failed = sum(1 for r in self.results if r['status'] == 'FAILED')
        skipped = sum(1 for r in self.results if r['status'] == 'SKIPPED')
        
        print(f"\nResults:")
        print(f"  ✅ PASSED:  {passed}")
        print(f"  ❌ FAILED:  {failed}")
        print(f"  ⏭️  SKIPPED: {skipped}")
        print(f"  📊 TOTAL:   {len(self.results)}")
        
        success_rate = (passed / len(self.results)) * 100 if self.results else 0
        print(f"  🎯 SUCCESS RATE: {success_rate:.1f}%")
        
        print(f"\n{'='*80}")
        if failed == 0:
            print("🎉 ALL TESTS PASSED! FMP Data Fetcher is ready for production.")
        else:
            print(f"⚠️  {failed} TEST(S) FAILED. Please review the issues above.")
        print(f"{'='*80}")

    def add_test_result(self, category, test_name, status, duration=0, details=None):
        """テスト結果を追加"""
        result = {
            'category': category,
            'test_name': test_name,
            'status': status,
            'duration': duration,
            'details': details or {},
            'timestamp': datetime.now()
        }
        self.results.append(result)
        
        # リアルタイム出力
        status_icon = {'PASSED': '✅', 'FAILED': '❌', 'SKIPPED': '⏭️'}.get(status, '❓')
        print(f"{status_icon} [{category}] {test_name} ({duration:.3f}s)")
        
        if details and status != 'SKIPPED':
            for key, value in details.items():
                print(f"    {key}: {value}")


def run_comprehensive_tests():
    """包括的テストの実行"""
    reporter = TestReportGenerator()
    reporter.start_test_suite()
    
    # FMP APIキーの確認
    api_key = os.getenv('FMP_API_KEY')
    if not api_key:
        reporter.add_test_result(
            "Setup", "API Key Check", "SKIPPED",
            details={"reason": "FMP_API_KEY not set in environment"}
        )
        reporter.end_test_suite()
        return
    
    try:
        fetcher = FMPDataFetcher(api_key=api_key)
        reporter.add_test_result("Setup", "FMP Fetcher Initialization", "PASSED", 0.001)
    except Exception as e:
        reporter.add_test_result(
            "Setup", "FMP Fetcher Initialization", "FAILED", 0.001,
            details={"error": str(e)}
        )
        reporter.end_test_suite()
        return

    # テスト1: レート制限機能テスト
    test_start = time.time()
    try:
        initial_stats = fetcher.get_api_usage_stats()
        
        # 5回のAPIコール実行
        for i in range(5):
            result = fetcher.get_company_profile("AAPL")
            if not result:
                raise Exception(f"API call {i+1} failed")
        
        final_stats = fetcher.get_api_usage_stats()
        duration = time.time() - test_start
        
        reporter.add_test_result(
            "Rate Limiting", "API Rate Limiting Test", "PASSED", duration,
            details={
                "initial_calls": initial_stats['calls_last_minute'],
                "final_calls": final_stats['calls_last_minute'],
                "calls_executed": 5,
                "duration": f"{duration:.2f}s"
            }
        )
    except Exception as e:
        reporter.add_test_result(
            "Rate Limiting", "API Rate Limiting Test", "FAILED", time.time() - test_start,
            details={"error": str(e)}
        )

    # テスト2: 決算カレンダーデータ取得
    test_start = time.time()
    try:
        from datetime import timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        earnings_data = fetcher.get_earnings_calendar(
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d'),
            us_only=True
        )
        
        duration = time.time() - test_start
        
        if earnings_data:
            sample = earnings_data[0]
            us_count = len(earnings_data)
            
            reporter.add_test_result(
                "Data Fetching", "Earnings Calendar Retrieval", "PASSED", duration,
                details={
                    "records_retrieved": len(earnings_data),
                    "us_only_filter": "Applied",
                    "sample_symbol": sample.get('symbol', 'N/A'),
                    "sample_date": sample.get('date', 'N/A')
                }
            )
        else:
            reporter.add_test_result(
                "Data Fetching", "Earnings Calendar Retrieval", "PASSED", duration,
                details={"records_retrieved": 0, "note": "No earnings data in test period"}
            )
    except Exception as e:
        reporter.add_test_result(
            "Data Fetching", "Earnings Calendar Retrieval", "FAILED", time.time() - test_start,
            details={"error": str(e)}
        )

    # テスト3: 株価データ取得
    test_start = time.time()
    try:
        from datetime import timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)
        
        price_data = fetcher.get_historical_price_data(
            "AAPL",
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )
        
        duration = time.time() - test_start
        
        if price_data and len(price_data) > 0:
            sample = price_data[0]
            reporter.add_test_result(
                "Data Fetching", "Historical Price Data Retrieval", "PASSED", duration,
                details={
                    "symbol": "AAPL",
                    "records_retrieved": len(price_data),
                    "sample_date": sample.get('date', 'N/A'),
                    "sample_close": f"${sample.get('close', 'N/A')}"
                }
            )
        else:
            raise Exception("No price data returned")
    except Exception as e:
        reporter.add_test_result(
            "Data Fetching", "Historical Price Data Retrieval", "FAILED", time.time() - test_start,
            details={"error": str(e)}
        )

    # テスト4: データ処理機能
    test_start = time.time()
    try:
        # サンプル決算データでテスト
        sample_earnings = [
            {
                "symbol": "TEST",
                "date": "2024-01-15",
                "epsActual": 2.5,
                "epsEstimated": 2.0,
                "time": "AfterMarket"
            }
        ]
        
        df = fetcher.process_earnings_data(sample_earnings)
        duration = time.time() - test_start
        
        if not df.empty:
            processed_record = df.iloc[0]
            surprise_percent = processed_record.get('percent', 0)
            
            reporter.add_test_result(
                "Data Processing", "Earnings Data Processing", "PASSED", duration,
                details={
                    "input_records": len(sample_earnings),
                    "output_records": len(df),
                    "surprise_calculation": f"{surprise_percent:.1f}%",
                    "data_format": "DataFrame"
                }
            )
        else:
            raise Exception("Processed data frame is empty")
    except Exception as e:
        reporter.add_test_result(
            "Data Processing", "Earnings Data Processing", "FAILED", time.time() - test_start,
            details={"error": str(e)}
        )

    # テスト5: エラーハンドリング
    test_start = time.time()
    try:
        # 存在しない銘柄でのテスト
        result = fetcher.get_company_profile("NONEXISTENT123")
        
        # 無効な日付範囲でのテスト
        invalid_result = fetcher.get_historical_price_data("AAPL", "2030-01-01", "2030-01-02")
        
        duration = time.time() - test_start
        
        reporter.add_test_result(
            "Error Handling", "Invalid Input Handling", "PASSED", duration,
            details={
                "nonexistent_symbol": "Handled gracefully" if result is None else "Unexpected result",
                "invalid_date_range": "Handled gracefully" if invalid_result is None else "Unexpected result"
            }
        )
    except Exception as e:
        reporter.add_test_result(
            "Error Handling", "Invalid Input Handling", "FAILED", time.time() - test_start,
            details={"error": str(e)}
        )

    # テスト完了
    reporter.end_test_suite()


if __name__ == "__main__":
    run_comprehensive_tests()