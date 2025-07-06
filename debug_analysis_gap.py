#!/usr/bin/env python3
"""
AnalysisEngineでのギャップ処理をデバッグ
"""

import sys
import os
import pandas as pd

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.analysis_engine import AnalysisEngine
from src.data_fetcher import DataFetcher

def debug_analysis_gap():
    """AnalysisEngineでのギャップ処理をデバッグ"""
    # 最新のCSVファイルを読み込み
    reports_dir = "reports"
    csv_files = [f for f in os.listdir(reports_dir) if f.endswith('.csv')]
    latest_csv = sorted(csv_files)[-1]
    csv_path = os.path.join(reports_dir, latest_csv)
    
    print(f"読み込み: {csv_path}")
    df = pd.read_csv(csv_path)
    
    print(f"\n=== 元のデータ ===")
    print(f"カラム: {df.columns.tolist()}")
    print(f"gap カラムの存在: {'gap' in df.columns}")
    
    if 'gap' in df.columns:
        print(f"元のギャップ統計:")
        print(f"- 最小値: {df['gap'].min():.2f}%")
        print(f"- 最大値: {df['gap'].max():.2f}%")
        print(f"- 平均値: {df['gap'].mean():.2f}%")
        print(f"- ネガティブ数: {(df['gap'] < 0).sum()}")
    
    # AnalysisEngineを初期化
    data_fetcher = DataFetcher()
    analysis_engine = AnalysisEngine(data_fetcher)
    
    print(f"\n=== セクター情報追加後 ===")
    df_with_sector = analysis_engine._add_sector_info(df)
    print(f"カラム: {df_with_sector.columns.tolist()}")
    print(f"gap カラムの存在: {'gap' in df_with_sector.columns}")
    
    if 'gap' in df_with_sector.columns:
        print(f"セクター追加後のギャップ統計:")
        print(f"- 最小値: {df_with_sector['gap'].min():.2f}%")
        print(f"- 最大値: {df_with_sector['gap'].max():.2f}%")
        print(f"- 平均値: {df_with_sector['gap'].mean():.2f}%")
        print(f"- ネガティブ数: {(df_with_sector['gap'] < 0).sum()}")
    
    print(f"\n=== EPS情報追加後 ===")
    df_with_eps = analysis_engine._add_eps_info(df_with_sector)
    print(f"カラム: {df_with_eps.columns.tolist()}")
    print(f"gap カラムの存在: {'gap' in df_with_eps.columns}")
    
    if 'gap' in df_with_eps.columns:
        print(f"EPS追加後のギャップ統計:")
        print(f"- 最小値: {df_with_eps['gap'].min():.2f}%")
        print(f"- 最大値: {df_with_eps['gap'].max():.2f}%")
        print(f"- 平均値: {df_with_eps['gap'].mean():.2f}%")
        print(f"- ネガティブ数: {(df_with_eps['gap'] < 0).sum()}")
        
        # ネガティブギャップがある場合の詳細
        negative_gaps = df_with_eps[df_with_eps['gap'] < 0]
        if len(negative_gaps) > 0:
            print(f"\n❌ ネガティブギャップ検出: {len(negative_gaps)}件")
            print("詳細:")
            print(negative_gaps[['ticker', 'entry_date', 'gap']].to_string(index=False))
        else:
            print("✅ ネガティブギャップなし")
    
    # ギャップパフォーマンスチャートのデータを確認
    print(f"\n=== ギャップパフォーマンス分析 ===")
    
    # ギャップ範囲の作成
    df_with_eps['gap_range'] = pd.cut(df_with_eps['gap'], 
                                    bins=[-float('inf'), 0, 2, 5, 10, float('inf')],
                                    labels=['Negative', '0-2%', '2-5%', '5-10%', '10%+'])
    
    gap_perf = df_with_eps.groupby('gap_range', observed=True).agg({
        'pnl_rate': ['mean', 'count'],
        'pnl': 'sum'
    }).round(2)
    
    gap_perf.columns = ['avg_return', 'trade_count', 'total_pnl']
    
    print("ギャップパフォーマンス集計:")
    print(gap_perf.to_string())

if __name__ == '__main__':
    debug_analysis_gap()