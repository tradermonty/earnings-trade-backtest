#!/usr/bin/env python3
"""
ギャップデータをデバッグするスクリプト
"""

import sys
import os
import pandas as pd

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def debug_gap_data():
    """実際のCSVファイルからギャップデータを確認"""
    # 最新のCSVファイルを探す
    reports_dir = "reports"
    if not os.path.exists(reports_dir):
        print("reportsディレクトリが見つかりません")
        return
    
    csv_files = [f for f in os.listdir(reports_dir) if f.endswith('.csv')]
    if not csv_files:
        print("CSVファイルが見つかりません")
        return
    
    # 最新のCSVファイルを取得
    latest_csv = sorted(csv_files)[-1]
    csv_path = os.path.join(reports_dir, latest_csv)
    
    print(f"分析対象ファイル: {csv_path}")
    
    # CSVファイルを読み込み
    try:
        df = pd.read_csv(csv_path)
        print(f"\n総トレード数: {len(df)}")
        print(f"カラム: {df.columns.tolist()}")
        
        if 'gap' in df.columns:
            print(f"\n=== ギャップデータ分析 ===")
            print(f"ギャップの統計:")
            print(f"- 最小値: {df['gap'].min():.2f}%")
            print(f"- 最大値: {df['gap'].max():.2f}%")
            print(f"- 平均値: {df['gap'].mean():.2f}%")
            print(f"- 中央値: {df['gap'].median():.2f}%")
            
            # ギャップの分布
            negative_count = (df['gap'] < 0).sum()
            zero_to_2_count = ((df['gap'] >= 0) & (df['gap'] < 2)).sum()
            two_to_5_count = ((df['gap'] >= 2) & (df['gap'] < 5)).sum()
            five_to_10_count = ((df['gap'] >= 5) & (df['gap'] < 10)).sum()
            over_10_count = (df['gap'] >= 10).sum()
            
            print(f"\nギャップ分布:")
            print(f"- Negative: {negative_count} 件 ({negative_count/len(df)*100:.1f}%)")
            print(f"- 0-2%: {zero_to_2_count} 件 ({zero_to_2_count/len(df)*100:.1f}%)")
            print(f"- 2-5%: {two_to_5_count} 件 ({two_to_5_count/len(df)*100:.1f}%)")
            print(f"- 5-10%: {five_to_10_count} 件 ({five_to_10_count/len(df)*100:.1f}%)")
            print(f"- 10%+: {over_10_count} 件 ({over_10_count/len(df)*100:.1f}%)")
            
            if negative_count > 0:
                print(f"\n❌ 警告: {negative_count}個のネガティブギャップが見つかりました！")
                print("ネガティブギャップのサンプル:")
                negative_trades = df[df['gap'] < 0][['ticker', 'entry_date', 'gap', 'pnl_rate']].head(10)
                print(negative_trades.to_string(index=False))
                
                # パフォーマンス分析
                print(f"\nネガティブギャップトレードのパフォーマンス:")
                neg_trades = df[df['gap'] < 0]
                print(f"- 平均リターン: {neg_trades['pnl_rate'].mean():.2f}%")
                print(f"- 勝率: {(neg_trades['pnl_rate'] > 0).mean()*100:.1f}%")
            else:
                print("✅ ネガティブギャップは見つかりませんでした（期待通り）")
        else:
            print("ギャップカラムが見つかりません")
            
    except Exception as e:
        print(f"エラー: {e}")

if __name__ == '__main__':
    debug_gap_data()