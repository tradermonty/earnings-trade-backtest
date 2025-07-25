#!/usr/bin/env python3
"""
決算日検証システムのテストスクリプト
"""

import os
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

from src.news_fetcher import NewsFetcher
from src.earnings_date_validator import EarningsDateValidator

def test_news_fetcher():
    """NewsFetcherのテスト"""
    print("=== NewsFetcher テスト ===")
    
    api_key = os.getenv('EODHD_API_KEY')
    if not api_key:
        print("エラー: EODHD_API_KEYが設定されていません")
        return False
    
    fetcher = NewsFetcher(api_key)
    
    # AAPLの決算前後のニュースを取得
    print("AAPLのニュースを取得中...")
    news = fetcher.fetch_earnings_period_news('AAPL', '2024-01-25', days_before=3, days_after=3)
    
    print(f"取得したニュース数: {len(news)}")
    if news:
        print("最初のニュース:")
        first_news = news[0]
        print(f"- タイトル: {first_news.get('title', 'N/A')}")
        print(f"- 日付: {first_news.get('date', 'N/A')}")
        print(f"- ソース: {first_news.get('source', 'N/A')}")
        return True
    else:
        print("ニュースが取得できませんでした")
        return False

def test_earnings_date_validator():
    """EarningsDateValidatorのテスト"""
    print("\n=== EarningsDateValidator テスト ===")
    
    api_key = os.getenv('EODHD_API_KEY')
    if not api_key:
        print("エラー: EODHD_API_KEYが設定されていません")
        return False
    
    fetcher = NewsFetcher(api_key)
    validator = EarningsDateValidator(fetcher)
    
    # AAPLの決算日を検証
    print("AAPLの決算日を検証中...")
    result = validator.validate_earnings_date('AAPL', '2024-01-25')
    
    print("検証結果:")
    print(f"- 銘柄: {result['symbol']}")
    print(f"- EODHD日付: {result['eodhd_date']}")
    print(f"- 実際の日付: {result['actual_date']}")
    print(f"- 信頼度: {result['confidence']:.2f} ({result['confidence_level']})")
    print(f"- 日付変更: {result['date_changed']}")
    print(f"- 証拠数: {len(result['news_evidence'])}")
    
    if result['news_evidence']:
        print("決算関連記事:")
        for i, evidence in enumerate(result['news_evidence'][:3]):  # 最初の3件
            print(f"  {i+1}. {evidence['title'][:60]}...")
            print(f"     スコア: {evidence['earnings_score']:.2f}, 日付: {evidence['date'][:10]}")
    
    return True

def test_cache_functionality():
    """キャッシュ機能のテスト"""
    print("\n=== キャッシュ機能テスト ===")
    
    api_key = os.getenv('EODHD_API_KEY')
    if not api_key:
        print("エラー: EODHD_API_KEYが設定されていません")
        return False
    
    fetcher = NewsFetcher(api_key)
    
    # キャッシュ情報を表示
    cache_info = fetcher.get_cache_info()
    print(f"キャッシュファイル数: {cache_info['file_count']}")
    print(f"合計サイズ: {cache_info['total_size_mb']} MB")
    print(f"キャッシュディレクトリ: {cache_info['cache_dir']}")
    
    return True

def main():
    """メインテスト関数"""
    print("決算日検証システムのテストを開始します...")
    
    # 各テストを実行
    tests = [
        ("NewsFetcher", test_news_fetcher),
        ("EarningsDateValidator", test_earnings_date_validator),
        ("キャッシュ機能", test_cache_functionality)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"{test_name}でエラーが発生: {e}")
            results.append((test_name, False))
    
    # 結果サマリー
    print("\n" + "=" * 50)
    print("テスト結果サマリー:")
    for test_name, result in results:
        status = "成功" if result else "失敗"
        print(f"- {test_name}: {status}")
    
    successful_tests = sum(1 for _, result in results if result)
    print(f"\n成功: {successful_tests}/{len(results)} テスト")

if __name__ == "__main__":
    main()