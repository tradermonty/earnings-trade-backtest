#!/usr/bin/env python3
"""
FMP APIでセクター・業種情報取得方法の調査
"""

import os
import requests
import json
from dotenv import load_dotenv
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from fmp_data_fetcher import FMPDataFetcher

def test_fmp_endpoints():
    """FMP APIのセクター・業種データ取得エンドポイントをテスト"""
    
    load_dotenv()
    fmp_key = os.getenv('FMP_API_KEY')
    
    if not fmp_key:
        print("FMP_API_KEY が設定されていません")
        return
    
    # テスト銘柄リスト
    test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'MANH', 'TSLA']
    
    print("="*60)
    print("FMP APIセクター・業種データ調査")
    print("="*60)
    
    for symbol in test_symbols:
        print(f"\n--- {symbol} の情報取得 ---")
        
        # 1. Company Profile API
        print(f"\n1. Company Profile API:")
        profile_url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}?apikey={fmp_key}"
        
        try:
            response = requests.get(profile_url)
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    company = data[0]
                    print(f"   - Company Name: {company.get('companyName', 'N/A')}")
                    print(f"   - Sector: {company.get('sector', 'N/A')}")
                    print(f"   - Industry: {company.get('industry', 'N/A')}")
                    print(f"   - Exchange: {company.get('exchangeShortName', 'N/A')}")
                    print(f"   - Market Cap: ${company.get('mktCap', 0):,}")
                else:
                    print("   - データなし")
            else:
                print(f"   - エラー: {response.status_code}")
        except Exception as e:
            print(f"   - 例外: {e}")
        
        # 2. Company Quote API  
        print(f"\n2. Company Quote API:")
        quote_url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={fmp_key}"
        
        try:
            response = requests.get(quote_url)
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    quote = data[0]
                    print(f"   - Name: {quote.get('name', 'N/A')}")
                    print(f"   - Exchange: {quote.get('exchange', 'N/A')}")
                    # Quoteにはセクター情報がない場合が多い
                else:
                    print("   - データなし")
            else:
                print(f"   - エラー: {response.status_code}")
        except Exception as e:
            print(f"   - 例外: {e}")
        
        # 3. Search API (追加情報があるかチェック)
        print(f"\n3. Search API:")
        search_url = f"https://financialmodelingprep.com/api/v3/search?query={symbol}&apikey={fmp_key}"
        
        try:
            response = requests.get(search_url)
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    for item in data:
                        if item.get('symbol') == symbol:
                            print(f"   - Name: {item.get('name', 'N/A')}")
                            print(f"   - Exchange: {item.get('exchangeShortName', 'N/A')}")
                            break
                else:
                    print("   - データなし")
            else:
                print(f"   - エラー: {response.status_code}")
        except Exception as e:
            print(f"   - 例外: {e}")

def test_fmp_fetcher_integration():
    """既存のFMPDataFetcherでセクター情報取得をテスト"""
    
    print(f"\n" + "="*60)
    print("FMPDataFetcher統合テスト")
    print("="*60)
    
    try:
        fetcher = FMPDataFetcher()
        test_symbols = ['AAPL', 'MSFT', 'MANH', 'NVDA']
        
        for symbol in test_symbols:
            print(f"\n--- {symbol} ---")
            profile = fetcher.get_company_profile(symbol)
            
            if profile:
                print(f"Company: {profile.get('companyName', 'N/A')}")
                print(f"Sector: {profile.get('sector', 'N/A')}")
                print(f"Industry: {profile.get('industry', 'N/A')}")
                print(f"Market Cap: ${profile.get('mktCap', 0):,}")
                print(f"Exchange: {profile.get('exchangeShortName', 'N/A')}")
            else:
                print("プロファイル取得失敗")
                
    except Exception as e:
        print(f"FMPDataFetcher初期化エラー: {e}")

def investigate_sector_endpoints():
    """セクター関連の追加エンドポイントを調査"""
    
    load_dotenv()
    fmp_key = os.getenv('FMP_API_KEY')
    
    print(f"\n" + "="*60)
    print("セクター関連エンドポイント調査")
    print("="*60)
    
    # セクター一覧取得
    print(f"\n1. セクター一覧:")
    sectors_url = f"https://financialmodelingprep.com/api/v3/stock/sectors-performance?apikey={fmp_key}"
    
    try:
        response = requests.get(sectors_url)
        if response.status_code == 200:
            data = response.json()
            if data:
                print("利用可能なセクター:")
                for sector in data[:10]:  # 最初の10件
                    print(f"   - {sector.get('sector', 'N/A')}: {sector.get('changesPercentage', 0):.2f}%")
            else:
                print("   - データなし")
        else:
            print(f"   - エラー: {response.status_code}")
    except Exception as e:
        print(f"   - 例外: {e}")
    
    # 業種一覧取得  
    print(f"\n2. 業種別パフォーマンス:")
    industries_url = f"https://financialmodelingprep.com/api/v3/industry_price_earning_ratio?apikey={fmp_key}"
    
    try:
        response = requests.get(industries_url)
        if response.status_code == 200:
            data = response.json()
            if data:
                print("利用可能な業種:")
                for industry in data[:10]:  # 最初の10件
                    print(f"   - {industry.get('industry', 'N/A')}")
            else:
                print("   - データなし")
        else:
            print(f"   - エラー: {response.status_code}")
    except Exception as e:
        print(f"   - 例外: {e}")

def check_current_issue():
    """現在のシステムでセクター情報がUnknownになる原因を調査"""
    
    print(f"\n" + "="*60)
    print("現在の問題調査")
    print("="*60)
    
    # データフェッチャーの確認
    try:
        from data_fetcher import DataFetcher
        
        # FMP使用時
        print("\n1. FMP DataFetcher確認:")
        data_fetcher = DataFetcher(use_fmp=True)
        if hasattr(data_fetcher, 'fmp_fetcher') and data_fetcher.fmp_fetcher:
            print("   - FMP DataFetcher正常に初期化済み")
            
            # テスト銘柄でプロファイル取得
            test_profile = data_fetcher.fmp_fetcher.get_company_profile('AAPL')
            if test_profile:
                print(f"   - AAPL Sector: {test_profile.get('sector', 'MISSING')}")
                print(f"   - AAPL Industry: {test_profile.get('industry', 'MISSING')}")
            else:
                print("   - テストプロファイル取得失敗")
        else:
            print("   - FMP DataFetcher初期化失敗")
            
        # EODHD使用時
        print("\n2. EODHD DataFetcher確認:")
        data_fetcher_eodhd = DataFetcher(use_fmp=False)
        print("   - EODHD DataFetcher初期化済み（セクター情報なし想定）")
        
    except Exception as e:
        print(f"DataFetcher確認エラー: {e}")

if __name__ == "__main__":
    print("FMP セクター・業種データ取得調査を開始...")
    
    # 各調査の実行
    test_fmp_endpoints()
    test_fmp_fetcher_integration() 
    investigate_sector_endpoints()
    check_current_issue()
    
    print(f"\n" + "="*60)
    print("調査完了")
    print("="*60)