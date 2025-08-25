#!/usr/bin/env python3
"""
実際のバックテストデータを使用した動的ポジションサイズ調整
既存のmain.pyを変更せずに、subprocessで実行し、結果を後処理で動的調整

Usage:
    python run_dynamic_backtest_real.py --start_date 2020-09-01 --end_date 2025-06-30 --pattern breadth_8ma --stop_loss 10
"""

import sys
import os
import subprocess
import argparse
import pandas as pd
import re
import tempfile
from datetime import datetime
import json

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

def run_base_backtest(args):
    """既存のmain.pyでバックテストを実行"""
    print("🔄 Running base backtest with existing system...")
    
    # 既存システムのコマンドを構築
    cmd = [
        sys.executable, "main.py",
        "--start_date", args.start_date,
        "--end_date", args.end_date,
        "--position_size", str(args.position_size),
        "--margin_ratio", str(args.margin_ratio),
        "--max_holding_days", str(args.max_holding_days),
        "--screener_price_min", str(args.screener_price_min),
        "--min_market_cap", str(args.min_market_cap),
        "--stop_loss", str(args.stop_loss)
    ]
    
    # 追加オプション
    if args.use_eodhd:
        cmd.append("--use_eodhd")
    if not args.partial_profit:  # no_partial_profitが正しいパラメータ
        cmd.append("--no_partial_profit")
    if args.sp500_only:
        cmd.append("--sp500_only")
    if args.enable_earnings_date_validation:
        cmd.append("--enable_date_validation")
    
    try:
        # バックテスト実行
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)  # 30分タイムアウト
        
        if result.returncode != 0:
            print(f"❌ Base backtest failed:")
            print("STDERR:", result.stderr[-1000:])
            return None, None
        
        print(f"✅ Base backtest completed")
        
        # 出力から基本メトリクスを抽出
        base_metrics = extract_base_metrics(result.stdout)
        
        # CSVファイルを探して読み込み
        csv_file = find_generated_csv_file()
        if csv_file:
            trades_data = pd.read_csv(csv_file)
            print(f"📊 Loaded {len(trades_data)} trades from {csv_file}")
            return trades_data, base_metrics
        else:
            print("⚠️  CSV file not found, falling back to output parsing")
            return None, base_metrics
        
    except subprocess.TimeoutExpired:
        print(f"❌ Base backtest timed out (30 minutes)")
        return None, None
    except Exception as e:
        print(f"❌ Error running base backtest: {e}")
        return None, None

def extract_base_metrics(output):
    """バックテスト出力から基本メトリクスを抽出"""
    metrics = {}
    
    lines = output.split('\n')
    for line in lines:
        if "実行されたトレード数:" in line or "Total trades:" in line:
            numbers = re.findall(r'\d+', line)
            if numbers:
                metrics['total_trades'] = int(numbers[0])
        elif "総リターン:" in line or "Total return:" in line:
            match = re.search(r'([\d.]+)%', line)
            if match:
                metrics['total_return'] = float(match.group(1))
        elif "勝率:" in line or "Win rate:" in line:
            match = re.search(r'([\d.]+)%', line)
            if match:
                metrics['win_rate'] = float(match.group(1))
        elif "最終資産:" in line or "Final value:" in line:
            match = re.search(r'\$([\d,]+\.?\d*)', line)
            if match:
                value_str = match.group(1).replace(',', '')
                metrics['final_value'] = float(value_str)
    
    return metrics

def find_generated_csv_file():
    """生成されたCSVファイルを探す"""
    # 最新のCSVファイルを探す
    csv_files = [f for f in os.listdir('.') if f.endswith('.csv') and 'earnings_backtest' in f]
    if csv_files:
        # 最新のファイルを返す
        latest_csv = max(csv_files, key=os.path.getmtime)
        return latest_csv
    return None

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

def apply_dynamic_position_sizing(trades_df, breadth_df, pattern, config):
    """実際のトレードデータに動的ポジションサイズを適用"""
    if trades_df is None or len(trades_df) == 0:
        print("❌ No trades data to process")
        return None
    
    print(f"📊 Applying dynamic position sizing to {len(trades_df)} real trades...")
    
    # entry_dateカラムを探す
    date_column = None
    for col in ['entry_date', 'date', 'Date', 'Entry Date']:
        if col in trades_df.columns:
            date_column = col
            break
    
    if not date_column:
        print("❌ No date column found in trades data")
        return None
    
    trades_df[date_column] = pd.to_datetime(trades_df[date_column])
    
    results = []
    original_position_size = config['default_position_size']
    
    for _, trade in trades_df.iterrows():
        entry_date = trade[date_column]
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
        
        # P&Lを調整（ポジションサイズに比例）
        if 'pnl' in trade:
            adjusted_trade['pnl'] = trade['pnl'] * position_multiplier
        if 'total_return' in trade:
            adjusted_trade['total_return'] = trade['total_return'] * position_multiplier
        
        if market_data:
            adjusted_trade['breadth_8ma'] = market_data['breadth_8ma']
            adjusted_trade['bearish_signal'] = market_data['bearish_signal']
        
        results.append(adjusted_trade)
    
    return pd.DataFrame(results)

def calculate_adjusted_metrics(adjusted_trades_df, base_metrics, initial_capital=100000):
    """調整後のメトリクスを計算"""
    if adjusted_trades_df is None or len(adjusted_trades_df) == 0:
        return {}
    
    total_trades = len(adjusted_trades_df)
    
    # P&L計算
    if 'pnl' in adjusted_trades_df.columns:
        total_pnl = adjusted_trades_df['pnl'].sum()
        winning_trades = len(adjusted_trades_df[adjusted_trades_df['pnl'] > 0])
    else:
        total_pnl = 0
        winning_trades = 0
    
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    total_return = (total_pnl / initial_capital) * 100
    avg_position_size = adjusted_trades_df['dynamic_position_size'].mean()
    
    return {
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'total_return': total_return,
        'avg_position_size': avg_position_size,
        'base_total_return': base_metrics.get('total_return', 0)
    }

def print_results(pattern, metrics, adjusted_trades_df, base_metrics):
    """結果を表示"""
    print(f"\n" + "="*60)
    print(f"📊 Real Data Dynamic Position Size Results ({pattern})")
    print(f"="*60)
    print(f"Total Trades: {metrics.get('total_trades', 0)}")
    print(f"Win Rate: {metrics.get('win_rate', 0):.1f}%")
    print(f"Total Return: {metrics.get('total_return', 0):.2f}%")
    print(f"Avg Position Size: {metrics.get('avg_position_size', 0):.1f}%")
    
    base_return = base_metrics.get('total_return', 0)
    dynamic_return = metrics.get('total_return', 0)
    if base_return != 0:
        improvement = dynamic_return - base_return
        improvement_pct = (improvement / abs(base_return)) * 100
        print(f"\n📈 Improvement vs Base Strategy:")
        print(f"Base Return (fixed 15%): {base_return:.2f}%")
        print(f"Dynamic Return: {dynamic_return:.2f}%")
        print(f"Improvement: {improvement:.2f}% ({improvement_pct:+.1f}%)")
    
    if adjusted_trades_df is not None and not adjusted_trades_df.empty:
        print(f"\nPosition Size Distribution:")
        reasons = adjusted_trades_df['position_reason'].value_counts()
        for reason, count in reasons.head(5).items():
            avg_size = adjusted_trades_df[adjusted_trades_df['position_reason'] == reason]['dynamic_position_size'].mean()
            print(f"  {reason}: {count} trades, avg {avg_size:.1f}%")

def parse_arguments():
    """コマンドライン引数の解析"""
    parser = argparse.ArgumentParser(description='Real Data Dynamic Position Size Backtest')
    
    # 既存main.pyと同じ引数
    parser.add_argument('--start_date', type=str, default='2020-09-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end_date', type=str, default='2025-06-30', help='End date (YYYY-MM-DD)')
    parser.add_argument('--position_size', type=float, default=15.0, help='Base position size percentage')
    parser.add_argument('--margin_ratio', type=float, default=1.5, help='Margin ratio')
    parser.add_argument('--max_holding_days', type=int, default=90, help='Maximum holding period')
    parser.add_argument('--screener_price_min', type=float, default=30.0, help='Minimum stock price')
    parser.add_argument('--min_market_cap', type=float, default=5.0, help='Minimum market cap (billions)')
    parser.add_argument('--stop_loss', type=float, default=10.0, help='Stop loss percentage')
    parser.add_argument('--use_eodhd', action='store_true', help='Use EODHD instead of FMP')
    parser.add_argument('--partial_profit', action='store_true', default=True, help='Enable partial profit taking')
    parser.add_argument('--sp500_only', action='store_true', help='S&P 500 only')
    parser.add_argument('--enable_earnings_date_validation', action='store_true', help='Enable date validation')
    
    # 動的ポジションサイズ専用引数
    parser.add_argument('--pattern', type=str, default='breadth_8ma',
                       choices=['breadth_8ma', 'advanced_5stage', 'bearish_signal', 'bottom_3stage'],
                       help='Dynamic position sizing pattern')
    parser.add_argument('--breadth_csv', type=str, default='data/market_breadth_data_20250817_ma8.csv',
                       help='Market Breadth CSV file path')
    
    return parser.parse_args()

def main():
    """メイン実行関数"""
    args = parse_arguments()
    
    print("Real Data Dynamic Position Size Backtest")
    print("=" * 60)
    print(f"Pattern: {args.pattern}")
    print(f"Period: {args.start_date} to {args.end_date}")
    print(f"Base Position Size: {args.position_size}%")
    
    # Market Breadthデータの読み込み
    breadth_df = load_market_breadth_data(args.breadth_csv)
    if breadth_df is None:
        return 1
    
    # 動的ポジションサイズ設定
    config = {
        'default_position_size': args.position_size,
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
        # 1. 既存システムでバックテストを実行
        trades_df, base_metrics = run_base_backtest(args)
        
        if trades_df is None:
            print("❌ Failed to get trade data from base backtest")
            return 1
        
        print(f"📊 Base backtest results:")
        print(f"   Total Trades: {base_metrics.get('total_trades', 0)}")
        print(f"   Total Return: {base_metrics.get('total_return', 0):.2f}%")
        print(f"   Win Rate: {base_metrics.get('win_rate', 0):.1f}%")
        
        # 2. 動的ポジションサイズを適用
        print(f"\n🔄 Applying dynamic position sizing ({args.pattern})...")
        adjusted_trades_df = apply_dynamic_position_sizing(trades_df, breadth_df, args.pattern, config)
        
        if adjusted_trades_df is not None:
            # 3. メトリクスを計算
            adjusted_metrics = calculate_adjusted_metrics(adjusted_trades_df, base_metrics)
            
            # 4. 結果を表示
            print_results(args.pattern, adjusted_metrics, adjusted_trades_df, base_metrics)
            
            # 5. 結果をCSVに保存
            output_csv = f"dynamic_backtest_{args.pattern}_{args.start_date}_{args.end_date}.csv"
            adjusted_trades_df.to_csv(output_csv, index=False)
            print(f"\n💾 Results saved to: {output_csv}")
            
            print(f"\n✅ Real Data Dynamic Position Size Backtest completed!")
            return 0
        else:
            print(f"\n❌ Failed to apply dynamic position sizing")
            return 1
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())