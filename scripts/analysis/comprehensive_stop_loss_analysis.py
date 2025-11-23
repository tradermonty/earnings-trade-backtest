import pandas as pd
import numpy as np

# 3つのStop Loss設定の結果をまとめて分析
def load_and_process_data():
    df_6 = pd.read_csv('reports/earnings_backtest_2020_09_01_2025_06_30_all_stop6.csv')
    df_8 = pd.read_csv('reports/earnings_backtest_2020_09_01_2025_06_30_all_stop8.csv')
    df_9 = pd.read_csv('reports/earnings_backtest_2020_09_01_2025_06_30_all_stop9.csv')
    
    for df in [df_6, df_8, df_9]:
        df['entry_date'] = pd.to_datetime(df['entry_date'])
        df['exit_date'] = pd.to_datetime(df['exit_date'])
        df['return_pct'] = df['pnl_rate'] * 100
        df['year'] = df['entry_date'].dt.year
    
    return df_6, df_8, df_9

df_6, df_8, df_9 = load_and_process_data()

print("="*80)
print("総合Stop Loss分析: 6% vs 8% vs 9%")
print("="*80)

# 基本統計の比較
print("\n【総合パフォーマンス比較】")
print(f"{'指標':<20} {'Stop Loss 6%':>15} {'Stop Loss 8%':>15} {'Stop Loss 9%':>15}")
print("-"*80)
print(f"{'トレード数':<20} {len(df_6):>15} {len(df_8):>15} {len(df_9):>15}")
print(f"{'総利益($)':<20} {df_6['pnl'].sum():>15,.0f} {df_8['pnl'].sum():>15,.0f} {df_9['pnl'].sum():>15,.0f}")
print(f"{'勝率(%)':<20} {(df_6['pnl'] > 0).mean()*100:>14.1f}% {(df_8['pnl'] > 0).mean()*100:>14.1f}% {(df_9['pnl'] > 0).mean()*100:>14.1f}%")
print(f"{'平均リターン(%)':<20} {df_6['return_pct'].mean():>14.1f}% {df_8['return_pct'].mean():>14.1f}% {df_9['return_pct'].mean():>14.1f}%")

# Stop Loss退場率
sl_rate_6 = len(df_6[df_6['exit_reason'].isin(['stop_loss', 'stop_loss_intraday'])]) / len(df_6) * 100
sl_rate_8 = len(df_8[df_8['exit_reason'].isin(['stop_loss', 'stop_loss_intraday'])]) / len(df_8) * 100
sl_rate_9 = len(df_9[df_9['exit_reason'].isin(['stop_loss', 'stop_loss_intraday'])]) / len(df_9) * 100

print(f"{'Stop Loss退場率(%)':<20} {sl_rate_6:>14.1f}% {sl_rate_8:>14.1f}% {sl_rate_9:>14.1f}%")

# 保有期間
print(f"{'平均保有期間(日)':<20} {df_6['holding_period'].mean():>14.1f} {df_8['holding_period'].mean():>14.1f} {df_9['holding_period'].mean():>14.1f}")

print(f"\n【パフォーマンス順位】")
performances = [
    ('Stop Loss 6%', df_6['pnl'].sum()),
    ('Stop Loss 8%', df_8['pnl'].sum()),
    ('Stop Loss 9%', df_9['pnl'].sum())
]
performances.sort(key=lambda x: x[1], reverse=True)

for i, (name, profit) in enumerate(performances, 1):
    print(f"{i}位: {name} - ${profit:,.0f}")

print(f"\n【なぜ 9% > 6% > 8% という結果になったのか？】")

# 年別詳細分析
yearly_stats = {}
for year in range(2020, 2026):
    year_6 = df_6[df_6['year'] == year]
    year_8 = df_8[df_8['year'] == year]
    year_9 = df_9[df_9['year'] == year]
    
    yearly_stats[year] = {
        'profit_6': year_6['pnl'].sum() if len(year_6) > 0 else 0,
        'profit_8': year_8['pnl'].sum() if len(year_8) > 0 else 0,
        'profit_9': year_9['pnl'].sum() if len(year_9) > 0 else 0,
        'trades_6': len(year_6),
        'trades_8': len(year_8),
        'trades_9': len(year_9)
    }

print(f"\n【年別詳細分析】")
print(f"{'年':<6} {'6%利益':>12} {'8%利益':>12} {'9%利益':>12} {'6%勝者':>8} {'8%勝者':>8} {'9%勝者':>8}")
print("-"*80)

for year, stats in yearly_stats.items():
    winner_6 = "★" if stats['profit_6'] >= stats['profit_8'] and stats['profit_6'] >= stats['profit_9'] else ""
    winner_8 = "★" if stats['profit_8'] >= stats['profit_6'] and stats['profit_8'] >= stats['profit_9'] else ""
    winner_9 = "★" if stats['profit_9'] >= stats['profit_6'] and stats['profit_9'] >= stats['profit_8'] else ""
    
    print(f"{year:<6} {stats['profit_6']:>12,.0f} {stats['profit_8']:>12,.0f} {stats['profit_9']:>12,.0f} {winner_6:>8} {winner_8:>8} {winner_9:>8}")

# 重要な発見
print(f"\n【重要な発見】")

# 1. トレード数効果
print(f"\n1. トレード数効果:")
print(f"   - 6%: {len(df_6)}件 (+{len(df_6)-len(df_8)}件 vs 8%)")
print(f"   - 8%: {len(df_8)}件")
print(f"   - 9%: {len(df_9)}件 ({len(df_9)-len(df_8):+}件 vs 8%)")
print(f"   → 6%は最多のトレード機会を獲得")

# 2. 年別勝利分析
winners_by_year = {}
for year in yearly_stats.keys():
    profits = [yearly_stats[year]['profit_6'], yearly_stats[year]['profit_8'], yearly_stats[year]['profit_9']]
    max_profit = max(profits)
    if yearly_stats[year]['profit_6'] == max_profit:
        winner = '6%'
    elif yearly_stats[year]['profit_8'] == max_profit:
        winner = '8%'
    else:
        winner = '9%'
    winners_by_year[year] = winner

print(f"\n2. 年別勝利パターン:")
year_wins = {'6%': 0, '8%': 0, '9%': 0}
for year, winner in winners_by_year.items():
    year_wins[winner] += 1
    print(f"   {year}年: {winner} (利益: ${yearly_stats[year][f'profit_{winner[0]}']:,.0f})")

print(f"\n   年間勝利数: 6%={year_wins['6%']}年, 8%={year_wins['8%']}年, 9%={year_wins['9%']}年")

# 3. 特異な年の分析 (2025年)
print(f"\n3. 2025年の特異性:")
print(f"   - 6%: ${yearly_stats[2025]['profit_6']:,.0f} ({yearly_stats[2025]['trades_6']}件)")
print(f"   - 8%: ${yearly_stats[2025]['profit_8']:,.0f} ({yearly_stats[2025]['trades_8']}件)")
print(f"   - 9%: ${yearly_stats[2025]['profit_9']:,.0f} ({yearly_stats[2025]['trades_9']}件)")
print(f"   → 2025年は6%が圧倒的に有利（部分年データの影響？）")

# 4. リスク調整後分析
def calculate_risk_metrics(df):
    monthly_returns = df.groupby(df['exit_date'].dt.to_period('M'))['pnl'].sum()
    if len(monthly_returns) > 1:
        return_volatility = monthly_returns.std()
        avg_monthly_return = monthly_returns.mean()
        risk_adj_return = avg_monthly_return / return_volatility if return_volatility > 0 else 0
    else:
        risk_adj_return = 0
    return risk_adj_return

risk_adj_6 = calculate_risk_metrics(df_6)
risk_adj_8 = calculate_risk_metrics(df_8)
risk_adj_9 = calculate_risk_metrics(df_9)

print(f"\n4. リスク調整後リターン:")
print(f"   - 6%: {risk_adj_6:.3f}")
print(f"   - 8%: {risk_adj_8:.3f}")
print(f"   - 9%: {risk_adj_9:.3f}")

# 5. Exit reasonの影響分析
print(f"\n5. Exit Strategy効果:")
for i, (name, df) in enumerate([('6%', df_6), ('8%', df_8), ('9%', df_9)]):
    trailing_stop_rate = len(df[df['exit_reason'] == 'trailing_stop']) / len(df) * 100
    print(f"   - {name}: Trailing Stop成功率 {trailing_stop_rate:.1f}%")

print(f"\n【結論とメカニズム解明】")
print("="*80)

print(f"\n9% > 6% > 8% の結果となった複合的要因:")

print(f"\n1. 【9%が最優秀な理由】")
print(f"   - 適度なボラティリティ許容でトレンドフォロー効果最大化")
print(f"   - Stop Loss退場率が最低({sl_rate_9:.1f}%)")
print(f"   - 勝率が最高({(df_9['pnl'] > 0).mean()*100:.1f}%)")

print(f"\n2. 【6%が8%を上回った理由】")
print(f"   - トレード数優位({len(df_6)}件 vs {len(df_8)}件)")
print(f"   - 2025年の異常な好成績(${yearly_stats[2025]['profit_6']:,.0f})")
print(f"   - 早期利確による確実性重視戦略が特定期間で有効")

print(f"\n3. 【8%が中途半端だった理由】")
print(f"   - 6%ほど機会を活かせず、9%ほど成長を待てない")
print(f"   - Stop Loss退場率({sl_rate_8:.1f}%)が6%と9%の中間")
print(f"   - リスク・リターンの最適化点から外れた設定")

print(f"\n4. 【実践的示唆】")
print(f"   - 現在の市場環境では9%が最適")
print(f"   - ただし6%も量的戦略として有効な場面あり")
print(f"   - 8%は避けるべき設定（中途半端な効果）")
print(f"   - 動的なStop Loss調整の検討価値あり")

print(f"\n5. 【注意すべき点】")
print(f"   - 2025年のデータは部分年（〜6月）のため解釈に注意")
print(f"   - マーケット環境変化により最適解は変動する可能性")
print(f"   - トレード数差が結果に大きな影響を与えている")