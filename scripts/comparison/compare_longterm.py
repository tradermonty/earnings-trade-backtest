#!/usr/bin/env python3
"""
長期バックテスト比較分析: stop10 vs bearish_signal (2020-09-01 to 2025-06-30)
ストップロス10%設定 vs 弱気相場対応動的ポジションサイズの5年間比較
"""
import pandas as pd
import numpy as np
from datetime import datetime

# CSVファイルを読み込み
stop10 = pd.read_csv('reports/earnings_backtest_2020_09_01_2025_06_30_all_stop10.csv')
bearish_signal = pd.read_csv('reports/earnings_backtest_2020_09_01_2025_06_30_bearish_signal.csv')

print('=== 長期バックテスト比較分析 (2020-09-01 to 2025-06-30) ===')
print('Fixed Position (10% stop loss) vs Dynamic Position (bearish_signal)')
print()

# 基本統計
print('📊 基本統計:')
print(f'stop10 (10%ストップロス):     {len(stop10)} トレード')
print(f'bearish_signal (動的ポジション): {len(bearish_signal)} トレード')
print(f'期間: 2020年9月 〜 2025年6月 (約5年間)')
print()

# 基本メトリクス計算
def calc_comprehensive_metrics(df, name):
    total_pnl = df['pnl'].sum()
    win_rate = len(df[df['pnl'] > 0]) / len(df) * 100 if len(df) > 0 else 0
    avg_pnl = df['pnl'].mean()
    avg_win = df[df['pnl'] > 0]['pnl'].mean() if len(df[df['pnl'] > 0]) > 0 else 0
    avg_loss = df[df['pnl'] < 0]['pnl'].mean() if len(df[df['pnl'] < 0]) > 0 else 0
    max_win = df['pnl'].max()
    max_loss = df['pnl'].min()
    avg_holding = df['holding_period'].mean()
    
    # 年次リターン計算
    df['entry_year'] = pd.to_datetime(df['entry_date']).dt.year
    years = df['entry_year'].nunique()
    annual_return = total_pnl / years if years > 0 else 0
    
    # Sharpe ratio (簡易版)
    pnl_std = df['pnl'].std()
    sharpe = avg_pnl / pnl_std if pnl_std > 0 else 0
    
    # 勝敗比
    win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
    
    # プロフィット・ファクター
    total_wins = df[df['pnl'] > 0]['pnl'].sum()
    total_losses = abs(df[df['pnl'] < 0]['pnl'].sum())
    profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
    
    # ドローダウン計算
    df_sorted = df.sort_values('entry_date').copy()
    df_sorted['cumulative_pnl'] = df_sorted['pnl'].cumsum()
    df_sorted['running_max'] = df_sorted['cumulative_pnl'].cummax()
    df_sorted['drawdown'] = df_sorted['cumulative_pnl'] - df_sorted['running_max']
    max_drawdown = df_sorted['drawdown'].min()
    
    # 各種比率
    stop_loss_trades = len(df[df['exit_reason'] == 'stop_loss'])
    stop_loss_rate = (stop_loss_trades / len(df)) * 100
    
    print(f'{name}:')
    print(f'  トレード数:      {len(df)}')
    print(f'  総P&L:           ${total_pnl:,.2f}')
    print(f'  年間平均リターン: ${annual_return:,.2f}')
    print(f'  勝率:            {win_rate:.1f}%')
    print(f'  平均P&L:         ${avg_pnl:,.2f}')
    print(f'  平均勝ち:        ${avg_win:,.2f}')
    print(f'  平均負け:        ${avg_loss:,.2f}')
    print(f'  最大勝ち:        ${max_win:,.2f}')
    print(f'  最大負け:        ${max_loss:,.2f}')
    print(f'  平均保有期間:    {avg_holding:.1f}日')
    print(f'  最大ドローダウン: ${max_drawdown:,.2f}')
    print(f'  Sharpe比:        {sharpe:.3f}')
    print(f'  勝敗比:          {win_loss_ratio:.2f}')
    print(f'  プロフィット・ファクター: {profit_factor:.2f}')
    print(f'  ストップロス率:  {stop_loss_rate:.1f}%')
    print()
    
    return {
        'trades': len(df),
        'total_pnl': total_pnl,
        'annual_return': annual_return,
        'win_rate': win_rate,
        'avg_pnl': avg_pnl,
        'max_win': max_win,
        'max_loss': max_loss,
        'max_drawdown': max_drawdown,
        'sharpe': sharpe,
        'profit_factor': profit_factor,
        'stop_loss_rate': stop_loss_rate,
        'avg_shares': df['shares'].mean()
    }

metrics_stop10 = calc_comprehensive_metrics(stop10, 'stop10 (10%ストップロス)')
metrics_bearish = calc_comprehensive_metrics(bearish_signal, 'bearish_signal (動的ポジション)')

# 改善分析
print('📈 bearish_signal戦略の改善効果:')
pnl_improvement = metrics_bearish['total_pnl'] - metrics_stop10['total_pnl']
pnl_improvement_pct = (pnl_improvement / abs(metrics_stop10['total_pnl'])) * 100 if metrics_stop10['total_pnl'] != 0 else 0
win_rate_improvement = metrics_bearish['win_rate'] - metrics_stop10['win_rate']
trade_difference = metrics_bearish['trades'] - metrics_stop10['trades']

print(f'総P&L改善:        ${pnl_improvement:,.2f} ({pnl_improvement_pct:+.1f}%)')
print(f'年間リターン改善: ${metrics_bearish["annual_return"] - metrics_stop10["annual_return"]:,.2f}')
print(f'勝率変化:         {win_rate_improvement:+.1f}ポイント')
print(f'トレード数差:     {trade_difference:+d} ({trade_difference/metrics_stop10["trades"]*100:+.1f}%)')
print(f'Sharpe比改善:     {metrics_bearish["sharpe"] - metrics_stop10["sharpe"]:+.3f}')
print()

# 年次パフォーマンス分析
print('📅 年次パフォーマンス推移:')
print('=' * 60)

def calc_yearly_performance(df, name):
    df['entry_year'] = pd.to_datetime(df['entry_date']).dt.year
    yearly = df.groupby('entry_year').agg({
        'pnl': ['sum', 'count', 'mean'],
        'holding_period': 'mean'
    }).round(2)
    yearly.columns = ['Total_PnL', 'Trades', 'Avg_PnL', 'Avg_Holding']
    yearly['Win_Rate'] = df.groupby('entry_year').apply(
        lambda x: round(len(x[x['pnl'] > 0]) / len(x) * 100, 1)
    )
    return yearly

yearly_stop10 = calc_yearly_performance(stop10, 'stop10')
yearly_bearish = calc_yearly_performance(bearish_signal, 'bearish')

print(f'{"年":<6} {"stop10 P&L":<12} {"bearish P&L":<12} {"改善額":<10} {"stop10勝率":<10} {"bearish勝率":<10}')
print('-' * 70)

years = sorted(set(yearly_stop10.index) | set(yearly_bearish.index))
for year in years:
    stop_pnl = yearly_stop10.loc[year, 'Total_PnL'] if year in yearly_stop10.index else 0
    bearish_pnl = yearly_bearish.loc[year, 'Total_PnL'] if year in yearly_bearish.index else 0
    improvement = bearish_pnl - stop_pnl
    stop_wr = yearly_stop10.loc[year, 'Win_Rate'] if year in yearly_stop10.index else 0
    bearish_wr = yearly_bearish.loc[year, 'Win_Rate'] if year in yearly_bearish.index else 0
    
    print(f'{year:<6} ${stop_pnl:<11,.0f} ${bearish_pnl:<11,.0f} ${improvement:<9,.0f} '
          f'{stop_wr:<9.1f}% {bearish_wr:<9.1f}%')

print()

# ポジションサイズ分析
print('💰 ポジションサイズ分析:')
print('=' * 60)

def analyze_position_sizing(df, name):
    shares_stats = df['shares'].describe()
    print(f'{name}:')
    print(f'  平均株数:   {shares_stats["mean"]:.0f}')
    print(f'  中央値:     {shares_stats["50%"]:.0f}')
    print(f'  最小株数:   {shares_stats["min"]:.0f}')
    print(f'  最大株数:   {shares_stats["max"]:.0f}')
    print(f'  標準偏差:   {shares_stats["std"]:.0f}')
    return shares_stats["mean"]

stop10_avg_shares = analyze_position_sizing(stop10, 'stop10')
bearish_avg_shares = analyze_position_sizing(bearish_signal, 'bearish_signal')

print()
print(f'平均ポジションサイズ比率: {bearish_avg_shares/stop10_avg_shares:.2f}x')
print()

# 月次パフォーマンス分析（直近2年）
print('📊 月次パフォーマンス (2024-2025):')
print('=' * 60)

def get_monthly_recent(df):
    df['entry_date'] = pd.to_datetime(df['entry_date'])
    recent = df[df['entry_date'] >= '2024-01-01'].copy()
    recent['month'] = recent['entry_date'].dt.to_period('M')
    return recent.groupby('month')['pnl'].sum()

monthly_stop10 = get_monthly_recent(stop10)
monthly_bearish = get_monthly_recent(bearish_signal)

all_months = sorted(set(monthly_stop10.index) | set(monthly_bearish.index))

print(f'{"月":<10} {"stop10":<12} {"bearish":<12} {"差額":<10}')
print('-' * 50)

for month in all_months:
    stop_val = monthly_stop10.get(month, 0)
    bearish_val = monthly_bearish.get(month, 0)
    diff = bearish_val - stop_val
    print(f'{str(month):<10} ${stop_val:<11,.0f} ${bearish_val:<11,.0f} ${diff:<9,.0f}')

print()

# リスク分析
print('⚠️ リスク分析:')
print('=' * 60)

def analyze_risk_metrics(df, name):
    losses = df[df['pnl'] < 0]['pnl']
    gains = df[df['pnl'] > 0]['pnl']
    
    # VaR (5%、95%)
    var_5 = df['pnl'].quantile(0.05) if len(df) > 0 else 0
    var_95 = df['pnl'].quantile(0.95) if len(df) > 0 else 0
    
    # 下方偏差
    downside_dev = losses.std() if len(losses) > 0 else 0
    
    # 最大連続損失
    df_sorted = df.sort_values('entry_date')
    consecutive_losses = 0
    max_consecutive_losses = 0
    consecutive_loss_amount = 0
    max_consecutive_loss_amount = 0
    
    for _, row in df_sorted.iterrows():
        if row['pnl'] < 0:
            consecutive_losses += 1
            consecutive_loss_amount += row['pnl']
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            max_consecutive_loss_amount = min(max_consecutive_loss_amount, consecutive_loss_amount)
        else:
            consecutive_losses = 0
            consecutive_loss_amount = 0
    
    print(f'{name}:')
    print(f'  VaR (5%):            ${var_5:,.2f}')
    print(f'  VaR (95%):           ${var_95:,.2f}')
    print(f'  下方偏差:            {downside_dev:.2f}')
    print(f'  最大連続損失回数:    {max_consecutive_losses}回')
    print(f'  最大連続損失額:      ${max_consecutive_loss_amount:,.2f}')
    
    return {
        'var_5': var_5,
        'var_95': var_95,
        'downside_dev': downside_dev,
        'max_consecutive_losses': max_consecutive_losses,
        'max_consecutive_loss_amount': max_consecutive_loss_amount
    }

risk_stop10 = analyze_risk_metrics(stop10, 'stop10')
risk_bearish = analyze_risk_metrics(bearish_signal, 'bearish_signal')

print()

# 市場環境別パフォーマンス
print('🌍 市場環境別パフォーマンス:')
print('=' * 60)

market_periods = {
    'COVID回復期 (2020-2021)': ('2020-09-01', '2021-12-31'),
    '金利上昇期 (2022-2023)': ('2022-01-01', '2023-12-31'),
    'AI相場期 (2024-2025)': ('2024-01-01', '2025-06-30')
}

for period_name, (start_date, end_date) in market_periods.items():
    stop10_period = stop10[
        (pd.to_datetime(stop10['entry_date']) >= start_date) & 
        (pd.to_datetime(stop10['entry_date']) <= end_date)
    ]
    bearish_period = bearish_signal[
        (pd.to_datetime(bearish_signal['entry_date']) >= start_date) & 
        (pd.to_datetime(bearish_signal['entry_date']) <= end_date)
    ]
    
    stop10_pnl = stop10_period['pnl'].sum()
    bearish_pnl = bearish_period['pnl'].sum()
    improvement = bearish_pnl - stop10_pnl
    
    print(f'{period_name}:')
    print(f'  stop10:     ${stop10_pnl:,.0f} ({len(stop10_period)}トレード)')
    print(f'  bearish:    ${bearish_pnl:,.0f} ({len(bearish_period)}トレード)')
    print(f'  改善:       ${improvement:,.0f}')
    print()

# 最終結論
print('🎯 最終結論:')
print('=' * 60)

if pnl_improvement > 0:
    print(f'✅ bearish_signal戦略が優秀')
    print(f'   5年間で${pnl_improvement:,.0f}の追加利益を実現 ({pnl_improvement_pct:+.1f}%改善)')
    print(f'   年間平均で${(metrics_bearish["annual_return"] - metrics_stop10["annual_return"]):,.0f}の改善')
    
    if metrics_bearish['sharpe'] > metrics_stop10['sharpe']:
        print(f'   リスク調整後リターンも改善 (Sharpe比 {metrics_bearish["sharpe"]:.3f} vs {metrics_stop10["sharpe"]:.3f})')
    
    if abs(metrics_bearish['max_drawdown']) < abs(metrics_stop10['max_drawdown']):
        print(f'   最大ドローダウンも改善 (${metrics_bearish["max_drawdown"]:,.0f} vs ${metrics_stop10["max_drawdown"]:,.0f})')
    
else:
    print(f'❌ stop10戦略が優秀')
    print(f'   bearish_signalは${abs(pnl_improvement):,.0f}の損失')

print()
print('💡 戦略特性:')
print(f'stop10:        固定10%ストップロス、{metrics_stop10["avg_shares"]:.0f}株平均')
print(f'bearish_signal: 動的ポジションサイズ、{metrics_bearish["avg_shares"]:.0f}株平均')
print(f'               弱気相場で保守的、強気相場で積極的に調整')

# パフォーマンス要約
print()
print('📋 5年間パフォーマンス要約:')
print('=' * 60)
print(f'期間:             2020年9月〜2025年6月')
print(f'総取引数:         stop10 {metrics_stop10["trades"]} vs bearish {metrics_bearish["trades"]}')
print(f'総リターン:       stop10 ${metrics_stop10["total_pnl"]:,.0f} vs bearish ${metrics_bearish["total_pnl"]:,.0f}')
print(f'年間平均リターン: stop10 ${metrics_stop10["annual_return"]:,.0f} vs bearish ${metrics_bearish["annual_return"]:,.0f}')
print(f'勝率:             stop10 {metrics_stop10["win_rate"]:.1f}% vs bearish {metrics_bearish["win_rate"]:.1f}%')
print(f'最大ドローダウン: stop10 ${metrics_stop10["max_drawdown"]:,.0f} vs bearish ${metrics_bearish["max_drawdown"]:,.0f}')