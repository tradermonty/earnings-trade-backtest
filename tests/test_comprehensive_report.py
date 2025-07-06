#!/usr/bin/env python3
"""
レポート機能の包括的テスト - 全分析項目の検証
"""

import sys
import os
import pandas as pd

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.analysis_engine import AnalysisEngine
from src.data_fetcher import DataFetcher

def test_comprehensive_report():
    """全分析項目の包括的テスト"""
    # 最新のCSVファイルを読み込み
    reports_dir = "reports"
    csv_files = [f for f in os.listdir(reports_dir) if f.endswith('.csv')]
    latest_csv = sorted(csv_files)[-1]
    csv_path = os.path.join(reports_dir, latest_csv)
    
    print(f"テスト対象: {csv_path}")
    df = pd.read_csv(csv_path)
    
    print(f"\n=== 基本データ統計 ===")
    print(f"取引数: {len(df)}")
    print(f"カラム: {df.columns.tolist()}")
    
    # 重要なカラムの統計情報
    numeric_cols = ['gap', 'pnl', 'pnl_rate']
    for col in numeric_cols:
        if col in df.columns:
            print(f"\n{col} 統計:")
            print(f"  範囲: {df[col].min():.2f} ～ {df[col].max():.2f}")
            print(f"  平均: {df[col].mean():.2f}")
            print(f"  欠損値: {df[col].isna().sum()}")
    
    # AnalysisEngineでテスト
    data_fetcher = DataFetcher()
    analysis_engine = AnalysisEngine(data_fetcher)
    
    print(f"\n=== 分析チャート生成テスト ===")
    
    # セクター情報追加
    print("1. セクター情報追加...")
    df_with_sector = analysis_engine._add_sector_info(df)
    print(f"  完了: {len(df_with_sector)} 行")
    
    # EPS情報追加
    print("2. EPS情報追加...")
    df_enriched = analysis_engine._add_eps_info(df_with_sector)
    print(f"  完了: {len(df_enriched)} 行")
    print(f"  新規カラム: {set(df_enriched.columns) - set(df.columns)}")
    
    # 各分析チャートのテスト
    chart_methods = [
        ('月次パフォーマンス', '_create_monthly_performance_chart'),
        ('セクター別パフォーマンス', '_create_sector_performance_chart'),
        ('業界別パフォーマンス', '_create_industry_performance_chart'),
        ('ギャップサイズ別パフォーマンス', '_create_gap_performance_chart'),
        ('決算前トレンド別パフォーマンス', '_create_pre_earnings_performance_chart'),
        ('出来高トレンド', '_create_volume_trend_chart'),
        ('MA200分析', '_create_ma200_analysis_chart'),
        ('MA50分析', '_create_ma50_analysis_chart'),
        ('EPSサプライズ', '_create_eps_surprise_chart'),
        ('EPS成長率', '_create_eps_growth_chart'),
        ('EPS成長加速', '_create_eps_acceleration_chart'),
    ]
    
    chart_results = {}
    
    for chart_name, method_name in chart_methods:
        print(f"\n3. {chart_name}チャート生成...")
        try:
            method = getattr(analysis_engine, method_name)
            chart_html = method(df_enriched)
            chart_results[chart_name] = chart_html
            
            # 基本的な検証
            if chart_html and len(chart_html) > 100:
                print(f"  ✅ 成功: {len(chart_html)} 文字")
                
                # 空カテゴリの問題をチェック
                problem_indicators = ['Negative', '0 trades', 'No data', 'undefined']
                found_problems = []
                for indicator in problem_indicators:
                    if indicator in chart_html and 'trade_count' in chart_html:
                        # より詳細にチェック
                        lines = chart_html.split('\n')
                        problem_lines = [line for line in lines if indicator in line and ('0' in line or 'null' in line)]
                        if problem_lines:
                            found_problems.append(indicator)
                
                if found_problems:
                    print(f"  ⚠️  潜在的問題: {found_problems}")
                else:
                    print(f"  ✅ 空カテゴリ問題なし")
                    
            else:
                print(f"  ❌ 失敗: チャート生成エラー")
                chart_results[chart_name] = None
                
        except Exception as e:
            print(f"  ❌ エラー: {str(e)}")
            chart_results[chart_name] = None
    
    # pd.cutを使用しているチャートの詳細分析
    print(f"\n=== pd.cut使用チャートの詳細分析 ===")
    
    cut_charts = [
        ('ギャップサイズ別', 'gap', [-float('inf'), 0, 2, 5, 10, float('inf')], ['Negative', '0-2%', '2-5%', '5-10%', '10%+']),
        ('決算前トレンド別', 'pre_earnings_change', [-float('inf'), -20, -10, 0, 10, 20, float('inf')], ['<-20%', '-20~-10%', '-10~0%', '0~10%', '10~20%', '>20%']),
        ('出来高トレンド', 'volume_ratio', [0, 1.5, 2.0, 3.0, 4.0, float('inf')], ['1.0-1.5x', '1.5-2.0x', '2.0-3.0x', '3.0-4.0x', '4.0x+']),
        ('MA200分析', 'price_to_ma200', [0, 0.9, 1.0, 1.1, 1.2, float('inf')], ['<90%', '90-100%', '100-110%', '110-120%', '>120%']),
        ('MA50分析', 'price_to_ma50', [0, 0.95, 1.0, 1.05, 1.1, float('inf')], ['<95%', '95-100%', '100-105%', '105-110%', '>110%']),
    ]
    
    for chart_name, column, bins, labels in cut_charts:
        print(f"\n{chart_name} ({column}):")
        
        if column in df_enriched.columns:
            # データ範囲
            col_data = df_enriched[column]
            print(f"  データ範囲: {col_data.min():.3f} ～ {col_data.max():.3f}")
            print(f"  欠損値: {col_data.isna().sum()}")
            
            # カテゴリ分割
            try:
                categories = pd.cut(col_data, bins=bins, labels=labels)
                cat_counts = categories.value_counts()
                print(f"  カテゴリ分布:")
                for cat, count in cat_counts.items():
                    print(f"    {cat}: {count} 件")
                
                # 空カテゴリの確認
                empty_cats = [label for label in labels if label not in cat_counts.index or cat_counts[label] == 0]
                if empty_cats:
                    print(f"  ❌ 空カテゴリ: {empty_cats}")
                else:
                    print(f"  ✅ 空カテゴリなし")
                    
            except Exception as e:
                print(f"  ❌ カテゴリ分割エラー: {str(e)}")
        else:
            print(f"  ❌ カラム '{column}' が存在しません")
    
    # 成功率の集計
    successful_charts = sum(1 for result in chart_results.values() if result is not None)
    total_charts = len(chart_results)
    
    print(f"\n=== 総合結果 ===")
    print(f"成功したチャート: {successful_charts}/{total_charts}")
    print(f"成功率: {successful_charts/total_charts*100:.1f}%")
    
    if successful_charts == total_charts:
        print("✅ 全チャート生成成功")
    else:
        failed_charts = [name for name, result in chart_results.items() if result is None]
        print(f"❌ 失敗したチャート: {failed_charts}")
    
    return chart_results

if __name__ == '__main__':
    test_comprehensive_report()