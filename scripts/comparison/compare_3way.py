#!/usr/bin/env python3
"""
3者比較分析: Fixed Position vs breadth_8ma vs bottom_3stage
"""
import pandas as pd
import numpy as np

# CSVファイルを読み込み
before = pd.read_csv('reports/earnings_backtest_2025_01_01_2025_06_30_before.csv')
breadth_8ma = pd.read_csv('reports/earnings_backtest_2025_01_01_2025_06_30_breadth_8ma.csv')
bottom_3stage = pd.read_csv('reports/earnings_backtest_2025_01_01_2025_06_30_bottom_3stage.csv')

print('=== 3者比較分析: Fixed vs breadth_8ma vs bottom_3stage ===')
print('期間: 2025-01-01 to 2025-06-30')
print()

# 基本メトリクス計算
def calc_metrics(df, name):
    total_pnl = df['pnl'].sum()
    win_rate = len(df[df['pnl'] > 0]) / len(df) * 100 if len(df) > 0 else 0
    avg_pnl = df['pnl'].mean()
    avg_win = df[df['pnl'] > 0]['pnl'].mean() if len(df[df['pnl'] > 0]) > 0 else 0
    avg_loss = df[df['pnl'] < 0]['pnl'].mean() if len(df[df['pnl'] < 0]) > 0 else 0
    avg_holding = df['holding_period'].mean()
    max_loss = df['pnl'].min()
    max_win = df['pnl'].max()
    
    # ラグが-10で「nan」になったtrades（ストップロス）の数を計算
    stop_loss_trades = len(df[df['exit_reason'] == 'stop_loss'])
    partial_profit_trades = len(df[df['exit_reason'] == 'partial_profit'])
    
    print(f'{name}:')
    print(f'  トレード数:   {len(df)}')
    print(f'  総P&L:        ${total_pnl:,.2f}')
    print(f'  勝率:         {win_rate:.1f}%')
    print(f'  平均P&L:      ${avg_pnl:,.2f}')
    print(f'  平均勝ち:     ${avg_win:,.2f}')
    print(f'  平均負け:     ${avg_loss:,.2f}')
    print(f'  最大勝ち:     ${max_win:,.2f}')
    print(f'  最大負け:     ${max_loss:,.2f}')
    print(f'  平均保有期間: {avg_holding:.1f}日')
    print(f'  ストップロス: {stop_loss_trades}件')
    print(f'  部分利確:     {partial_profit_trades}件')
    print()
    
    return {
        'total_pnl': total_pnl,
        'win_rate': win_rate,
        'avg_pnl': avg_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'max_win': max_win,
        'max_loss': max_loss,
        'avg_holding': avg_holding,
        'trades': len(df),
        'stop_loss': stop_loss_trades
    }

print('📊 基本統計:')
print('=' * 60)
metrics_before = calc_metrics(before, '1. Fixed Position')
metrics_breadth = calc_metrics(breadth_8ma, '2. Dynamic (breadth_8ma)')
metrics_bottom = calc_metrics(bottom_3stage, '3. Dynamic (bottom_3stage)')

# 改善率の計算
print('📈 Fixed Positionからの改善率:')
print('=' * 60)

def print_improvement(base_metrics, target_metrics, name):
    pnl_imp = target_metrics['total_pnl'] - base_metrics['total_pnl']
    pnl_imp_pct = (pnl_imp / abs(base_metrics['total_pnl'])) * 100 if base_metrics['total_pnl'] != 0 else 0
    win_rate_imp = target_metrics['win_rate'] - base_metrics['win_rate']
    trade_diff = target_metrics['trades'] - base_metrics['trades']
    
    print(f'{name}:')
    print(f'  総P&L改善:    ${pnl_imp:,.2f} ({pnl_imp_pct:+.1f}%)')
    print(f'  勝率変化:     {win_rate_imp:+.1f}ポイント')
    print(f'  トレード数差: {trade_diff:+d} ({trade_diff/base_metrics["trades"]*100:+.1f}%)')
    print()

print_improvement(metrics_before, metrics_breadth, 'breadth_8ma')
print_improvement(metrics_before, metrics_bottom, 'bottom_3stage')

# ポジションサイズ分析
print('💰 ポジションサイズ分析:')
print('=' * 60)

def analyze_position_size(df, name):
    shares_desc = df['shares'].describe()
    print(f'{name}:')
    print(f'  平均株数:     {shares_desc["mean"]:.0f}')
    print(f'  中央値:       {shares_desc["50%"]:.0f}')
    print(f'  最小株数:     {shares_desc["min"]:.0f}')
    print(f'  最大株数:     {shares_desc["max"]:.0f}')
    print(f'  標準偏差:     {shares_desc["std"]:.0f}')
    return shares_desc["mean"]

before_avg = analyze_position_size(before, 'Fixed Position')
breadth_avg = analyze_position_size(breadth_8ma, 'breadth_8ma')
bottom_avg = analyze_position_size(bottom_3stage, 'bottom_3stage')

print()
print('ポジションサイズ比率:')
print(f'  breadth_8ma / Fixed:    {breadth_avg/before_avg:.2f}x')
print(f'  bottom_3stage / Fixed:  {bottom_avg/before_avg:.2f}x')
print()

# 月次パフォーマンス分析
print('📅 月次パフォーマンス:')
print('=' * 60)

def calc_monthly_pnl(df, name):
    df['entry_month'] = pd.to_datetime(df['entry_date']).dt.to_period('M')
    monthly = df.groupby('entry_month')['pnl'].sum()
    
    print(f'{name}:')
    for month, pnl in monthly.items():
        print(f'  {month}: ${pnl:,.0f}')
    print()
    return monthly

monthly_before = calc_monthly_pnl(before, 'Fixed Position')
monthly_breadth = calc_monthly_pnl(breadth_8ma, 'breadth_8ma')
monthly_bottom = calc_monthly_pnl(bottom_3stage, 'bottom_3stage')

# 共通トレードの比較
print('🔍 3者共通トレードの分析:')
print('=' * 60)

# 各データセットのトレードIDを作成
before['trade_id'] = before['ticker'] + '_' + before['entry_date']
breadth_8ma['trade_id'] = breadth_8ma['ticker'] + '_' + breadth_8ma['entry_date']
bottom_3stage['trade_id'] = bottom_3stage['ticker'] + '_' + bottom_3stage['entry_date']

# 3者共通のトレードを見つける
common_trades = set(before['trade_id']) & set(breadth_8ma['trade_id']) & set(bottom_3stage['trade_id'])

if common_trades:
    print(f'3者共通トレード数: {len(common_trades)}')
    
    # 共通トレードのP&L比較
    common_analysis = []
    for trade_id in common_trades:
        before_trade = before[before['trade_id'] == trade_id].iloc[0]
        breadth_trade = breadth_8ma[breadth_8ma['trade_id'] == trade_id].iloc[0]
        bottom_trade = bottom_3stage[bottom_3stage['trade_id'] == trade_id].iloc[0]
        
        common_analysis.append({
            'ticker': before_trade['ticker'],
            'entry_date': before_trade['entry_date'],
            'fixed_pnl': before_trade['pnl'],
            'breadth_pnl': breadth_trade['pnl'],
            'bottom_pnl': bottom_trade['pnl'],
            'fixed_shares': before_trade['shares'],
            'breadth_shares': breadth_trade['shares'],
            'bottom_shares': bottom_trade['shares'],
        })
    
    common_df = pd.DataFrame(common_analysis)
    
    # 平均改善を計算
    avg_breadth_imp = (common_df['breadth_pnl'] - common_df['fixed_pnl']).mean()
    avg_bottom_imp = (common_df['bottom_pnl'] - common_df['fixed_pnl']).mean()
    
    print(f'breadth_8ma平均P&L改善: ${avg_breadth_imp:,.2f}')
    print(f'bottom_3stage平均P&L改善: ${avg_bottom_imp:,.2f}')
    print()
    
    # 最も改善が大きかったトレード
    common_df['breadth_improvement'] = common_df['breadth_pnl'] - common_df['fixed_pnl']
    common_df['bottom_improvement'] = common_df['bottom_pnl'] - common_df['fixed_pnl']
    
    print('最大改善トレード (breadth_8ma):')
    best_breadth = common_df.nlargest(3, 'breadth_improvement')
    for _, row in best_breadth.iterrows():
        print(f'  {row["ticker"]} ({row["entry_date"]}): ${row["breadth_improvement"]:+,.0f}')
    
    print()
    print('最大改善トレード (bottom_3stage):')
    best_bottom = common_df.nlargest(3, 'bottom_improvement')
    for _, row in best_bottom.iterrows():
        print(f'  {row["ticker"]} ({row["entry_date"]}): ${row["bottom_improvement"]:+,.0f}')
else:
    print('3者共通トレードなし')

print()

# リスク分析
print('⚠️ リスク分析:')
print('=' * 60)

def analyze_risk(df, name):
    losses = df[df['pnl'] < 0]['pnl']
    if len(losses) > 0:
        avg_loss = losses.mean()
        max_loss = losses.min()
        total_loss = losses.sum()
        loss_std = losses.std()
    else:
        avg_loss = max_loss = total_loss = loss_std = 0
    
    # ドローダウン計算（簡易版）
    df_sorted = df.sort_values('entry_date')
    df_sorted['cumulative_pnl'] = df_sorted['pnl'].cumsum()
    df_sorted['running_max'] = df_sorted['cumulative_pnl'].cummax()
    df_sorted['drawdown'] = df_sorted['cumulative_pnl'] - df_sorted['running_max']
    max_drawdown = df_sorted['drawdown'].min()
    
    print(f'{name}:')
    print(f'  平均損失:     ${avg_loss:,.2f}')
    print(f'  最大損失:     ${max_loss:,.2f}')
    print(f'  総損失:       ${total_loss:,.2f}')
    print(f'  損失標準偏差: ${loss_std:,.2f}')
    print(f'  最大ドローダウン: ${max_drawdown:,.2f}')
    print()

analyze_risk(before, 'Fixed Position')
analyze_risk(breadth_8ma, 'breadth_8ma')
analyze_risk(bottom_3stage, 'bottom_3stage')

# 最終結論
print('🎯 結論:')
print('=' * 60)

# パフォーマンスランキング
rankings = [
    ('Fixed Position', metrics_before['total_pnl']),
    ('breadth_8ma', metrics_breadth['total_pnl']),
    ('bottom_3stage', metrics_bottom['total_pnl'])
]
rankings.sort(key=lambda x: x[1], reverse=True)

print('総P&Lランキング:')
for i, (name, pnl) in enumerate(rankings, 1):
    print(f'  {i}位: {name} (${pnl:,.2f})')

print()

# 最適戦略の提案
best_strategy = rankings[0][0]
if best_strategy == 'Fixed Position':
    print('⚠️ 固定ポジションサイズが最も良い結果')
    print('   動的ポジションサイズの調整が必要')
else:
    improvement = rankings[0][1] - metrics_before['total_pnl']
    improvement_pct = (improvement / abs(metrics_before['total_pnl'])) * 100
    print(f'✅ {best_strategy}が最適戦略')
    print(f'   Fixed Positionから${improvement:,.2f} (+{improvement_pct:.1f}%)の改善')

# 特徴的な発見
print()
print('📌 特徴的な発見:')
if metrics_breadth['total_pnl'] > metrics_before['total_pnl']:
    print('- breadth_8maは市場環境に応じた動的調整が有効')
if metrics_bottom['total_pnl'] > metrics_before['total_pnl']:
    print('- bottom_3stageは底値検出後の段階的増加が有効')
if metrics_bottom['max_win'] > metrics_breadth['max_win']:
    print('- bottom_3stageは大型勝利トレードを生成')
if abs(metrics_breadth['max_loss']) < abs(metrics_before['max_loss']):
    print('- breadth_8maはリスク管理が改善')