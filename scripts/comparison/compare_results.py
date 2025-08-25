#!/usr/bin/env python3
"""
動的ポジションサイズ vs 固定ポジションサイズの比較分析
"""
import pandas as pd
import numpy as np

# CSVファイルを読み込み
breadth_8ma = pd.read_csv('reports/earnings_backtest_2025_01_01_2025_06_30_breadth_8ma.csv')
before = pd.read_csv('reports/earnings_backtest_2025_01_01_2025_06_30_before.csv')

print('=== バックテスト結果比較分析 ===')
print('期間: 2025-01-01 to 2025-06-30')
print()

print('📊 基本統計:')
print(f'Dynamic Position (breadth_8ma): {len(breadth_8ma)} トレード')
print(f'Fixed Position (before):        {len(before)} トレード')
print()

# 基本メトリクス計算
def calc_metrics(df, name):
    total_pnl = df['pnl'].sum()
    win_rate = len(df[df['pnl'] > 0]) / len(df) * 100
    avg_pnl = df['pnl'].mean()
    avg_win = df[df['pnl'] > 0]['pnl'].mean() if len(df[df['pnl'] > 0]) > 0 else 0
    avg_loss = df[df['pnl'] < 0]['pnl'].mean() if len(df[df['pnl'] < 0]) > 0 else 0
    avg_holding = df['holding_period'].mean()
    
    print(f'{name}:')
    print(f'  総P&L:        ${total_pnl:,.2f}')
    print(f'  勝率:         {win_rate:.1f}%')
    print(f'  平均P&L:      ${avg_pnl:,.2f}')
    print(f'  平均勝ち:     ${avg_win:,.2f}')
    print(f'  平均負け:     ${avg_loss:,.2f}')
    print(f'  平均保有期間: {avg_holding:.1f}日')
    print()
    
    return {
        'total_pnl': total_pnl,
        'win_rate': win_rate,
        'avg_pnl': avg_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'avg_holding': avg_holding
    }

metrics_breadth = calc_metrics(breadth_8ma, 'Dynamic Position (breadth_8ma)')
metrics_before = calc_metrics(before, 'Fixed Position (before)')

# 改善分析
print('📈 改善分析:')
pnl_improvement = metrics_breadth['total_pnl'] - metrics_before['total_pnl']
pnl_improvement_pct = (pnl_improvement / abs(metrics_before['total_pnl'])) * 100 if metrics_before['total_pnl'] != 0 else 0
win_rate_improvement = metrics_breadth['win_rate'] - metrics_before['win_rate']

print(f'総P&L改善:     ${pnl_improvement:,.2f} ({pnl_improvement_pct:+.1f}%)')
print(f'勝率改善:      {win_rate_improvement:+.1f}ポイント')
print(f'トレード数差:  {len(breadth_8ma) - len(before)} ({((len(breadth_8ma) - len(before))/len(before)*100):+.1f}%)')
print()

# ポジションサイズ分析
print('💰 ポジションサイズ分析:')
breadth_shares = breadth_8ma['shares'].describe()
before_shares = before['shares'].describe()

print(f'Dynamic Position:')
print(f'  平均株数: {breadth_shares["mean"]:.0f}')
print(f'  最小株数: {breadth_shares["min"]:.0f}')
print(f'  最大株数: {breadth_shares["max"]:.0f}')
print()
print(f'Fixed Position:')
print(f'  平均株数: {before_shares["mean"]:.0f}')
print(f'  最小株数: {before_shares["min"]:.0f}')
print(f'  最大株数: {before_shares["max"]:.0f}')
print()

shares_ratio = breadth_shares['mean'] / before_shares['mean']
print(f'平均ポジションサイズ比率: {shares_ratio:.2f}x')
print()

# 同一銘柄比較
print('🔍 同一銘柄での比較:')
common_trades = []
for _, b_row in breadth_8ma.iterrows():
    matching = before[(before['ticker'] == b_row['ticker']) & 
                     (before['entry_date'] == b_row['entry_date'])]
    if len(matching) > 0:
        f_row = matching.iloc[0]
        common_trades.append({
            'ticker': b_row['ticker'],
            'entry_date': b_row['entry_date'],
            'breadth_shares': b_row['shares'],
            'before_shares': f_row['shares'],
            'breadth_pnl': b_row['pnl'],
            'before_pnl': f_row['pnl'],
            'shares_ratio': b_row['shares'] / f_row['shares'],
            'pnl_improvement': b_row['pnl'] - f_row['pnl']
        })

if common_trades:
    common_df = pd.DataFrame(common_trades)
    print(f'共通トレード数: {len(common_df)}')
    print(f'平均株数比率: {common_df["shares_ratio"].mean():.2f}x')
    print(f'平均P&L改善: ${common_df["pnl_improvement"].mean():,.2f}')
    print()
    
    print('共通トレード詳細 (上位10件):')
    common_df_sorted = common_df.sort_values('pnl_improvement', ascending=False)
    for _, row in common_df_sorted.head(10).iterrows():
        print(f'  {row["ticker"]} ({row["entry_date"]}): '
              f'{row["shares_ratio"]:.2f}x株数, '
              f'${row["pnl_improvement"]:+,.0f} P&L改善')
else:
    print('共通トレードが見つかりません')

print()

# 動的ポジション特有のトレード分析
breadth_only = []
before_only = []

breadth_keys = set(breadth_8ma['ticker'] + '_' + breadth_8ma['entry_date'])
before_keys = set(before['ticker'] + '_' + before['entry_date'])

breadth_only_keys = breadth_keys - before_keys
before_only_keys = before_keys - breadth_keys

print('🆕 動的ポジション特有のトレード:')
if breadth_only_keys:
    # 正しくフィルタリング
    breadth_trade_ids = breadth_8ma['ticker'] + '_' + breadth_8ma['entry_date']
    breadth_only_trades = breadth_8ma[breadth_trade_ids.isin(breadth_only_keys)]
    print(f'件数: {len(breadth_only_trades)}')
    print(f'総P&L: ${breadth_only_trades["pnl"].sum():,.2f}')
    print('上位5件:')
    for _, row in breadth_only_trades.nlargest(5, 'pnl').iterrows():
        print(f'  {row["ticker"]} ({row["entry_date"]}): ${row["pnl"]:+,.0f}')
else:
    print('特有のトレードなし')

print()
print('🆕 固定ポジション特有のトレード:')
if before_only_keys:
    # 正しくフィルタリング
    before_trade_ids = before['ticker'] + '_' + before['entry_date']
    before_only_trades = before[before_trade_ids.isin(before_only_keys)]
    print(f'件数: {len(before_only_trades)}')
    print(f'総P&L: ${before_only_trades["pnl"].sum():,.2f}')
    print('上位5件:')
    for _, row in before_only_trades.nlargest(5, 'pnl').iterrows():
        print(f'  {row["ticker"]} ({row["entry_date"]}): ${row["pnl"]:+,.0f}')
else:
    print('特有のトレードなし')

print()
print('🎯 結論:')
if pnl_improvement > 0:
    print(f'✅ Dynamic Position Size (breadth_8ma) が ${pnl_improvement:,.2f} の改善を実現')
    print(f'   改善率: {pnl_improvement_pct:+.1f}%')
    print(f'   主要因: 平均ポジションサイズ {shares_ratio:.2f}x による利益拡大')
else:
    print(f'❌ Dynamic Position Size で ${abs(pnl_improvement):,.2f} の悪化')
    print(f'   悪化率: {pnl_improvement_pct:.1f}%')

# リスク分析
print()
print('⚠️ リスク分析:')
breadth_losses = breadth_8ma[breadth_8ma['pnl'] < 0]['pnl']
before_losses = before[before['pnl'] < 0]['pnl']

print(f'Dynamic Position 最大損失: ${breadth_losses.min():,.2f}')
print(f'Fixed Position 最大損失:   ${before_losses.min():,.2f}')
print(f'平均損失 (Dynamic):       ${breadth_losses.mean():,.2f}')
print(f'平均損失 (Fixed):         ${before_losses.mean():,.2f}')