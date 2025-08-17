#!/usr/bin/env python3
"""
動的ポジションサイズ調整の基本テスト
Import issues を避けるための簡易テストスクリプト
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# main.pyを直接実行して既存システムをテスト
import subprocess
from datetime import datetime

def test_basic_backtest():
    """既存システムの基本動作確認"""
    print("=== Testing Basic Backtest System ===")
    
    # 基本的なバックテストを実行
    cmd = [
        sys.executable, "main.py",
        "--start_date", "2020-09-01",
        "--end_date", "2020-12-31",
        "--stop_loss", "8",
        "--position_size", "15"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("✅ Basic backtest executed successfully")
            print("Output sample:")
            # 出力の最後の数行を表示
            lines = result.stdout.strip().split('\n')
            for line in lines[-5:]:
                print(f"  {line}")
        else:
            print("❌ Basic backtest failed")
            print("Error output:")
            print(result.stderr)
            
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("❌ Backtest timed out")
        return False
    except Exception as e:
        print(f"❌ Error running backtest: {e}")
        return False

def test_csv_reading():
    """Market Breadth CSVファイルの読み込みテスト"""
    print("\n=== Testing CSV Reading ===")
    
    csv_path = "data/market_breadth_data_20250817_ma8.csv"
    
    if not os.path.exists(csv_path):
        print(f"❌ CSV file not found: {csv_path}")
        return False
    
    try:
        import pandas as pd
        df = pd.read_csv(csv_path)
        
        print(f"✅ CSV loaded successfully")
        print(f"  Records: {len(df):,}")
        print(f"  Columns: {list(df.columns)}")
        print(f"  Date range: {df['Date'].min()} to {df['Date'].max()}")
        
        # データサンプルを表示
        print("  Sample data:")
        sample = df.head(3)[['Date', 'Breadth_Index_8MA', 'Bearish_Signal']].to_string(index=False)
        print(f"    {sample}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        return False

def main():
    """メイン関数"""
    print("Dynamic Position Size Backtest - Basic Test")
    print("=" * 50)
    
    # CSVファイルテスト
    csv_ok = test_csv_reading()
    
    # 基本バックテストテスト
    backtest_ok = test_basic_backtest()
    
    print("\n" + "=" * 50)
    print("TEST RESULTS:")
    print(f"  CSV Reading: {'✅' if csv_ok else '❌'}")
    print(f"  Basic Backtest: {'✅' if backtest_ok else '❌'}")
    
    if csv_ok and backtest_ok:
        print("\n🎉 All basic tests passed! Ready for dynamic position sizing.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please fix issues before proceeding.")
        return 1

if __name__ == "__main__":
    exit(main())