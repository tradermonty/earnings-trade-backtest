#!/usr/bin/env python3
"""
動的ポジションサイズ調整 - インポート問題修正版
元のrun_dynamic_backtest.pyをsubprocessベースで修正
"""

import sys
import os
import subprocess
import argparse
import json
from datetime import datetime

def run_subprocess_backtest(start_date, end_date, pattern):
    """subprocessを使って動的バックテストを実行"""
    
    print("Dynamic Position Size Backtest (Fixed Import Issues)")
    print("=" * 60)
    print(f"Pattern: {pattern}")
    print(f"Period: {start_date} to {end_date}")
    
    # CSVファイルの存在確認
    breadth_csv = "data/market_breadth_data_20250817_ma8.csv"
    if not os.path.exists(breadth_csv):
        print(f"❌ Market Breadth CSV not found: {breadth_csv}")
        return 1
    
    print(f"✅ Market Breadth CSV found: {breadth_csv}")
    
    # 簡易版スクリプトを使用
    cmd = [
        sys.executable,
        "scripts/run_dynamic_simple.py",
        "--start_date", start_date,
        "--end_date", end_date
    ]
    
    # パターン指定または比較モード
    if pattern == "compare_all":
        cmd.append("--compare_all")
    else:
        cmd.extend(["--pattern", pattern])
    
    try:
        print(f"\n🔄 Executing dynamic position sizing...")
        result = subprocess.run(cmd, check=True)
        
        print(f"\n✅ Dynamic Position Size Backtest completed successfully!")
        return 0
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Dynamic backtest failed with exit code {e.returncode}")
        return e.returncode
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description='Fixed Dynamic Position Size Backtest')
    parser.add_argument('--start_date', default='2020-09-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end_date', default='2025-06-30', help='End date (YYYY-MM-DD)')
    parser.add_argument('--pattern', default='breadth_8ma', 
                       help='Position sizing pattern (breadth_8ma, advanced_5stage, bearish_signal, bottom_3stage)')
    parser.add_argument('--compare_all', action='store_true', default=False,
                       help='Run all 4 patterns and compare results')
    
    args = parser.parse_args()
    
    # パターン名の修正（よくあるタイポを修正）
    pattern = args.pattern
    if pattern == 'bradth_8ma':
        pattern = 'breadth_8ma'
        print(f"⚠️  Pattern name corrected: 'bradth_8ma' → 'breadth_8ma'")
    elif pattern == 'breath_8ma':
        pattern = 'breadth_8ma'
        print(f"⚠️  Pattern name corrected: 'breath_8ma' → 'breadth_8ma'")
    
    # 比較モードの処理
    if args.compare_all:
        pattern = "compare_all"
    
    return run_subprocess_backtest(args.start_date, args.end_date, pattern)

if __name__ == "__main__":
    exit(main())