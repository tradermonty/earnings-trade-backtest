#!/usr/bin/env python3
"""
FMP API 403エラーの詳細調査スクリプト
"""

import os
import requests
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

def debug_fmp_api():
    """FMP APIの詳細デバッグ"""
    
    api_key = os.getenv('FMP_API_KEY')
    if not api_key:
        print("❌ FMP_API_KEY環境変数が設定されていません")
        return
    
    print("=== FMP API 詳細デバッグ ===")
    print(f"使用中のAPIキー: {api_key[:10]}...{api_key[-10:]}")
    print()
    
    # 1. 基本接続テスト
    print("1. 基本接続テスト...")
    test_basic_connection(api_key)
    
    # 2. APIキー検証
    print("\n2. APIキー検証...")
    test_api_key_validation(api_key)
    
    # 3. プラン確認
    print("\n3. プラン・制限確認...")
    test_plan_limits(api_key)
    
    # 4. 利用可能エンドポイント確認
    print("\n4. 利用可能エンドポイント確認...")
    test_available_endpoints(api_key)
    
    # 5. 代替エンドポイントテスト
    print("\n5. 代替エンドポイントテスト...")
    test_alternative_endpoints(api_key)

def test_basic_connection(api_key):
    """基本接続テスト"""
    try:
        # 最もシンプルなエンドポイント
        url = f"https://financialmodelingprep.com/api/v3/profile/AAPL?apikey={api_key}"
        response = requests.get(url, timeout=10)
        
        print(f"  ステータスコード: {response.status_code}")
        print(f"  レスポンスヘッダー: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            if data:
                print(f"  ✅ 基本接続成功: {data[0].get('companyName', 'N/A')}")
            else:
                print("  ⚠️ 空のレスポンス")
        else:
            print(f"  ❌ 接続失敗: {response.text}")
            
    except Exception as e:
        print(f"  ❌ 例外発生: {e}")

def test_api_key_validation(api_key):
    """APIキー検証"""
    try:
        # APIキー検証用エンドポイント
        url = f"https://financialmodelingprep.com/api/v4/general_news?page=0&apikey={api_key}"
        response = requests.get(url, timeout=10)
        
        print(f"  ステータスコード: {response.status_code}")
        
        if response.status_code == 200:
            print("  ✅ APIキー有効")
        elif response.status_code == 403:
            print("  ❌ APIキー無効または権限不足")
            print(f"  レスポンス: {response.text}")
        elif response.status_code == 429:
            print("  ⚠️ レート制限に達している")
        else:
            print(f"  ❌ 予期しないエラー: {response.text}")
            
    except Exception as e:
        print(f"  ❌ 例外発生: {e}")

def test_plan_limits(api_key):
    """プランと制限の確認"""
    try:
        # 複数のエンドポイントで制限を調査
        endpoints_to_test = [
            ("基本プロファイル", f"https://financialmodelingprep.com/api/v3/profile/AAPL?apikey={api_key}"),
            ("株価履歴", f"https://financialmodelingprep.com/api/v3/historical-price-full/AAPL?apikey={api_key}"),
            ("決算カレンダー", f"https://financialmodelingprep.com/api/v3/earnings-calendar?from=2024-01-01&to=2024-01-02&apikey={api_key}"),
            ("決算履歴", f"https://financialmodelingprep.com/api/v3/historical/earning_calendar/AAPL?apikey={api_key}")
        ]
        
        for name, url in endpoints_to_test:
            try:
                response = requests.get(url, timeout=10)
                status = "✅ 利用可能" if response.status_code == 200 else f"❌ {response.status_code}"
                print(f"  {name}: {status}")
                
                if response.status_code == 403:
                    print(f"    詳細: {response.text}")
                    
            except Exception as e:
                print(f"  {name}: ❌ エラー - {e}")
                
    except Exception as e:
        print(f"  全体エラー: {e}")

def test_available_endpoints(api_key):
    """利用可能なエンドポイントの確認"""
    
    # Starterプランで利用可能なエンドポイント
    starter_endpoints = [
        ("Company Profile", f"https://financialmodelingprep.com/api/v3/profile/AAPL?apikey={api_key}"),
        ("Stock Price", f"https://financialmodelingprep.com/api/v3/quote/AAPL?apikey={api_key}"),
        ("Financial News", f"https://financialmodelingprep.com/api/v3/stock_news?tickers=AAPL&limit=5&apikey={api_key}")
    ]
    
    print("  Starterプラン相当の機能テスト:")
    for name, url in starter_endpoints:
        try:
            response = requests.get(url, timeout=10)
            status = "✅" if response.status_code == 200 else f"❌ {response.status_code}"
            print(f"    {name}: {status}")
        except Exception as e:
            print(f"    {name}: ❌ {e}")

def test_alternative_endpoints(api_key):
    """代替エンドポイントのテスト"""
    
    # 決算データ取得の代替手段
    alternatives = [
        ("Earnings (v3)", f"https://financialmodelingprep.com/api/v3/earnings/AAPL?apikey={api_key}"),
        ("Income Statement", f"https://financialmodelingprep.com/api/v3/income-statement/AAPL?apikey={api_key}"),
        ("Key Metrics", f"https://financialmodelingprep.com/api/v3/key-metrics/AAPL?apikey={api_key}")
    ]
    
    print("  決算関連の代替エンドポイント:")
    working_endpoints = []
    
    for name, url in alternatives:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                print(f"    ✅ {name}: 利用可能")
                working_endpoints.append((name, url))
                
                # サンプルデータ確認
                data = response.json()
                if data and isinstance(data, list) and len(data) > 0:
                    sample = data[0]
                    print(f"      サンプル: {list(sample.keys())[:5]}")
            else:
                print(f"    ❌ {name}: {response.status_code}")
        except Exception as e:
            print(f"    ❌ {name}: {e}")
    
    return working_endpoints

def suggest_solutions():
    """解決策の提案"""
    print("\n" + "="*60)
    print("🔍 403エラーの考えられる原因と解決策:")
    print()
    
    print("【原因1】プラン不足")
    print("  - 現在: Starterプラン ($19/月)")
    print("  - 必要: Premium以上 ($49/月)")
    print("  - 解決: FMPでプランアップグレード")
    print()
    
    print("【原因2】APIキーの問題")
    print("  - 無効なAPIキー")
    print("  - 期限切れ")
    print("  - 解決: FMPダッシュボードで確認")
    print()
    
    print("【原因3】エンドポイント制限")
    print("  - earnings-calendar がプレミアム機能")
    print("  - 解決: 代替エンドポイント使用")
    print()
    
    print("【推奨対応】")
    print("1. FMPダッシュボードでプラン確認")
    print("2. Premium プランへアップグレード")
    print("3. 一時的に代替エンドポイント使用")

if __name__ == "__main__":
    debug_fmp_api()
    suggest_solutions()