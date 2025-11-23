import pandas as pd
import numpy as np
from datetime import datetime

# Load CSV files
df_stop6 = pd.read_csv('reports/earnings_backtest_2020_09_01_2025_06_30_all_stop6.csv')
df_stop8 = pd.read_csv('reports/earnings_backtest_2020_09_01_2025_06_30_all_stop8.csv')

# Convert date columns
df_stop6['entry_date'] = pd.to_datetime(df_stop6['entry_date'])
df_stop6['exit_date'] = pd.to_datetime(df_stop6['exit_date'])
df_stop8['entry_date'] = pd.to_datetime(df_stop8['entry_date'])
df_stop8['exit_date'] = pd.to_datetime(df_stop8['exit_date'])

# Calculate returns
df_stop6['return_pct'] = df_stop6['pnl_rate'] * 100
df_stop8['return_pct'] = df_stop8['pnl_rate'] * 100

print("="*70)
print("Stop Loss 6% vs 8% バックテスト結果分析")
print("="*70)

print("\n【基本統計比較】")
print(f"{'項目':<25} {'Stop Loss 6%':>15} {'Stop Loss 8%':>15} {'差異':>15}")
print("-"*70)
print(f"{'トレード数':<25} {len(df_stop6):>15} {len(df_stop8):>15} {len(df_stop6)-len(df_stop8):>15}")
print(f"{'勝率':<25} {(df_stop6['pnl'] > 0).mean()*100:>14.1f}% {(df_stop8['pnl'] > 0).mean()*100:>14.1f}% {(df_stop6['pnl'] > 0).mean()*100 - (df_stop8['pnl'] > 0).mean()*100:>14.1f}%")
print(f"{'総利益($)':<25} {df_stop6['pnl'].sum():>15,.2f} {df_stop8['pnl'].sum():>15,.2f} {df_stop6['pnl'].sum() - df_stop8['pnl'].sum():>15,.2f}")
print(f"{'平均リターン(%)':<25} {df_stop6['return_pct'].mean():>14.2f}% {df_stop8['return_pct'].mean():>14.2f}% {df_stop6['return_pct'].mean() - df_stop8['return_pct'].mean():>14.2f}%")
print(f"{'中央値リターン(%)':<25} {df_stop6['return_pct'].median():>14.2f}% {df_stop8['return_pct'].median():>14.2f}% {df_stop6['return_pct'].median() - df_stop8['return_pct'].median():>14.2f}%")
print(f"{'標準偏差(%)':<25} {df_stop6['return_pct'].std():>14.2f}% {df_stop8['return_pct'].std():>14.2f}% {df_stop6['return_pct'].std() - df_stop8['return_pct'].std():>14.2f}%")

print("\n【Exit Reason分析】")
print("\nStop Loss 6%:")
exit_reasons_6 = df_stop6['exit_reason'].value_counts()
for reason, count in exit_reasons_6.items():
    print(f"  {reason}: {count} ({count/len(df_stop6)*100:.1f}%)")

print("\nStop Loss 8%:")
exit_reasons_8 = df_stop8['exit_reason'].value_counts()
for reason, count in exit_reasons_8.items():
    print(f"  {reason}: {count} ({count/len(df_stop8)*100:.1f}%)")

# Stop lossによる損失分析
stop_loss_exits_6 = df_stop6[df_stop6['exit_reason'].isin(['stop_loss', 'stop_loss_intraday'])]
stop_loss_exits_8 = df_stop8[df_stop8['exit_reason'].isin(['stop_loss', 'stop_loss_intraday'])]

print("\n【Stop Loss退場分析】")
print(f"Stop Loss 6%: {len(stop_loss_exits_6)}件 ({len(stop_loss_exits_6)/len(df_stop6)*100:.1f}%)")
print(f"Stop Loss 8%: {len(stop_loss_exits_8)}件 ({len(stop_loss_exits_8)/len(df_stop8)*100:.1f}%)")
print(f"差: {len(stop_loss_exits_6) - len(stop_loss_exits_8)}件")

# 勝敗分析
winners_6 = df_stop6[df_stop6['pnl'] > 0]
losers_6 = df_stop6[df_stop6['pnl'] <= 0]
winners_8 = df_stop8[df_stop8['pnl'] > 0]
losers_8 = df_stop8[df_stop8['pnl'] <= 0]

print("\n【勝敗トレード詳細分析】")
print(f"{'項目':<25} {'Stop Loss 6%':>15} {'Stop Loss 8%':>15} {'差異':>15}")
print("-"*70)
print(f"{'勝ちトレード数':<25} {len(winners_6):>15} {len(winners_8):>15} {len(winners_6)-len(winners_8):>15}")
print(f"{'負けトレード数':<25} {len(losers_6):>15} {len(losers_8):>15} {len(losers_6)-len(losers_8):>15}")
print(f"{'平均勝ち幅(%)':<25} {winners_6['return_pct'].mean():>14.2f}% {winners_8['return_pct'].mean():>14.2f}% {winners_6['return_pct'].mean() - winners_8['return_pct'].mean():>14.2f}%")
print(f"{'平均負け幅(%)':<25} {losers_6['return_pct'].mean():>14.2f}% {losers_8['return_pct'].mean():>14.2f}% {losers_6['return_pct'].mean() - losers_8['return_pct'].mean():>14.2f}%")
print(f"{'最大勝ち幅(%)':<25} {winners_6['return_pct'].max():>14.2f}% {winners_8['return_pct'].max():>14.2f}% {winners_6['return_pct'].max() - winners_8['return_pct'].max():>14.2f}%")
print(f"{'最大負け幅(%)':<25} {losers_6['return_pct'].min():>14.2f}% {losers_8['return_pct'].min():>14.2f}% {losers_6['return_pct'].min() - losers_8['return_pct'].min():>14.2f}%")

# リスクリワード比
risk_reward_6 = abs(winners_6['return_pct'].mean() / losers_6['return_pct'].mean())
risk_reward_8 = abs(winners_8['return_pct'].mean() / losers_8['return_pct'].mean())
print(f"{'リスクリワード比':<25} {risk_reward_6:>14.2f}x {risk_reward_8:>14.2f}x {risk_reward_6 - risk_reward_8:>14.2f}x")

# 保有期間分析
print("\n【保有期間分析】")
print(f"{'項目':<25} {'Stop Loss 6%':>15} {'Stop Loss 8%':>15} {'差異':>15}")
print("-"*70)
print(f"{'平均保有期間(日)':<25} {df_stop6['holding_period'].mean():>14.1f} {df_stop8['holding_period'].mean():>14.1f} {df_stop6['holding_period'].mean() - df_stop8['holding_period'].mean():>14.1f}")
print(f"{'中央値保有期間(日)':<25} {df_stop6['holding_period'].median():>14.1f} {df_stop8['holding_period'].median():>14.1f} {df_stop6['holding_period'].median() - df_stop8['holding_period'].median():>14.1f}")
print(f"{'勝ちトレード平均(日)':<25} {winners_6['holding_period'].mean():>14.1f} {winners_8['holding_period'].mean():>14.1f} {winners_6['holding_period'].mean() - winners_8['holding_period'].mean():>14.1f}")
print(f"{'負けトレード平均(日)':<25} {losers_6['holding_period'].mean():>14.1f} {losers_8['holding_period'].mean():>14.1f} {losers_6['holding_period'].mean() - losers_8['holding_period'].mean():>14.1f}")

# 年別分析
df_stop6['year'] = df_stop6['entry_date'].dt.year
df_stop8['year'] = df_stop8['entry_date'].dt.year

print("\n【年別パフォーマンス比較】")
years = sorted(set(df_stop6['year'].unique()) | set(df_stop8['year'].unique()))
print(f"{'年':<10} {'SL6% 利益($)':>15} {'SL8% 利益($)':>15} {'差額($)':>15} {'SL6% 勝率':>10} {'SL8% 勝率':>10}")
print("-"*80)

yearly_analysis = {}
for year in years:
    year_data_6 = df_stop6[df_stop6['year'] == year]
    year_data_8 = df_stop8[df_stop8['year'] == year]
    
    pnl_6 = year_data_6['pnl'].sum() if len(year_data_6) > 0 else 0
    pnl_8 = year_data_8['pnl'].sum() if len(year_data_8) > 0 else 0
    wr_6 = (year_data_6['pnl'] > 0).mean() * 100 if len(year_data_6) > 0 else 0
    wr_8 = (year_data_8['pnl'] > 0).mean() * 100 if len(year_data_8) > 0 else 0
    
    yearly_analysis[year] = {
        'pnl_6': pnl_6,
        'pnl_8': pnl_8,
        'diff': pnl_6 - pnl_8,
        'wr_6': wr_6,
        'wr_8': wr_8
    }
    
    print(f"{year:<10} {pnl_6:>15,.2f} {pnl_8:>15,.2f} {pnl_6-pnl_8:>15,.2f} {wr_6:>9.1f}% {wr_8:>9.1f}%")

# 同じトレードの比較
merged = pd.merge(
    df_stop6[['ticker', 'entry_date', 'exit_date', 'pnl', 'return_pct', 'exit_reason', 'holding_period']], 
    df_stop8[['ticker', 'entry_date', 'exit_date', 'pnl', 'return_pct', 'exit_reason', 'holding_period']], 
    on=['ticker', 'entry_date'], 
    suffixes=('_6', '_8'),
    how='outer',
    indicator=True
)

both_trades = merged[merged['_merge'] == 'both'].copy()
only_6 = merged[merged['_merge'] == 'left_only']
only_8 = merged[merged['_merge'] == 'right_only']

print(f"\n【トレードの一致性分析】")
print(f"両方に存在: {len(both_trades)}件")
print(f"6%のみ: {len(only_6)}件")  
print(f"8%のみ: {len(only_8)}件")

# Exit reasonが異なるトレード
different_exit = both_trades[both_trades['exit_reason_6'] != both_trades['exit_reason_8']]
print(f"\nExit Reasonが異なるトレード: {len(different_exit)}件")

# 6%でstop lossしたが8%では継続したトレード
sl_6_survived_8 = different_exit[
    (different_exit['exit_reason_6'].isin(['stop_loss', 'stop_loss_intraday'])) &
    (~different_exit['exit_reason_8'].isin(['stop_loss', 'stop_loss_intraday']))
]

print(f"\n【6% Stop Lossで退場、8%は継続したトレード】: {len(sl_6_survived_8)}件")
if len(sl_6_survived_8) > 0:
    profit_diff = sl_6_survived_8['pnl_8'] - sl_6_survived_8['pnl_6']
    print(f"  合計利益差: ${profit_diff.sum():,.2f}")
    print(f"  平均利益差: ${profit_diff.mean():,.2f}")
    
    turned_winner = sl_6_survived_8[sl_6_survived_8['pnl_8'] > 0]
    print(f"  8%で最終的に勝利: {len(turned_winner)}件 ({len(turned_winner)/len(sl_6_survived_8)*100:.1f}%)")

# 8%でstop lossしたが6%では継続したトレード（逆パターン）
sl_8_survived_6 = different_exit[
    (different_exit['exit_reason_8'].isin(['stop_loss', 'stop_loss_intraday'])) &
    (~different_exit['exit_reason_6'].isin(['stop_loss', 'stop_loss_intraday']))
]

print(f"\n【8% Stop Lossで退場、6%は継続したトレード】: {len(sl_8_survived_6)}件")
if len(sl_8_survived_6) > 0:
    profit_diff_rev = sl_8_survived_6['pnl_6'] - sl_8_survived_6['pnl_8']
    print(f"  合計利益差: ${profit_diff_rev.sum():,.2f}")
    print(f"  平均利益差: ${profit_diff_rev.mean():,.2f}")

# 大きな差が出たトレード
both_trades['pnl_diff'] = both_trades['pnl_6'] - both_trades['pnl_8']
top_diff_positive = both_trades.nlargest(5, 'pnl_diff')[['ticker', 'entry_date', 'pnl_6', 'pnl_8', 'pnl_diff', 'exit_reason_6', 'exit_reason_8']]
top_diff_negative = both_trades.nsmallest(5, 'pnl_diff')[['ticker', 'entry_date', 'pnl_6', 'pnl_8', 'pnl_diff', 'exit_reason_6', 'exit_reason_8']]

print("\n【6%が有利だったトップ5トレード】")
print(top_diff_positive.to_string(index=False))

print("\n【8%が有利だったトップ5トレード】")
print(top_diff_negative.to_string(index=False))

# 月別累積リターン分析
df_stop6['month'] = df_stop6['exit_date'].dt.to_period('M')
df_stop8['month'] = df_stop8['exit_date'].dt.to_period('M')

monthly_returns_6 = df_stop6.groupby('month')['pnl'].sum()
monthly_returns_8 = df_stop8.groupby('month')['pnl'].sum()

# 最大ドローダウン分析
def calculate_max_drawdown(returns, initial_capital=100000):
    cumulative = initial_capital + returns.cumsum()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max * 100
    return drawdown.min()

max_dd_6 = calculate_max_drawdown(monthly_returns_6)
max_dd_8 = calculate_max_drawdown(monthly_returns_8)

print("\n【リスク指標】")
print(f"最大ドローダウン 6%: {max_dd_6:.2f}%")
print(f"最大ドローダウン 8%: {max_dd_8:.2f}%")

print("\n" + "="*70)
print("【重要な発見と洞察】")
print("="*70)

print(f"\n1. パフォーマンス逆転の謎:")
print(f"   - 6%の総利益: ${df_stop6['pnl'].sum():,.2f}")
print(f"   - 8%の総利益: ${df_stop8['pnl'].sum():,.2f}")
print(f"   - 差額: ${df_stop6['pnl'].sum() - df_stop8['pnl'].sum():,.2f} (6%が優位)")

print(f"\n2. トレード数の影響:")
print(f"   - 6%は{len(df_stop6) - len(df_stop8)}件多くトレード実行")
print(f"   - これにより追加の利益機会を獲得")

print(f"\n3. Stop Loss効果の非線形性:")
stop_loss_rate_6 = len(stop_loss_exits_6) / len(df_stop6) * 100
stop_loss_rate_8 = len(stop_loss_exits_8) / len(df_stop8) * 100
print(f"   - 6% Stop Loss率: {stop_loss_rate_6:.1f}%")
print(f"   - 8% Stop Loss率: {stop_loss_rate_8:.1f}%")
print(f"   - 6%は早期退場が多いが、より多くの機会でエントリー")

# 最も差が出た年を特定
max_diff_year = max(yearly_analysis.items(), key=lambda x: abs(x[1]['diff']))
print(f"\n4. 最も差が出た年: {max_diff_year[0]}年")
print(f"   - 差額: ${max_diff_year[1]['diff']:,.2f}")
if max_diff_year[1]['diff'] > 0:
    print(f"   - 6%が優位")
else:
    print(f"   - 8%が優位")

print(f"\n5. 結論:")
print("   6% > 8%の結果になった理由:")
print("   - より多くのトレード機会（トレード数の増加効果）")
print("   - 早期Exit可能性の増大（機会損失は犠牲にして確実性重視）")
print("   - 特定の市場環境で6%のStop Lossが効果的だった期間がある")
print("   ※ただし勝率は8%の方が高く、質vs量のトレードオフが発生")