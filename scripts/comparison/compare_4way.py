#!/usr/bin/env python3
"""
4者比較分析: Fixed Position vs breadth_8ma vs bottom_3stage vs bearish_signal
"""
import pandas as pd
import numpy as np

# CSVファイルを読み込み
before = pd.read_csv('reports/earnings_backtest_2025_01_01_2025_06_30_before.csv')
breadth_8ma = pd.read_csv('reports/earnings_backtest_2025_01_01_2025_06_30_breadth_8ma.csv')
bottom_3stage = pd.read_csv('reports/earnings_backtest_2025_01_01_2025_06_30_bottom_3stage.csv')
bearish_signal = pd.read_csv('reports/earnings_backtest_2025_01_01_2025_06_30_bearish_signal.csv')

print('=== 4者比較分析: 動的ポジションサイズ戦略の包括評価 ===')
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
    
    # Sharpe ratio (簡易版)
    pnl_std = df['pnl'].std()
    sharpe = avg_pnl / pnl_std if pnl_std > 0 else 0
    
    # Win/Loss ratio
    win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
    
    # Profit factor
    total_wins = df[df['pnl'] > 0]['pnl'].sum()
    total_losses = abs(df[df['pnl'] < 0]['pnl'].sum())
    profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
    
    return {
        'name': name,
        'trades': len(df),
        'total_pnl': total_pnl,
        'win_rate': win_rate,
        'avg_pnl': avg_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'max_win': max_win,
        'max_loss': max_loss,
        'avg_holding': avg_holding,
        'sharpe': sharpe,
        'win_loss_ratio': win_loss_ratio,
        'profit_factor': profit_factor,
        'avg_shares': df['shares'].mean()
    }

# 全戦略のメトリクス計算
strategies = {
    'Fixed Position': before,
    'breadth_8ma': breadth_8ma,
    'bottom_3stage': bottom_3stage,
    'bearish_signal': bearish_signal
}

metrics = []
for name, df in strategies.items():
    metrics.append(calc_metrics(df, name))

print('📊 戦略別パフォーマンス:')
print('=' * 80)
print(f'{"戦略":<18} {"トレード数":<8} {"総P&L":<12} {"勝率":<8} {"平均P&L":<10} {"Sharpe":<8} {"PF":<6}')
print('-' * 80)

for m in metrics:
    print(f'{m["name"]:<18} {m["trades"]:<8} ${m["total_pnl"]:<11,.0f} {m["win_rate"]:<7.1f}% '
          f'${m["avg_pnl"]:<9,.0f} {m["sharpe"]:<7.2f} {m["profit_factor"]:<5.2f}')

print()

# ランキング作成
rankings = {
    'total_pnl': sorted(metrics, key=lambda x: x['total_pnl'], reverse=True),
    'win_rate': sorted(metrics, key=lambda x: x['win_rate'], reverse=True),
    'sharpe': sorted(metrics, key=lambda x: x['sharpe'], reverse=True),
    'profit_factor': sorted(metrics, key=lambda x: x['profit_factor'], reverse=True)
}

print('🏆 各指標でのランキング:')
print('=' * 80)

for metric_name, ranking in rankings.items():
    print(f'{metric_name.upper()}:')
    for i, m in enumerate(ranking, 1):
        if metric_name == 'total_pnl':
            print(f'  {i}位: {m["name"]:<18} ${m[metric_name]:,.0f}')
        elif metric_name == 'win_rate':
            print(f'  {i}位: {m["name"]:<18} {m[metric_name]:.1f}%')
        else:
            print(f'  {i}位: {m["name"]:<18} {m[metric_name]:.2f}')
    print()

# 月次パフォーマンス分析
print('📅 月次P&L推移:')
print('=' * 80)

def calc_monthly_pnl(df):
    df['entry_month'] = pd.to_datetime(df['entry_date']).dt.to_period('M')
    return df.groupby('entry_month')['pnl'].sum()

# 月次データの取得
monthly_data = {}
for name, df in strategies.items():
    monthly_data[name] = calc_monthly_pnl(df)

# 全ての月を取得
all_months = set()
for monthly in monthly_data.values():
    all_months.update(monthly.index)
all_months = sorted(all_months)

print(f'{"月":<10} {"Fixed":<12} {"breadth_8ma":<12} {"bottom_3stage":<12} {"bearish_signal":<12}')
print('-' * 70)

for month in all_months:
    row = f'{str(month):<10}'
    for strategy in ['Fixed Position', 'breadth_8ma', 'bottom_3stage', 'bearish_signal']:
        value = monthly_data[strategy].get(month, 0)
        row += f'${value:<11,.0f}'
    print(row)

print()

# ポジションサイズ分析
print('💰 ポジションサイズ分析:')
print('=' * 80)

base_avg = metrics[0]['avg_shares']  # Fixed Position
print(f'{"戦略":<18} {"平均株数":<10} {"倍率":<8} {"最小":<8} {"最大":<8}')
print('-' * 60)

for name, df in strategies.items():
    shares_desc = df['shares'].describe()
    multiplier = shares_desc['mean'] / base_avg
    print(f'{name:<18} {shares_desc["mean"]:<9.0f} {multiplier:<7.2f}x '
          f'{shares_desc["min"]:<7.0f} {shares_desc["max"]:<7.0f}')

print()

# リスク分析
print('⚠️ リスク分析:')
print('=' * 80)

def analyze_risk(df):
    # ドローダウン計算
    df_sorted = df.sort_values('entry_date').copy()
    df_sorted['cumulative_pnl'] = df_sorted['pnl'].cumsum()
    df_sorted['running_max'] = df_sorted['cumulative_pnl'].cummax()
    df_sorted['drawdown'] = df_sorted['cumulative_pnl'] - df_sorted['running_max']
    max_drawdown = df_sorted['drawdown'].min()
    
    # VaR計算 (95%)
    var_95 = df['pnl'].quantile(0.05)
    
    return {
        'max_drawdown': max_drawdown,
        'var_95': var_95,
        'downside_deviation': df[df['pnl'] < 0]['pnl'].std()
    }

print(f'{"戦略":<18} {"最大DD":<12} {"VaR(95%)":<12} {"下方偏差":<12}')
print('-' * 60)

for name, df in strategies.items():
    risk = analyze_risk(df)
    print(f'{name:<18} ${risk["max_drawdown"]:<11,.0f} '
          f'${risk["var_95"]:<11,.0f} {risk["downside_deviation"]:<11.0f}')

print()

# 戦略間の相関分析
print('🔗 戦略間相関分析:')
print('=' * 80)

# 共通トレードベースでの相関
def get_common_trades_pnl():
    # 各戦略のトレードIDを作成
    trade_ids = {}
    for name, df in strategies.items():
        df['trade_id'] = df['ticker'] + '_' + df['entry_date']
        trade_ids[name] = set(df['trade_id'])
    
    # 全戦略共通のトレードを見つける
    common_trade_ids = set.intersection(*trade_ids.values())
    
    if not common_trade_ids:
        return None
    
    # 共通トレードのP&Lを抽出
    common_pnl = {}
    for name, df in strategies.items():
        common_df = df[df['trade_id'].isin(common_trade_ids)].sort_values('trade_id')
        common_pnl[name] = common_df['pnl'].values
    
    return pd.DataFrame(common_pnl)

common_pnl_df = get_common_trades_pnl()
if common_pnl_df is not None:
    correlation_matrix = common_pnl_df.corr()
    print(f'共通トレード数: {len(common_pnl_df)}')
    print('\n相関係数行列:')
    print(correlation_matrix.round(3))
else:
    print('全戦略共通のトレードが見つかりませんでした')

print()

# パフォーマンス・リスク効率性
print('📈 パフォーマンス効率性:')
print('=' * 80)

print(f'{"戦略":<18} {"リターン/DD比":<15} {"リターン/VaR比":<15} {"総合スコア":<12}')
print('-' * 70)

efficiency_scores = []
for name, df in strategies.items():
    m = next(metric for metric in metrics if metric['name'] == name)
    risk = analyze_risk(df)
    
    return_dd_ratio = m['total_pnl'] / abs(risk['max_drawdown']) if risk['max_drawdown'] != 0 else 0
    return_var_ratio = m['total_pnl'] / abs(risk['var_95']) if risk['var_95'] != 0 else 0
    
    # 総合スコア (リターン × Sharpe比 × 勝率 / リスク要因)
    overall_score = (m['total_pnl'] * m['sharpe'] * m['win_rate'] / 100) / (abs(risk['max_drawdown']) + 1)
    
    efficiency_scores.append({
        'name': name,
        'return_dd_ratio': return_dd_ratio,
        'return_var_ratio': return_var_ratio,
        'overall_score': overall_score
    })
    
    print(f'{name:<18} {return_dd_ratio:<14.2f} {return_var_ratio:<14.2f} {overall_score:<11.2f}')

print()

# 最終結論と推奨
print('🎯 最終結論と戦略推奨:')
print('=' * 80)

# 各指標での1位を集計
first_place_counts = {}
for name in strategies.keys():
    first_place_counts[name] = 0

for ranking in rankings.values():
    first_place_counts[ranking[0]['name']] += 1

# 効率性スコアでソート
efficiency_ranking = sorted(efficiency_scores, key=lambda x: x['overall_score'], reverse=True)

print('各指標での1位獲得回数:')
for name, count in sorted(first_place_counts.items(), key=lambda x: x[1], reverse=True):
    print(f'  {name}: {count}回')

print(f'\n総合効率性ランキング:')
for i, score in enumerate(efficiency_ranking, 1):
    print(f'  {i}位: {score["name"]} (スコア: {score["overall_score"]:.2f})')

print()

# 戦略特性まとめ
print('📋 各戦略の特性まとめ:')
print('=' * 80)

best_strategy = efficiency_ranking[0]['name']
top_pnl_strategy = rankings['total_pnl'][0]['name']

print(f'🥇 総合最優秀戦略: {best_strategy}')
print(f'💰 最高収益戦略: {top_pnl_strategy}')

strategy_characteristics = {
    'Fixed Position': '安定的だが成長性に限界',
    'breadth_8ma': '市場環境対応型、中程度のリスク',
    'bottom_3stage': '高リターン追求型、底値狙い',
    'bearish_signal': '弱気相場対応型、保守的'
}

print('\n各戦略の特徴:')
for name, char in strategy_characteristics.items():
    metric = next(m for m in metrics if m['name'] == name)
    print(f'  {name}: {char}')
    print(f'    → 総P&L: ${metric["total_pnl"]:,.0f}, 勝率: {metric["win_rate"]:.1f}%, Sharpe: {metric["sharpe"]:.2f}')

print()

# 実用的な推奨
print('💡 実用的な推奨:')
print('=' * 80)

if best_strategy == top_pnl_strategy:
    print(f'✅ {best_strategy}が総合的に最優秀')
    improvement = next(m for m in metrics if m['name'] == best_strategy)['total_pnl'] - metrics[0]['total_pnl']
    print(f'   Fixed Positionから${improvement:,.0f}の改善を実現')
else:
    print(f'🔄 用途別推奨:')
    print(f'   リスク重視: {best_strategy}')
    print(f'   リターン重視: {top_pnl_strategy}')

print('\n市場環境別推奨:')
print('  上昇相場: bottom_3stage (積極的成長狙い)')
print('  下落相場: bearish_signal (保守的対応)')
print('  横ばい相場: breadth_8ma (環境適応型)')
print('  安定重視: Fixed Position (リスク最小化)')