import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns

# Load both CSV files
df_stop8 = pd.read_csv('reports/earnings_backtest_2020_09_01_2025_06_30_all_stop8.csv')
df_stop9 = pd.read_csv('reports/earnings_backtest_2020_09_01_2025_06_30_all_stop9.csv')

# Convert date columns
df_stop8['entry_date'] = pd.to_datetime(df_stop8['entry_date'])
df_stop8['exit_date'] = pd.to_datetime(df_stop8['exit_date'])
df_stop9['entry_date'] = pd.to_datetime(df_stop9['entry_date'])
df_stop9['exit_date'] = pd.to_datetime(df_stop9['exit_date'])

# Calculate returns in percentage
df_stop8['return_pct'] = df_stop8['pnl_rate'] * 100
df_stop9['return_pct'] = df_stop9['pnl_rate'] * 100

print("="*60)
print("Stop Loss 8% vs 9% バックテスト結果分析")
print("="*60)

print("\n【基本統計】")
print(f"{'項目':<25} {'Stop Loss 8%':>15} {'Stop Loss 9%':>15} {'差異':>10}")
print("-"*65)
print(f"{'トレード数':<25} {len(df_stop8):>15} {len(df_stop9):>15} {len(df_stop9)-len(df_stop8):>10}")
print(f"{'勝率':<25} {(df_stop8['pnl'] > 0).mean()*100:>14.1f}% {(df_stop9['pnl'] > 0).mean()*100:>14.1f}% {(df_stop9['pnl'] > 0).mean()*100 - (df_stop8['pnl'] > 0).mean()*100:>9.1f}%")
print(f"{'総利益($)':<25} {df_stop8['pnl'].sum():>15,.2f} {df_stop9['pnl'].sum():>15,.2f} {df_stop9['pnl'].sum() - df_stop8['pnl'].sum():>10,.2f}")
print(f"{'平均リターン(%)':<25} {df_stop8['return_pct'].mean():>14.2f}% {df_stop9['return_pct'].mean():>14.2f}% {df_stop9['return_pct'].mean() - df_stop8['return_pct'].mean():>9.2f}%")
print(f"{'中央値リターン(%)':<25} {df_stop8['return_pct'].median():>14.2f}% {df_stop9['return_pct'].median():>14.2f}% {df_stop9['return_pct'].median() - df_stop8['return_pct'].median():>9.2f}%")
print(f"{'標準偏差(%)':<25} {df_stop8['return_pct'].std():>14.2f}% {df_stop9['return_pct'].std():>14.2f}% {df_stop9['return_pct'].std() - df_stop8['return_pct'].std():>9.2f}%")

# Exit reason analysis
print("\n【Exit Reason分析】")
print("\nStop Loss 8%:")
exit_reasons_8 = df_stop8['exit_reason'].value_counts()
for reason, count in exit_reasons_8.items():
    print(f"  {reason}: {count} ({count/len(df_stop8)*100:.1f}%)")

print("\nStop Loss 9%:")
exit_reasons_9 = df_stop9['exit_reason'].value_counts()
for reason, count in exit_reasons_9.items():
    print(f"  {reason}: {count} ({count/len(df_stop9)*100:.1f}%)")

# Stop lossによる損失回避の分析
stop_loss_exits_8 = df_stop8[df_stop8['exit_reason'] == 'stop_loss']
stop_loss_exits_9 = df_stop9[df_stop9['exit_reason'] == 'stop_loss']

print("\n【Stop Lossによる退場分析】")
print(f"Stop Loss 8%: {len(stop_loss_exits_8)}件 ({len(stop_loss_exits_8)/len(df_stop8)*100:.1f}%)")
print(f"Stop Loss 9%: {len(stop_loss_exits_9)}件 ({len(stop_loss_exits_9)/len(df_stop9)*100:.1f}%)")
print(f"差: {len(stop_loss_exits_8) - len(stop_loss_exits_9)}件")

# 勝ちトレードと負けトレードの分析
winners_8 = df_stop8[df_stop8['pnl'] > 0]
losers_8 = df_stop8[df_stop8['pnl'] <= 0]
winners_9 = df_stop9[df_stop9['pnl'] > 0]
losers_9 = df_stop9[df_stop9['pnl'] <= 0]

print("\n【勝敗トレード分析】")
print(f"{'項目':<25} {'Stop Loss 8%':>15} {'Stop Loss 9%':>15}")
print("-"*55)
print(f"{'勝ちトレード数':<25} {len(winners_8):>15} {len(winners_9):>15}")
print(f"{'負けトレード数':<25} {len(losers_8):>15} {len(losers_9):>15}")
print(f"{'平均勝ち幅(%)':<25} {winners_8['return_pct'].mean():>14.2f}% {winners_9['return_pct'].mean():>14.2f}%")
print(f"{'平均負け幅(%)':<25} {losers_8['return_pct'].mean():>14.2f}% {losers_9['return_pct'].mean():>14.2f}%")
print(f"{'最大勝ち幅(%)':<25} {winners_8['return_pct'].max():>14.2f}% {winners_9['return_pct'].max():>14.2f}%")
print(f"{'最大負け幅(%)':<25} {losers_8['return_pct'].min():>14.2f}% {losers_9['return_pct'].min():>14.2f}%")

# リスクリワード比
risk_reward_8 = abs(winners_8['return_pct'].mean() / losers_8['return_pct'].mean())
risk_reward_9 = abs(winners_9['return_pct'].mean() / losers_9['return_pct'].mean())
print(f"{'リスクリワード比':<25} {risk_reward_8:>14.2f}x {risk_reward_9:>14.2f}x")

# 保有期間の分析
print("\n【保有期間分析】")
print(f"{'項目':<25} {'Stop Loss 8%':>15} {'Stop Loss 9%':>15}")
print("-"*55)
print(f"{'平均保有期間(日)':<25} {df_stop8['holding_period'].mean():>14.1f} {df_stop9['holding_period'].mean():>14.1f}")
print(f"{'中央値保有期間(日)':<25} {df_stop8['holding_period'].median():>14.1f} {df_stop9['holding_period'].median():>14.1f}")
print(f"{'勝ちトレード平均(日)':<25} {winners_8['holding_period'].mean():>14.1f} {winners_9['holding_period'].mean():>14.1f}")
print(f"{'負けトレード平均(日)':<25} {losers_8['holding_period'].mean():>14.1f} {losers_9['holding_period'].mean():>14.1f}")

# 年別パフォーマンス比較
df_stop8['year'] = df_stop8['entry_date'].dt.year
df_stop9['year'] = df_stop9['entry_date'].dt.year

print("\n【年別パフォーマンス比較】")
years = sorted(set(df_stop8['year'].unique()) | set(df_stop9['year'].unique()))
print(f"{'年':<10} {'SL8% 利益($)':>15} {'SL9% 利益($)':>15} {'差額($)':>15} {'SL8% 勝率':>10} {'SL9% 勝率':>10}")
print("-"*80)

for year in years:
    year_data_8 = df_stop8[df_stop8['year'] == year]
    year_data_9 = df_stop9[df_stop9['year'] == year]
    
    pnl_8 = year_data_8['pnl'].sum() if len(year_data_8) > 0 else 0
    pnl_9 = year_data_9['pnl'].sum() if len(year_data_9) > 0 else 0
    wr_8 = (year_data_8['pnl'] > 0).mean() * 100 if len(year_data_8) > 0 else 0
    wr_9 = (year_data_9['pnl'] > 0).mean() * 100 if len(year_data_9) > 0 else 0
    
    print(f"{year:<10} {pnl_8:>15,.2f} {pnl_9:>15,.2f} {pnl_9-pnl_8:>15,.2f} {wr_8:>9.1f}% {wr_9:>9.1f}%")

# 月別累積リターンの計算
df_stop8['month'] = df_stop8['exit_date'].dt.to_period('M')
df_stop9['month'] = df_stop9['exit_date'].dt.to_period('M')

monthly_returns_8 = df_stop8.groupby('month')['pnl'].sum()
monthly_returns_9 = df_stop9.groupby('month')['pnl'].sum()

cumulative_8 = monthly_returns_8.cumsum()
cumulative_9 = monthly_returns_9.cumsum()

# 初期資産を100000と仮定
initial_capital = 100000
cumulative_value_8 = initial_capital + cumulative_8
cumulative_value_9 = initial_capital + cumulative_9

# 最大ドローダウンの計算
def calculate_max_drawdown(cumulative_values):
    running_max = cumulative_values.expanding().max()
    drawdown = (cumulative_values - running_max) / running_max * 100
    return drawdown.min()

max_dd_8 = calculate_max_drawdown(cumulative_value_8)
max_dd_9 = calculate_max_drawdown(cumulative_value_9)

print("\n【リスク指標】")
print(f"{'最大ドローダウン':<25} {max_dd_8:>14.2f}% {max_dd_9:>14.2f}%")

# シャープレシオの計算（簡易版：リスクフリーレートを0と仮定）
monthly_ret_8 = monthly_returns_8 / initial_capital
monthly_ret_9 = monthly_returns_9 / initial_capital
sharpe_8 = (monthly_ret_8.mean() / monthly_ret_8.std()) * np.sqrt(12) if monthly_ret_8.std() != 0 else 0
sharpe_9 = (monthly_ret_9.mean() / monthly_ret_9.std()) * np.sqrt(12) if monthly_ret_9.std() != 0 else 0

print(f"{'シャープレシオ(年換算)':<25} {sharpe_8:>14.2f} {sharpe_9:>14.2f}")

# 重要な差異のまとめ
print("\n" + "="*60)
print("【分析結果サマリー】")
print("="*60)

print("\n1. パフォーマンスの差異要因:")
print(f"   - Stop Loss 9%は8%より総利益が${df_stop9['pnl'].sum() - df_stop8['pnl'].sum():,.2f}多い")
print(f"   - 勝率は9%の方が{(df_stop9['pnl'] > 0).mean()*100 - (df_stop8['pnl'] > 0).mean()*100:.1f}%高い")
print(f"   - Stop Lossによる退場が{len(stop_loss_exits_8) - len(stop_loss_exits_9)}件少ない")

print("\n2. リスク・リターン特性:")
print(f"   - 9%の方が平均負け幅が{losers_9['return_pct'].mean() - losers_8['return_pct'].mean():.2f}%大きい（より大きな損失を許容）")
print(f"   - しかし、勝ちトレードが{len(winners_9) - len(winners_8)}件多く、総合的にプラス")
print(f"   - リスクリワード比は9%が{risk_reward_9:.2f}x、8%が{risk_reward_8:.2f}x")

print("\n3. 最も差が出た年:")
yearly_diff = {}
for year in years:
    year_data_8 = df_stop8[df_stop8['year'] == year]
    year_data_9 = df_stop9[df_stop9['year'] == year]
    pnl_8 = year_data_8['pnl'].sum() if len(year_data_8) > 0 else 0
    pnl_9 = year_data_9['pnl'].sum() if len(year_data_9) > 0 else 0
    yearly_diff[year] = pnl_9 - pnl_8

top_years = sorted(yearly_diff.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
for year, diff in top_years:
    print(f"   - {year}年: ${diff:,.2f}の差")

print("\n4. 結論:")
print("   Stop Loss 9%の方が優れた結果を示した理由:")
print("   - より多くのトレードに勝利の機会を与えた")
print("   - 一時的な下落で退場せず、回復の可能性を残した")
print("   - トレンドフォローの観点から、より適切なリスク許容度だった")