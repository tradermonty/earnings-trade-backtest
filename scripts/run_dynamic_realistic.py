#!/usr/bin/env python3
"""
現実的なサンプルデータを使用した動的ポジションサイズ調整
実際のバックテスト規模に近いデータで5年間のテスト
"""

import sys
import os
import pandas as pd
import numpy as np
import tempfile
import argparse
from datetime import datetime

# 既存のスクリプトをインポート
sys.path.insert(0, os.path.dirname(__file__))

def load_market_breadth_data(csv_path):
    """Market Breadth Index CSVファイルを読み込み"""
    try:
        df = pd.read_csv(csv_path)
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        
        # Boolean列の処理
        boolean_columns = ['Bearish_Signal', 'Is_Peak', 'Is_Trough', 'Is_Trough_8MA_Below_04']
        for col in boolean_columns:
            if col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].astype(str).str.lower() == 'true'
                else:
                    df[col] = df[col].astype(bool)
        
        print(f"✅ Market Breadth data loaded: {len(df)} records")
        return df
    except Exception as e:
        print(f"❌ Error loading Market Breadth CSV: {e}")
        return None

def generate_realistic_trades_for_period(start_date, end_date):
    """実際のバックテスト結果に基づくトレードデータを生成"""
    np.random.seed(42)  # 再現性のため
    
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    total_days = (end_dt - start_dt).days
    
    # 実際のバックテスト結果: 2020-09-01から2025-06-30で365トレード
    # 年間約75トレード（週1.4回程度）
    total_trades = int((total_days / 365) * 75)
    
    print(f"🔄 Generating {total_trades} realistic trades for {start_date} to {end_date}...")
    
    # ティッカーリスト（実際のearnings surprise銘柄）
    tickers = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX',
        'ADBE', 'CRM', 'ZM', 'PYPL', 'SQ', 'SHOP', 'ROKU', 'DOCU',
        'OKTA', 'DDOG', 'CRWD', 'SNOW', 'PLTR', 'U', 'NET', 'TWLO',
        'UBER', 'LYFT', 'ABNB', 'DASH', 'RBLX', 'COIN', 'SOFI', 'HOOD',
        'AMD', 'INTC', 'QCOM', 'AMAT', 'LRCX', 'KLAC', 'MRVL', 'ADI',
        'BABA', 'JD', 'PDD', 'BIDU', 'NIO', 'XPEV', 'LI', 'TSM',
        'ASML', 'SAP', 'SHOP', 'SPOT', 'SQ', 'PYPL', 'V', 'MA'
    ]
    
    trades = []
    
    for i in range(total_trades):
        # ランダムな日付を生成
        days_offset = np.random.randint(0, total_days)
        trade_date = start_dt + pd.Timedelta(days=days_offset)
        
        # 週末を避ける
        while trade_date.weekday() >= 5:  # 土日
            days_offset = np.random.randint(0, total_days)
            trade_date = start_dt + pd.Timedelta(days=days_offset)
        
        ticker = np.random.choice(tickers)
        
        # 実際のバックテスト結果に基づくリターン分布
        # 勝率62.5%、総リターン263.07%を365トレードで達成
        # 平均約0.72%/トレード
        is_winner = np.random.random() < 0.625
        
        if is_winner:
            # 勝ちトレード: 実際の収益分布を模擬
            pnl_rate = np.random.exponential(0.08) + 0.01
            pnl_rate = min(pnl_rate, 0.30)  # 最大30%
        else:
            # 負けトレード: stop loss 10%を考慮
            pnl_rate = -np.random.exponential(0.08) - 0.01
            pnl_rate = max(pnl_rate, -0.12)  # 最大-12%（stop loss近く）
        
        # ポジションサイズ（基準15%、$15,000投資）
        position_value = 15000
        pnl = position_value * pnl_rate
        entry_price = 50 + np.random.uniform(-30, 200)  # $20-$250の範囲
        
        trade = {
            'date': trade_date.strftime('%Y-%m-%d'),
            'ticker': ticker,
            'entry_price': entry_price,
            'shares': int(position_value / entry_price),
            'pnl': pnl,
            'pnl_rate': pnl_rate,
            'holding_period': np.random.randint(1, 20)  # 1-19日保有
        }
        trades.append(trade)
    
    # 日付でソート
    trades.sort(key=lambda x: x['date'])
    
    # 統計を表示
    total_pnl = sum(t['pnl'] for t in trades)
    win_rate = sum(1 for t in trades if t['pnl'] > 0) / len(trades) * 100
    total_return = (total_pnl / 100000) * 100  # $100k初期資本想定
    
    print(f"✅ Generated realistic backtest data:")
    print(f"   Total Trades: {len(trades)}")
    print(f"   Win Rate: {win_rate:.1f}%")
    print(f"   Total Return: {total_return:.1f}%")
    print(f"   Avg Return per Trade: {total_return/len(trades):.2f}%")
    
    return trades

def get_market_data(breadth_df, date):
    """指定日のMarket Breadthデータを取得"""
    target_date = pd.Timestamp(date)
    
    # 完全一致を試行
    if target_date in breadth_df.index:
        row = breadth_df.loc[target_date]
        return {
            'breadth_8ma': float(row.get('Breadth_Index_8MA', 0)),
            'bearish_signal': bool(row.get('Bearish_Signal', False)),
            'is_trough': bool(row.get('Is_Trough', False)),
            'is_trough_8ma_below_04': bool(row.get('Is_Trough_8MA_Below_04', False))
        }
    
    # 前後数日のデータで補間
    for days_offset in range(1, 6):
        for offset in [-days_offset, days_offset]:
            test_date = target_date + pd.Timedelta(days=offset)
            if test_date in breadth_df.index:
                row = breadth_df.loc[test_date]
                return {
                    'breadth_8ma': float(row.get('Breadth_Index_8MA', 0)),
                    'bearish_signal': bool(row.get('Bearish_Signal', False)),
                    'is_trough': bool(row.get('Is_Trough', False)),
                    'is_trough_8ma_below_04': bool(row.get('Is_Trough_8MA_Below_04', False))
                }
    
    return None

def calculate_dynamic_position_size(market_data, pattern, config):
    """動的ポジションサイズを計算"""
    if not market_data:
        return config['default_position_size'], "no_market_data"
    
    breadth_8ma = market_data['breadth_8ma']
    bearish_signal = market_data['bearish_signal']
    is_trough = market_data['is_trough']
    is_trough_8ma_below_04 = market_data['is_trough_8ma_below_04']
    
    if pattern == "breadth_8ma":
        if breadth_8ma < 0.4:
            size = config['stress_position_size']
            reason = f"stress_8ma_{breadth_8ma:.3f}"
        elif breadth_8ma >= 0.7:
            size = config['bullish_position_size'] 
            reason = f"bullish_8ma_{breadth_8ma:.3f}"
        else:
            size = config['normal_position_size']
            reason = f"normal_8ma_{breadth_8ma:.3f}"
            
    elif pattern == "advanced_5stage":
        if breadth_8ma < 0.3:
            size = config['extreme_stress_position']
            reason = f"extreme_stress_{breadth_8ma:.3f}"
        elif breadth_8ma < 0.4:
            size = config['stress_position']
            reason = f"stress_{breadth_8ma:.3f}"
        elif breadth_8ma < 0.7:
            size = config['normal_position']
            reason = f"normal_{breadth_8ma:.3f}"
        elif breadth_8ma < 0.8:
            size = config['bullish_position']
            reason = f"bullish_{breadth_8ma:.3f}"
        else:
            size = config['extreme_bullish_position']
            reason = f"extreme_bullish_{breadth_8ma:.3f}"
            
    elif pattern == "bearish_signal":
        if breadth_8ma < 0.4:
            base_size = config['stress_position_size']
        elif breadth_8ma >= 0.7:
            base_size = config['bullish_position_size']
        else:
            base_size = config['normal_position_size']
            
        if bearish_signal:
            size = base_size * config['bearish_reduction_multiplier']
            reason = f"bearish_reduction_{breadth_8ma:.3f}"
        else:
            size = base_size
            reason = f"normal_{breadth_8ma:.3f}"
            
    elif pattern == "bottom_3stage":
        if breadth_8ma < 0.4:
            base_size = config['stress_position_size']
        elif breadth_8ma >= 0.7:
            base_size = config['bullish_position_size']
        else:
            base_size = config['normal_position_size']
            
        if bearish_signal:
            size = base_size * config['bearish_stage_multiplier']
            reason = f"stage1_bearish_{breadth_8ma:.3f}"
        elif is_trough_8ma_below_04:
            size = base_size * config['bottom_8ma_multiplier']
            reason = f"stage2_8ma_bottom_{breadth_8ma:.3f}"
        elif is_trough:
            size = base_size * config['bottom_200ma_multiplier']
            reason = f"stage3_200ma_bottom_{breadth_8ma:.3f}"
        else:
            size = base_size
            reason = f"normal_{breadth_8ma:.3f}"
    else:
        size = config['default_position_size']
        reason = "unknown_pattern"
    
    # 制限適用
    size = max(config['min_position_size'], min(size, config['max_position_size']))
    
    return size, reason

def apply_dynamic_position_sizing(trades_data, breadth_df, pattern, config):
    """トレードデータに動的ポジションサイズを適用"""
    trades_df = pd.DataFrame(trades_data)
    trades_df['date'] = pd.to_datetime(trades_df['date'])
    
    print(f"📊 Applying dynamic position sizing to {len(trades_df)} trades...")
    
    results = []
    original_position_size = 15.0
    
    for _, trade in trades_df.iterrows():
        entry_date = trade['date']
        market_data = get_market_data(breadth_df, entry_date)
        
        # 動的ポジションサイズを計算
        new_position_size, reason = calculate_dynamic_position_size(market_data, pattern, config)
        position_multiplier = new_position_size / original_position_size
        
        # トレード結果を調整
        adjusted_trade = trade.copy()
        adjusted_trade['original_position_size'] = original_position_size
        adjusted_trade['dynamic_position_size'] = new_position_size
        adjusted_trade['position_multiplier'] = position_multiplier
        adjusted_trade['position_reason'] = reason
        
        # shares, pnlを調整
        adjusted_trade['shares'] = trade['shares'] * position_multiplier
        adjusted_trade['pnl'] = trade['pnl'] * position_multiplier
        
        if market_data:
            adjusted_trade['breadth_8ma'] = market_data['breadth_8ma']
            adjusted_trade['bearish_signal'] = market_data['bearish_signal']
        
        results.append(adjusted_trade)
    
    return pd.DataFrame(results)

def calculate_metrics(trades_df, initial_capital=100000):
    """調整後のトレードでメトリクスを計算"""
    if trades_df.empty:
        return {}
    
    total_trades = len(trades_df)
    winning_trades = len(trades_df[trades_df['pnl'] > 0])
    win_rate = winning_trades / total_trades if total_trades > 0 else 0
    
    total_pnl = trades_df['pnl'].sum()
    total_return = (total_pnl / initial_capital) * 100
    avg_return = trades_df['pnl_rate'].mean() * 100
    
    # dynamic_position_sizeがある場合のみ計算
    if 'dynamic_position_size' in trades_df.columns:
        avg_position_size = trades_df['dynamic_position_size'].mean()
        position_size_std = trades_df['dynamic_position_size'].std()
    else:
        avg_position_size = 15.0  # デフォルト値
        position_size_std = 0.0
    
    return {
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'win_rate': win_rate * 100,
        'total_pnl': total_pnl,
        'total_return': total_return,
        'avg_return': avg_return,
        'avg_position_size': avg_position_size,
        'position_size_std': position_size_std
    }

def print_results(pattern, metrics, trades_df, base_metrics=None):
    """結果を表示"""
    print(f"\n📊 Realistic Dynamic Position Size Results ({pattern}):")
    print(f"  Total Trades: {metrics.get('total_trades', 0)}")
    print(f"  Win Rate: {metrics.get('win_rate', 0):.1f}%")
    print(f"  Total Return: {metrics.get('total_return', 0):.2f}%")
    print(f"  Average Return: {metrics.get('avg_return', 0):.2f}%")
    print(f"  Avg Position Size: {metrics.get('avg_position_size', 0):.1f}%")
    
    if base_metrics:
        base_return = base_metrics.get('total_return', 0)
        dynamic_return = metrics.get('total_return', 0)
        improvement = dynamic_return - base_return
        improvement_pct = (improvement / abs(base_return)) * 100 if base_return != 0 else 0
        
        print(f"\n📈 Improvement vs Base Strategy:")
        print(f"  Base Return (15% fixed): {base_return:.2f}%")
        print(f"  Dynamic Return: {dynamic_return:.2f}%")
        print(f"  Improvement: {improvement:.2f}% ({improvement_pct:+.1f}%)")
    
    if not trades_df.empty:
        print(f"\n  Position Size Distribution:")
        reasons = trades_df['position_reason'].value_counts()
        for reason, count in reasons.head(5).items():
            avg_size = trades_df[trades_df['position_reason'] == reason]['dynamic_position_size'].mean()
            print(f"    {reason}: {count} trades, avg {avg_size:.1f}%")

def run_pattern_comparison(breadth_df, config, start_date, end_date):
    """全4パターンの比較実行"""
    patterns = ['breadth_8ma', 'advanced_5stage', 'bearish_signal', 'bottom_3stage']
    results = {}
    
    # 共通のトレードデータを生成
    trades_data = generate_realistic_trades_for_period(start_date, end_date)
    base_metrics = calculate_metrics(pd.DataFrame(trades_data))
    
    print("\n🔄 Running comparison of all 4 patterns...")
    print("=" * 60)
    
    for pattern in patterns:
        print(f"\n--- Testing {pattern} ---")
        
        adjusted_trades = apply_dynamic_position_sizing(trades_data, breadth_df, pattern, config)
        if adjusted_trades is not None:
            metrics = calculate_metrics(adjusted_trades)
            results[pattern] = {
                'metrics': metrics,
                'trades': adjusted_trades
            }
            
            print(f"  Total Return: {metrics.get('total_return', 0):.2f}%")
            print(f"  Win Rate: {metrics.get('win_rate', 0):.1f}%")
            print(f"  Avg Position Size: {metrics.get('avg_position_size', 0):.1f}%")
    
    # 比較結果表示
    print_comparison_results(results, base_metrics)
    return results

def print_comparison_results(results, base_metrics):
    """全パターンの比較結果を表示"""
    print(f"\n{'='*70}")
    print("📊 REALISTIC PATTERN COMPARISON RESULTS")
    print(f"{'='*70}")
    
    # 結果をソート（総リターン順）
    sorted_results = sorted(
        [(pattern, data) for pattern, data in results.items() if data],
        key=lambda x: x[1]['metrics'].get('total_return', 0),
        reverse=True
    )
    
    print(f"{'Rank':<4} {'Pattern':<15} {'Return':<10} {'Improvement':<12} {'WinRate':<8} {'AvgPos':<8} {'Trades':<7}")
    print("-" * 70)
    
    base_return = base_metrics.get('total_return', 0)
    
    for i, (pattern, data) in enumerate(sorted_results, 1):
        metrics = data['metrics']
        
        total_return = metrics.get('total_return', 0)
        improvement = total_return - base_return
        win_rate = metrics.get('win_rate', 0)
        avg_pos = metrics.get('avg_position_size', 0)
        total_trades = metrics.get('total_trades', 0)
        
        print(f"{i:<4} {pattern:<15} {total_return:>8.2f}% {improvement:>+10.2f}% {win_rate:>6.1f}% {avg_pos:>6.1f}% {total_trades:>6}")
    
    # 最優秀パターンを強調
    if sorted_results:
        best_pattern, best_data = sorted_results[0]
        best_return = best_data['metrics'].get('total_return', 0)
        improvement = best_return - base_return
        print(f"\n🏆 Best Pattern: {best_pattern}")
        print(f"   Return: {best_return:.2f}% (improvement: {improvement:+.2f}%)")
        print(f"   Base (15% fixed): {base_return:.2f}%")

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description='Realistic Dynamic Position Size Backtest')
    parser.add_argument('--start_date', default='2020-09-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end_date', default='2025-06-30', help='End date (YYYY-MM-DD)')
    parser.add_argument('--pattern', default='breadth_8ma', 
                       help='Position sizing pattern')
    parser.add_argument('--breadth_csv', default='data/market_breadth_data_20250817_ma8.csv',
                       help='Market Breadth CSV file path')
    parser.add_argument('--compare_all', action='store_true', default=False,
                       help='Run all 4 patterns and compare results')
    
    args = parser.parse_args()
    
    print("Realistic Dynamic Position Size Backtest")
    print("=" * 60)
    
    if args.compare_all:
        print("Mode: Compare All 4 Patterns")
    else:
        print(f"Pattern: {args.pattern}")
    print(f"Period: {args.start_date} to {args.end_date}")
    
    # Market Breadthデータの読み込み
    breadth_df = load_market_breadth_data(args.breadth_csv)
    if breadth_df is None:
        return 1
    
    # 設定
    config = {
        'default_position_size': 15.0,
        'stress_position_size': 8.0,
        'normal_position_size': 15.0,
        'bullish_position_size': 20.0,
        'extreme_stress_position': 6.0,
        'stress_position': 10.0,
        'normal_position': 15.0,
        'bullish_position': 20.0,
        'extreme_bullish_position': 25.0,
        'bearish_reduction_multiplier': 0.6,
        'bearish_stage_multiplier': 0.7,
        'bottom_8ma_multiplier': 1.3,
        'bottom_200ma_multiplier': 1.6,
        'min_position_size': 5.0,
        'max_position_size': 25.0
    }
    
    try:
        if args.compare_all:
            # 全パターン比較実行
            results = run_pattern_comparison(breadth_df, config, args.start_date, args.end_date)
            if results:
                print(f"\n✅ Realistic pattern comparison completed!")
                return 0
        else:
            # 単一パターン実行
            trades_data = generate_realistic_trades_for_period(args.start_date, args.end_date)
            base_metrics = calculate_metrics(pd.DataFrame(trades_data))
            
            print(f"\n🔄 Applying dynamic position sizing ({args.pattern})...")
            adjusted_trades = apply_dynamic_position_sizing(trades_data, breadth_df, args.pattern, config)
            
            if adjusted_trades is not None:
                metrics = calculate_metrics(adjusted_trades)
                print_results(args.pattern, metrics, adjusted_trades, base_metrics)
                print(f"\n✅ Realistic Dynamic Position Size Backtest completed!")
                return 0
        
        print(f"\n❌ Failed to complete backtest")
        return 1
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())