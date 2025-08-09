#!/usr/bin/env python3
"""
セクター・業種情報統合のテスト
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import pandas as pd
from src.data_fetcher import DataFetcher
from src.analysis_engine import AnalysisEngine

def test_sector_integration():
    """セクター情報統合のテスト"""
    
    print("セクター情報統合テストを開始...")
    
    # テスト用のトレードデータを作成
    test_data = {
        'ticker': ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'MANH', 'TSLA'],
        'pnl': [100, 200, -50, 300, 150, -100],
        'pnl_rate': [5.0, 10.0, -2.5, 15.0, 7.5, -5.0],
        'entry_date': ['2024-01-01'] * 6,
        'exit_date': ['2024-01-05'] * 6,
        'holding_period': [4] * 6
    }
    
    df = pd.DataFrame(test_data)
    print(f"テストデータ作成完了: {len(df)}件")
    
    # DataFetcher初期化（FMP使用）
    try:
        data_fetcher = DataFetcher(use_fmp=True)
        print("FMP DataFetcher初期化完了")
    except Exception as e:
        print(f"DataFetcher初期化エラー: {e}")
        return
    
    # AnalysisEngine初期化
    try:
        analysis_engine = AnalysisEngine(data_fetcher)
        print("AnalysisEngine初期化完了")
    except Exception as e:
        print(f"AnalysisEngine初期化エラー: {e}")
        return
    
    # セクター情報追加テスト
    try:
        print("\nセクター情報の追加を開始...")
        enriched_df = analysis_engine._add_sector_info(df)
        
        print(f"\nセクター情報追加結果:")
        for _, row in enriched_df.iterrows():
            print(f"{row['ticker']}: {row['sector']} - {row['industry']}")
        
        # 結果の検証
        unknown_sectors = enriched_df[enriched_df['sector'] == 'Unknown']
        unknown_industries = enriched_df[enriched_df['industry'] == 'Unknown']
        
        print(f"\n統計:")
        print(f"- 総銘柄数: {len(enriched_df)}")
        print(f"- Unknownセクター: {len(unknown_sectors)}件")
        print(f"- Unknown業種: {len(unknown_industries)}件")
        print(f"- 成功率: {((len(enriched_df) - len(unknown_sectors)) / len(enriched_df) * 100):.1f}%")
        
        if len(unknown_sectors) == 0 and len(unknown_industries) == 0:
            print("✅ セクター・業種情報統合テスト成功！")
        else:
            print("⚠️ 一部の銘柄でセクター・業種情報が取得できませんでした")
            
        return enriched_df
        
    except Exception as e:
        print(f"セクター情報追加エラー: {e}")
        return None

def test_chart_generation(enriched_df):
    """チャート生成のテスト"""
    
    if enriched_df is None:
        print("エンリッチされたデータがないため、チャート生成テストをスキップ")
        return
    
    print(f"\n" + "="*50)
    print("チャート生成テスト")
    print("="*50)
    
    try:
        data_fetcher = DataFetcher(use_fmp=True)
        analysis_engine = AnalysisEngine(data_fetcher)
        
        # セクター別パフォーマンスチャート
        print("\n1. セクター別パフォーマンスチャート生成...")
        sector_chart = analysis_engine._create_sector_performance_chart(enriched_df)
        
        if "セクター情報が利用できません" in sector_chart:
            print("❌ セクター情報が利用できません")
        else:
            print("✅ セクター別パフォーマンスチャート生成成功")
        
        # 業種別パフォーマンスチャート
        print("\n2. 業種別パフォーマンスチャート生成...")
        industry_chart = analysis_engine._create_industry_performance_chart(enriched_df)
        
        if "業界情報が利用できません" in industry_chart:
            print("❌ 業種情報が利用できません")
        else:
            print("✅ 業種別パフォーマンスチャート生成成功")
            
    except Exception as e:
        print(f"チャート生成エラー: {e}")

if __name__ == "__main__":
    enriched_data = test_sector_integration()
    test_chart_generation(enriched_data)
    
    print(f"\n" + "="*50)
    print("テスト完了")
    print("="*50)