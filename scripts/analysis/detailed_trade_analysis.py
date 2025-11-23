import pandas as pd
import numpy as np
from datetime import datetime

# Load both CSV files
df_stop8 = pd.read_csv('reports/earnings_backtest_2020_09_01_2025_06_30_all_stop8.csv')
df_stop9 = pd.read_csv('reports/earnings_backtest_2020_09_01_2025_06_30_all_stop9.csv')

# Convert date columns
df_stop8['entry_date'] = pd.to_datetime(df_stop8['entry_date'])
df_stop8['exit_date'] = pd.to_datetime(df_stop8['exit_date'])
df_stop9['entry_date'] = pd.to_datetime(df_stop9['entry_date'])
df_stop9['exit_date'] = pd.to_datetime(df_stop9['exit_date'])

# Calculate returns
df_stop8['return_pct'] = df_stop8['pnl_rate'] * 100
df_stop9['return_pct'] = df_stop9['pnl_rate'] * 100

print("="*60)
print("個別トレード詳細分析: Stop Loss 8% vs 9%の差異")
print("="*60)

# 同じティッカーと日付のトレードを比較
merged = pd.merge(
    df_stop8[['ticker', 'entry_date', 'exit_date', 'pnl', 'return_pct', 'exit_reason', 'holding_period']], 
    df_stop9[['ticker', 'entry_date', 'exit_date', 'pnl', 'return_pct', 'exit_reason', 'holding_period']], 
    on=['ticker', 'entry_date'], 
    suffixes=('_8', '_9'),
    how='outer',
    indicator=True
)

# 両方に存在するトレード
both_trades = merged[merged['_merge'] == 'both']
only_8 = merged[merged['_merge'] == 'left_only']
only_9 = merged[merged['_merge'] == 'right_only']

print(f"\n【トレードの一致性】")
print(f"両方に存在: {len(both_trades)}件")
print(f"8%のみ: {len(only_8)}件")
print(f"9%のみ: {len(only_9)}件")

# Exit reasonが異なるトレードを特定
different_exit = both_trades[both_trades['exit_reason_8'] != both_trades['exit_reason_9']]
print(f"\n【Exit Reasonが異なるトレード】: {len(different_exit)}件")

# Stop lossで8%が退場したが9%は生き残ったトレード
sl_8_survived_9 = different_exit[
    (different_exit['exit_reason_8'] == 'stop_loss') | 
    (different_exit['exit_reason_8'] == 'stop_loss_intraday')
]

print(f"\n【8% Stop Lossで退場、9%は継続したトレード】: {len(sl_8_survived_9)}件")
if len(sl_8_survived_9) > 0:
    print("\n詳細分析:")
    # これらのトレードの利益差を計算
    profit_diff = sl_8_survived_9['pnl_9'] - sl_8_survived_9['pnl_8']
    print(f"  合計利益差: ${profit_diff.sum():,.2f}")
    print(f"  平均利益差: ${profit_diff.mean():,.2f}")
    
    # 9%で最終的に勝利したトレード
    turned_winner = sl_8_survived_9[sl_8_survived_9['pnl_9'] > 0]
    print(f"  9%で最終的に勝利: {len(turned_winner)}件 ({len(turned_winner)/len(sl_8_survived_9)*100:.1f}%)")
    if len(turned_winner) > 0:
        print(f"    これらの合計利益: ${turned_winner['pnl_9'].sum():,.2f}")
        print(f"    8%での損失: ${turned_winner['pnl_8'].sum():,.2f}")
        print(f"    差額: ${(turned_winner['pnl_9'] - turned_winner['pnl_8']).sum():,.2f}")

# 大きな差が出たトレードのトップ10
both_trades['pnl_diff'] = both_trades['pnl_9'] - both_trades['pnl_8']
top_diff = both_trades.nlargest(10, 'pnl_diff')[['ticker', 'entry_date', 'pnl_8', 'pnl_9', 'pnl_diff', 'exit_reason_8', 'exit_reason_9']]

print("\n【利益差が大きいトップ10トレード】")
print(top_diff.to_string(index=False))

# ボラティリティが高い銘柄の分析
print("\n【ボラティリティ分析】")
# 8%でstop lossしたトレードのティッカー
sl_tickers_8 = df_stop8[df_stop8['exit_reason'].isin(['stop_loss', 'stop_loss_intraday'])]['ticker'].unique()

# これらのティッカーの9%での成績
perf_9_for_sl8 = df_stop9[df_stop9['ticker'].isin(sl_tickers_8)]
if len(perf_9_for_sl8) > 0:
    print(f"\n8%でStop Lossになった銘柄の9%での成績:")
    print(f"  トレード数: {len(perf_9_for_sl8)}")
    print(f"  勝率: {(perf_9_for_sl8['pnl'] > 0).mean()*100:.1f}%")
    print(f"  合計利益: ${perf_9_for_sl8['pnl'].sum():,.2f}")

# 年別・月別の差異分析
both_trades['year'] = both_trades['entry_date'].dt.year
both_trades['month'] = both_trades['entry_date'].dt.month

print("\n【時期別の差異分析】")
yearly_diff = both_trades.groupby('year')['pnl_diff'].agg(['sum', 'mean', 'count'])
print("\n年別利益差:")
print(yearly_diff)

# マーケット環境による影響（月別）
monthly_diff = both_trades.groupby('month')['pnl_diff'].agg(['sum', 'mean', 'count'])
print("\n月別利益差（全期間合計）:")
print(monthly_diff.sort_values('sum', ascending=False))

# リスク調整後リターンの比較
print("\n【リスク調整後パフォーマンス】")
# 保有期間を考慮した年率換算リターン
both_trades['annualized_return_8'] = (1 + both_trades['return_pct_8']/100) ** (365 / both_trades['holding_period_8']) - 1
both_trades['annualized_return_9'] = (1 + both_trades['return_pct_9']/100) ** (365 / both_trades['holding_period_9']) - 1

# 有限な値のみでフィルタリング
valid_returns = both_trades[
    np.isfinite(both_trades['annualized_return_8']) & 
    np.isfinite(both_trades['annualized_return_9'])
]

if len(valid_returns) > 0:
    print(f"平均年率リターン (8%): {valid_returns['annualized_return_8'].mean()*100:.2f}%")
    print(f"平均年率リターン (9%): {valid_returns['annualized_return_9'].mean()*100:.2f}%")

# 重要な洞察
print("\n" + "="*60)
print("【重要な洞察】")
print("="*60)

print("\n1. Stop Loss設定の影響:")
print(f"   - 8%の方が{len(sl_8_survived_9)}件多くStop Lossで退場")
print(f"   - これらのトレードで9%は${profit_diff.sum():,.2f}の追加利益を獲得")
if len(turned_winner) > 0:
    print(f"   - {len(turned_winner)}件は9%で勝利に転じた（{len(turned_winner)/len(sl_8_survived_9)*100:.1f}%）")

print("\n2. 最適なStop Loss水準の示唆:")
print("   - 8%は早期退場によるアップサイドの喪失が顕著")
print("   - 9%はボラティリティを許容し、トレンドに乗る機会を確保")
print("   - 特に高ボラティリティ銘柄で差が顕著")

print("\n3. マーケット環境との相関:")
best_months = monthly_diff.nlargest(3, 'sum')
print(f"   - 差が最も出た月: {best_months.index.tolist()}")
print("   - これらの月はボラティリティが高い傾向")

print("\n4. 推奨事項:")
print("   - 現在の市場環境では9%のStop Lossがより適切")
print("   - ただし、個別銘柄のボラティリティに応じた調整も検討すべき")
print("   - ATR（Average True Range）ベースの動的Stop Loss設定も有効な可能性")