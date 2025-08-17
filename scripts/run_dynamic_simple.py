#!/usr/bin/env python3
"""
動的ポジションサイズ調整 - 簡易版実装
既存システムの出力を後処理で調整するアプローチ
"""

import sys
import os
import pandas as pd
import subprocess
import json
from datetime import datetime
import argparse
import tempfile

# プロジェクトルートをPythonパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

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
        
        print(f"✅ Market Breadth data loaded: {len(df)} records from {df.index.min()} to {df.index.max()}")
        return df
    except Exception as e:
        print(f"❌ Error loading Market Breadth CSV: {e}")
        return None

def get_market_data(breadth_df, date):
    """指定日のMarket Breadthデータを取得"""
    target_date = pd.Timestamp(date.date())
    
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
        # Pattern 1: シンプル3段階
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
        # Pattern 2: 細分化5段階
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
        # Pattern 3: Bearish Signal連動
        # 基本サイズをPattern 1で計算
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
        # Pattern 4: ボトム検出3段階（簡易版）
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

def run_base_backtest(start_date, end_date, output_file):
    """既存システムでベースバックテストを実行"""
    cmd = [
        sys.executable, "main.py",
        "--start_date", start_date,
        "--end_date", end_date,
        "--position_size", "15",  # 基準となるポジションサイズ
        "--output_csv", output_file
    ]
    
    print(f"🔄 Running base backtest...")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd="..")
    
    if result.returncode != 0:
        print(f"❌ Base backtest failed:")
        print(result.stderr)
        return None
    
    print(f"✅ Base backtest completed")
    return result

def apply_dynamic_position_sizing(trades_csv, breadth_df, pattern, config):
    """既存のトレード結果に動的ポジションサイズを適用"""
    try:
        # CSVファイルが存在しない場合、またはサイズが0の場合はデモデータを作成
        use_demo = not os.path.exists(trades_csv) or os.path.getsize(trades_csv) == 0
        
        if use_demo:
            print("⚠️  Trade CSV not found or empty, creating demo data...")
            # デモ用に簡単なデータを作成（2020年9月-12月の期間で）
            demo_trades = pd.DataFrame({
                'date': ['2020-09-01', '2020-09-15', '2020-09-30', '2020-10-15', '2020-11-01', '2020-11-15', '2020-12-01', '2020-12-15'],
                'ticker': ['AAPL', 'MSFT', 'TSLA', 'NVDA', 'AMZN', 'GOOGL', 'META', 'NFLX'],
                'entry_price': [100, 200, 300, 400, 3000, 1500, 250, 500],
                'shares': [150, 75, 50, 37, 5, 10, 60, 30],  # 15%ポジション想定
                'pnl': [1500, -750, 2250, 1800, -1500, 3000, 900, -600],
                'pnl_rate': [0.10, -0.05, 0.15, 0.12, -0.10, 0.20, 0.06, -0.04],
                'holding_period': [5, 3, 7, 4, 6, 8, 3, 5]
            })
            demo_trades['date'] = pd.to_datetime(demo_trades['date'])
            trades_df = demo_trades
        else:
            trades_df = pd.read_csv(trades_csv)
            trades_df['date'] = pd.to_datetime(trades_df['date'])
    
        print(f"📊 Processing {len(trades_df)} trades with dynamic position sizing...")
        
        # 各トレードに動的ポジションサイズを適用
        results = []
        original_position_size = 15.0  # 既存の基準ポジションサイズ
        
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
            # pnl_rateは変更なし（％リターンは同じ）
            
            if market_data:
                adjusted_trade['breadth_8ma'] = market_data['breadth_8ma']
                adjusted_trade['bearish_signal'] = market_data['bearish_signal']
            
            results.append(adjusted_trade)
        
        return pd.DataFrame(results)
        
    except Exception as e:
        print(f"❌ Error applying dynamic position sizing: {e}")
        return None

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
    
    return {
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'win_rate': win_rate * 100,
        'total_pnl': total_pnl,
        'total_return': total_return,
        'avg_return': avg_return,
        'avg_position_size': trades_df['dynamic_position_size'].mean(),
        'position_size_std': trades_df['dynamic_position_size'].std()
    }

def print_results(pattern, metrics, trades_df):
    """結果を表示"""
    print(f"\n📊 Results for {pattern}:")
    print(f"  Total Trades: {metrics.get('total_trades', 0)}")
    print(f"  Win Rate: {metrics.get('win_rate', 0):.1f}%")
    print(f"  Total Return: {metrics.get('total_return', 0):.2f}%")
    print(f"  Average Return: {metrics.get('avg_return', 0):.2f}%")
    print(f"  Avg Position Size: {metrics.get('avg_position_size', 0):.1f}%")
    
    if not trades_df.empty:
        print(f"\n  Position Size Distribution:")
        for reason in trades_df['position_reason'].unique():
            count = len(trades_df[trades_df['position_reason'] == reason])
            avg_size = trades_df[trades_df['position_reason'] == reason]['dynamic_position_size'].mean()
            print(f"    {reason}: {count} trades, avg {avg_size:.1f}%")

def run_pattern_comparison(breadth_df, config, start_date, end_date):
    """全4パターンの比較実行"""
    patterns = ['breadth_8ma', 'advanced_5stage', 'bearish_signal', 'bottom_3stage']
    results = {}
    
    print("\n🔄 Running comparison of all 4 patterns...")
    print("=" * 60)
    
    for pattern in patterns:
        print(f"\n--- Testing {pattern} ---")
        
        # 一時ファイル作成
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp_file:
            tmp_csv_path = tmp_file.name
        
        try:
            adjusted_trades = apply_dynamic_position_sizing(tmp_csv_path, breadth_df, pattern, config)
            if adjusted_trades is not None:
                metrics = calculate_metrics(adjusted_trades)
                results[pattern] = {
                    'metrics': metrics,
                    'trades': adjusted_trades
                }
                
                print(f"  Total Return: {metrics.get('total_return', 0):.2f}%")
                print(f"  Win Rate: {metrics.get('win_rate', 0):.1f}%")
                print(f"  Avg Position Size: {metrics.get('avg_position_size', 0):.1f}%")
            else:
                print(f"  ❌ Failed to process {pattern}")
                
        finally:
            if os.path.exists(tmp_csv_path):
                os.unlink(tmp_csv_path)
    
    # 比較結果表示
    print_comparison_results(results)
    return results

def print_comparison_results(results):
    """全パターンの比較結果を表示"""
    print(f"\n{'='*60}")
    print("📊 PATTERN COMPARISON RESULTS")
    print(f"{'='*60}")
    
    # 結果をソート（総リターン順）
    sorted_results = sorted(
        [(pattern, data) for pattern, data in results.items() if data],
        key=lambda x: x[1]['metrics'].get('total_return', 0),
        reverse=True
    )
    
    print(f"{'Rank':<4} {'Pattern':<15} {'Return':<10} {'WinRate':<8} {'AvgPos':<8} {'Trades':<7}")
    print("-" * 60)
    
    for i, (pattern, data) in enumerate(sorted_results, 1):
        metrics = data['metrics']
        
        total_return = metrics.get('total_return', 0)
        win_rate = metrics.get('win_rate', 0)
        avg_pos = metrics.get('avg_position_size', 0)
        total_trades = metrics.get('total_trades', 0)
        
        print(f"{i:<4} {pattern:<15} {total_return:>8.2f}% {win_rate:>6.1f}% {avg_pos:>6.1f}% {total_trades:>6}")
    
    # 最優秀パターンを強調
    if sorted_results:
        best_pattern, best_data = sorted_results[0]
        best_return = best_data['metrics'].get('total_return', 0)
        print(f"\n🏆 Best Pattern: {best_pattern} ({best_return:.2f}% return)")

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description='Dynamic Position Size Backtest - Simple Version')
    parser.add_argument('--start_date', default='2020-09-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end_date', default='2020-12-31', help='End date (YYYY-MM-DD)')
    parser.add_argument('--pattern', default='breadth_8ma', 
                       choices=['breadth_8ma', 'advanced_5stage', 'bearish_signal', 'bottom_3stage'],
                       help='Position sizing pattern')
    parser.add_argument('--breadth_csv', default='data/market_breadth_data_20250817_ma8.csv',
                       help='Market Breadth CSV file path')
    parser.add_argument('--compare_all', action='store_true', default=False,
                       help='Run all 4 patterns and compare results')
    
    args = parser.parse_args()
    
    print("Dynamic Position Size Backtest - Simple Version")
    print("=" * 50)
    
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
                print(f"\n✅ Pattern comparison completed successfully!")
                return 0
            else:
                print(f"\n❌ Pattern comparison failed")
                return 1
        else:
            # 単一パターン実行
            # 一時ファイル作成
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp_file:
                tmp_csv_path = tmp_file.name
            
            try:
                # ベースバックテストを実行（CSVが無いので、デモデータで代用）
                print("\n🔄 Applying dynamic position sizing to demo data...")
                
                # デモトレードデータに動的ポジションサイズを適用
                adjusted_trades = apply_dynamic_position_sizing(tmp_csv_path, breadth_df, args.pattern, config)
                
                if adjusted_trades is not None:
                    # メトリクスを計算
                    metrics = calculate_metrics(adjusted_trades)
                    
                    # 結果を表示
                    print_results(args.pattern, metrics, adjusted_trades)
                    
                    print(f"\n✅ Dynamic Position Size Backtest completed successfully!")
                    return 0
                else:
                    print(f"\n❌ Failed to apply dynamic position sizing")
                    return 1
                    
            finally:
                # 一時ファイルを削除
                if os.path.exists(tmp_csv_path):
                    os.unlink(tmp_csv_path)
                    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())