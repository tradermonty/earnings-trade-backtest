import pandas as pd
import numpy as np

# 実際のCSVファイルを分析
csv_path = "/Users/takueisaotome/PycharmProjects/earnings-trade-backtest/data/market_breadth_data_20250817_ma8.csv"
df = pd.read_csv(csv_path)

print("="*80)
print("Market Breadth CSV ファイル構造分析")
print("="*80)

print(f"\n【基本情報】")
print(f"データ期間: {df['Date'].iloc[0]} ～ {df['Date'].iloc[-1]}")
print(f"総レコード数: {len(df):,}件")
print(f"期間: {(pd.to_datetime(df['Date'].iloc[-1]) - pd.to_datetime(df['Date'].iloc[0])).days:,}日")

print(f"\n【列構造】")
for i, col in enumerate(df.columns, 1):
    print(f"{i:2}. {col}")

print(f"\n【各列の統計情報】")
print(f"{'列名':<25} {'データ型':<10} {'Min':>10} {'Max':>10} {'Mean':>10} {'Null数':>8}")
print("-"*80)

for col in df.columns:
    if col == 'Date':
        print(f"{col:<25} {'datetime':<10} {'':>10} {'':>10} {'':>10} {df[col].isnull().sum():>8}")
    elif df[col].dtype in ['bool']:
        true_count = df[col].sum()
        false_count = len(df) - true_count
        print(f"{col:<25} {'bool':<10} {f'F:{false_count}':>10} {f'T:{true_count}':>10} {'':>10} {df[col].isnull().sum():>8}")
    elif df[col].dtype in ['int64', 'float64']:
        print(f"{col:<25} {str(df[col].dtype):<10} {df[col].min():>10.3f} {df[col].max():>10.3f} {df[col].mean():>10.3f} {df[col].isnull().sum():>8}")
    else:
        unique_count = df[col].nunique()
        print(f"{col:<25} {str(df[col].dtype):<10} {'':>10} {'':>10} {f'Uniq:{unique_count}':>10} {df[col].isnull().sum():>8}")

print(f"\n【重要な指標の分布】")

# Breadth_Index_8MA の分布分析
breadth_8ma = df['Breadth_Index_8MA']
print(f"\nBreadth_Index_8MA の分布:")
print(f"  < 0.3: {(breadth_8ma < 0.3).sum():,}件 ({(breadth_8ma < 0.3).mean()*100:.1f}%)")
print(f"  0.3-0.4: {((breadth_8ma >= 0.3) & (breadth_8ma < 0.4)).sum():,}件 ({((breadth_8ma >= 0.3) & (breadth_8ma < 0.4)).mean()*100:.1f}%)")
print(f"  0.4-0.6: {((breadth_8ma >= 0.4) & (breadth_8ma < 0.6)).sum():,}件 ({((breadth_8ma >= 0.4) & (breadth_8ma < 0.6)).mean()*100:.1f}%)")
print(f"  0.6-0.7: {((breadth_8ma >= 0.6) & (breadth_8ma < 0.7)).sum():,}件 ({((breadth_8ma >= 0.6) & (breadth_8ma < 0.7)).mean()*100:.1f}%)")
print(f"  0.7-0.8: {((breadth_8ma >= 0.7) & (breadth_8ma < 0.8)).sum():,}件 ({((breadth_8ma >= 0.7) & (breadth_8ma < 0.8)).mean()*100:.1f}%)")
print(f"  >= 0.8: {(breadth_8ma >= 0.8).sum():,}件 ({(breadth_8ma >= 0.8).mean()*100:.1f}%)")

print(f"\n【特殊フラグの分析】")
print(f"Bearish_Signal: {df['Bearish_Signal'].sum():,}件 ({df['Bearish_Signal'].mean()*100:.1f}%)")
print(f"Is_Peak: {df['Is_Peak'].sum():,}件 ({df['Is_Peak'].mean()*100:.1f}%)")
print(f"Is_Trough: {df['Is_Trough'].sum():,}件 ({df['Is_Trough'].mean()*100:.1f}%)")
print(f"Is_Trough_8MA_Below_04: {df['Is_Trough_8MA_Below_04'].sum():,}件 ({df['Is_Trough_8MA_Below_04'].mean()*100:.1f}%)")

# バックテスト期間との重複確認
print(f"\n【バックテスト期間との重複確認】")
backtest_start = "2020-09-01"
backtest_end = "2025-06-30"

df['Date'] = pd.to_datetime(df['Date'])
backtest_data = df[(df['Date'] >= backtest_start) & (df['Date'] <= backtest_end)]

print(f"バックテスト期間 ({backtest_start} ～ {backtest_end}):")
print(f"  該当データ: {len(backtest_data):,}件")
print(f"  データ欠損: {len(backtest_data) == 0}")

if len(backtest_data) > 0:
    print(f"  実際の期間: {backtest_data['Date'].min().strftime('%Y-%m-%d')} ～ {backtest_data['Date'].max().strftime('%Y-%m-%d')}")
    
    # バックテスト期間での分布
    bt_breadth = backtest_data['Breadth_Index_8MA']
    print(f"\n  バックテスト期間での分布:")
    print(f"    < 0.3: {(bt_breadth < 0.3).sum():,}件 ({(bt_breadth < 0.3).mean()*100:.1f}%)")
    print(f"    0.3-0.4: {((bt_breadth >= 0.3) & (bt_breadth < 0.4)).sum():,}件 ({((bt_breadth >= 0.3) & (bt_breadth < 0.4)).mean()*100:.1f}%)")
    print(f"    0.4-0.7: {((bt_breadth >= 0.4) & (bt_breadth < 0.7)).sum():,}件 ({((bt_breadth >= 0.4) & (bt_breadth < 0.7)).mean()*100:.1f}%)")
    print(f"    >= 0.7: {(bt_breadth >= 0.7).sum():,}件 ({(bt_breadth >= 0.7).mean()*100:.1f}%)")

# 追加の有用情報
print(f"\n【追加活用可能な情報】")
print(f"1. S&P500_Price: S&P500指数の価格データ（相関分析等に活用可能）")
print(f"2. Breadth_Index_Raw: 生のBreadth Index（平滑化前データ）")
print(f"3. Breadth_200MA_Trend: 200MA傾向 (-1: 下降, 0: 横ばい, 1: 上昇)")
print(f"4. Bearish_Signal: 弱気シグナル（追加フィルターとして活用可能）")
print(f"5. Is_Peak/Is_Trough: 市場のピーク・ボトム（エントリータイミング最適化）")
print(f"6. Is_Trough_8MA_Below_04: 8MA < 0.4でのボトム（極度ストレス期の特定）")

# 実用的な組み合わせ提案
print(f"\n【実用的な活用方法の提案】")
print(f"1. 基本モード: Breadth_Index_8MA のみを使用")
print(f"2. 拡張モード: Breadth_Index_8MA + Bearish_Signal")
print(f"3. 高度モード: Peak/Trough情報も考慮したタイミング調整")
print(f"4. フィルターモード: 200MA_Trend方向性も考慮")

print(f"\n【設計上の考慮点】")
print(f"1. 列名の更新: 'Breadth_Index_8MA' → 実装では 'breadth_8ma' として正規化")
print(f"2. Boolean列の処理: 文字列('True'/'False') → Python bool型への変換")
print(f"3. 日付形式: 'YYYY-MM-DD' 形式で統一済み（変換不要）")
print(f"4. 欠損データ: 現在のデータセットには欠損なし")

# サンプルデータの表示
print(f"\n【サンプルデータ】")
print("最初の5件:")
print(df[['Date', 'Breadth_Index_8MA', 'Bearish_Signal', 'Is_Peak', 'Is_Trough']].head())
print("\n最後の5件:")
print(df[['Date', 'Breadth_Index_8MA', 'Bearish_Signal', 'Is_Peak', 'Is_Trough']].tail())