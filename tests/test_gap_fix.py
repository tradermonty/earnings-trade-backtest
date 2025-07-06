#!/usr/bin/env python3
"""
ギャップチャートの修正をテスト
"""

import sys
import os
import pandas as pd

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.analysis_engine import AnalysisEngine
from src.data_fetcher import DataFetcher

def test_gap_chart_fix():
    """ギャップチャートの修正をテスト"""
    # 最新のCSVファイルを読み込み
    reports_dir = "reports"
    csv_files = [f for f in os.listdir(reports_dir) if f.endswith('.csv')]
    latest_csv = sorted(csv_files)[-1]
    csv_path = os.path.join(reports_dir, latest_csv)
    
    print(f"テスト対象: {csv_path}")
    df = pd.read_csv(csv_path)
    
    print(f"元のギャップ統計:")
    print(f"- 範囲: {df['gap'].min():.2f}% ～ {df['gap'].max():.2f}%")
    print(f"- ネガティブ数: {(df['gap'] < 0).sum()}")
    
    # AnalysisEngineでテスト
    data_fetcher = DataFetcher()
    analysis_engine = AnalysisEngine(data_fetcher)
    
    # ギャップパフォーマンスチャート生成
    print(f"\n=== ギャップパフォーマンスチャート生成 ===")
    
    # セクター情報を追加（必要な前処理）
    df_with_sector = analysis_engine._add_sector_info(df)
    
    # ギャップチャート生成
    gap_chart_html = analysis_engine._create_gap_performance_chart(df_with_sector)
    
    print(f"チャートHTML生成完了: {len(gap_chart_html)} 文字")
    
    # HTMLに'Negative'が含まれているかチェック
    if 'Negative' in gap_chart_html:
        print("❌ まだ'Negative'カテゴリが含まれています")
        # 詳細な調査
        lines = gap_chart_html.split('\n')
        negative_lines = [line for line in lines if 'Negative' in line]
        print("'Negative'を含む行:")
        for line in negative_lines[:3]:  # 最初の3行のみ表示
            print(f"  {line.strip()}")
    else:
        print("✅ 'Negative'カテゴリは除外されました")
    
    # 実際のデータ分析
    print(f"\n=== 実際のデータ分析 ===")
    
    # ギャップ範囲の作成
    df_with_sector['gap_range'] = pd.cut(df_with_sector['gap'], 
                                       bins=[-float('inf'), 0, 2, 5, 10, float('inf')],
                                       labels=['Negative', '0-2%', '2-5%', '5-10%', '10%+'])
    
    gap_perf = df_with_sector.groupby('gap_range', observed=True).agg({
        'pnl_rate': ['mean', 'count'],
        'pnl': 'sum'
    }).round(2)
    
    gap_perf.columns = ['avg_return', 'trade_count', 'total_pnl']
    
    print("修正前の集計（すべてのカテゴリ）:")
    print(gap_perf.to_string())
    
    # 修正後（取引数0のカテゴリを除外）
    gap_perf_filtered = gap_perf[gap_perf['trade_count'] > 0]
    
    print(f"\n修正後の集計（取引数>0のみ）:")
    print(gap_perf_filtered.to_string())
    
    print(f"\n除外されたカテゴリ:")
    excluded = gap_perf[gap_perf['trade_count'] == 0]
    if len(excluded) > 0:
        print(excluded.to_string())
    else:
        print("なし")

if __name__ == '__main__':
    test_gap_chart_fix()