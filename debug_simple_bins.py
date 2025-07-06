#!/usr/bin/env python3
"""
Simple debug script to analyze the binning issue in analysis charts
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def debug_binning_issue():
    """Debug the binning issue with analysis charts"""
    
    # Load the most recent trades CSV
    csv_path = "/Users/takueisaotome/PycharmProjects/earnings-trade-backtest/reports/earnings_backtest_2025_01_01_2025_06_30.csv"
    
    print(f"Loading trades from: {csv_path}")
    trades_df = pd.read_csv(csv_path)
    
    print(f"Total trades: {len(trades_df)}")
    print("\nColumns in CSV:")
    print(trades_df.columns.tolist())
    
    print("\nFirst few rows:")
    print(trades_df.head())
    
    # The issue is that the CSV doesn't contain the analysis data that's calculated in _add_eps_info
    # Let's simulate what would happen with typical values
    
    print("\n=== SIMULATING PRE-EARNINGS CHANGE VALUES ===")
    
    # Create realistic pre-earnings change values
    # Based on typical stock behavior, most stocks move within -20% to +20% over 20 days
    np.random.seed(42)  # for reproducible results
    
    # Generate realistic distribution
    # Most stocks should have small changes, some larger
    pre_earnings_changes = []
    for i in range(len(trades_df)):
        # Create a realistic distribution
        # 70% between -10% and +10%
        # 20% between -20% and -10% or 10% and 20%
        # 10% outside -20% to +20%
        
        rand = np.random.random()
        if rand < 0.7:  # 70% in -10% to +10%
            change = np.random.uniform(-10, 10)
        elif rand < 0.9:  # 20% in wider range
            if np.random.random() < 0.5:
                change = np.random.uniform(-20, -10)
            else:
                change = np.random.uniform(10, 20)
        else:  # 10% outside normal range
            if np.random.random() < 0.5:
                change = np.random.uniform(-40, -20)
            else:
                change = np.random.uniform(20, 40)
        
        pre_earnings_changes.append(change)
    
    trades_df['pre_earnings_change'] = pre_earnings_changes
    
    print(f"\nGenerated {len(pre_earnings_changes)} pre-earnings change values")
    print(f"Min: {min(pre_earnings_changes):.2f}%")
    print(f"Max: {max(pre_earnings_changes):.2f}%")
    print(f"Mean: {np.mean(pre_earnings_changes):.2f}%")
    print(f"Median: {np.median(pre_earnings_changes):.2f}%")
    
    # Test histogram
    print(f"\nDistribution of values:")
    hist, bins = np.histogram(pre_earnings_changes, bins=10)
    for i in range(len(hist)):
        print(f"  {bins[i]:.1f}% to {bins[i+1]:.1f}%: {hist[i]} trades")
    
    # Now test the binning logic
    print("\n=== TESTING BINNING LOGIC ===")
    
    # Test with the bins used in the analysis engine
    bins = [-float('inf'), -20, -10, 0, 10, 20, float('inf')]
    labels = ['<-20%', '-20~-10%', '-10~0%', '0~10%', '10~20%', '>20%']
    
    print(f"Bins: {bins}")
    print(f"Labels: {labels}")
    
    trades_df['pre_earnings_range'] = pd.cut(trades_df['pre_earnings_change'], 
                                           bins=bins, 
                                           labels=labels)
    
    print(f"\nBinning results:")
    print(trades_df['pre_earnings_range'].value_counts())
    
    # Test aggregation (like in the analysis engine)
    pre_perf = trades_df.groupby('pre_earnings_range', observed=True).agg({
        'pnl_rate': ['mean', 'count'],
        'pnl': 'sum'
    }).round(2)
    
    pre_perf.columns = ['avg_return', 'trade_count', 'total_pnl']
    
    print(f"\nAggregation result:")
    print(pre_perf)
    
    # Check for any issues with the binning
    print(f"\nDebugging potential issues:")
    print(f"Any NaN values in pre_earnings_change? {trades_df['pre_earnings_change'].isna().sum()}")
    print(f"Any inf values in pre_earnings_change? {np.isinf(trades_df['pre_earnings_change']).sum()}")
    
    # Test with actual problematic scenario - all values in one bin
    print("\n=== TESTING PROBLEMATIC SCENARIO ===")
    
    # Create scenario where all values fall in one bin
    all_same_df = trades_df.copy()
    all_same_df['pre_earnings_change'] = [-5.0] * len(all_same_df)  # All values between -10% and 0%
    
    all_same_df['pre_earnings_range'] = pd.cut(all_same_df['pre_earnings_change'], 
                                              bins=bins, 
                                              labels=labels)
    
    print(f"All same values (-5%) binning:")
    print(all_same_df['pre_earnings_range'].value_counts())
    
    # Test volume ratio binning
    print("\n=== TESTING VOLUME RATIO BINNING ===")
    
    # Generate realistic volume ratios (1.0 to 5.0, mostly around 1.5-2.5)
    volume_ratios = []
    for i in range(len(trades_df)):
        # Most volume ratios should be between 1.0 and 3.0
        ratio = np.random.lognormal(0.5, 0.5)  # lognormal distribution
        ratio = max(1.0, min(6.0, ratio))  # cap between 1.0 and 6.0
        volume_ratios.append(ratio)
    
    trades_df['volume_ratio'] = volume_ratios
    
    print(f"Volume ratio stats:")
    print(f"Min: {min(volume_ratios):.2f}")
    print(f"Max: {max(volume_ratios):.2f}")
    print(f"Mean: {np.mean(volume_ratios):.2f}")
    
    # Test volume binning
    trades_df['volume_range'] = pd.cut(trades_df['volume_ratio'], 
                                     bins=[0, 1.5, 2.0, 3.0, 4.0, float('inf')],
                                     labels=['1.0-1.5x', '1.5-2.0x', '2.0-3.0x', '3.0-4.0x', '4.0x+'])
    
    print(f"\nVolume binning results:")
    print(trades_df['volume_range'].value_counts())
    
    # Test MA200 ratio binning
    print("\n=== TESTING MA200 RATIO BINNING ===")
    
    # Generate realistic MA200 ratios (0.8 to 1.3, mostly around 1.0)
    ma200_ratios = []
    for i in range(len(trades_df)):
        # Most ratios should be between 0.9 and 1.1
        ratio = np.random.normal(1.0, 0.1)  # normal distribution around 1.0
        ratio = max(0.7, min(1.5, ratio))  # cap between 0.7 and 1.5
        ma200_ratios.append(ratio)
    
    trades_df['price_to_ma200'] = ma200_ratios
    
    print(f"MA200 ratio stats:")
    print(f"Min: {min(ma200_ratios):.2f}")
    print(f"Max: {max(ma200_ratios):.2f}")
    print(f"Mean: {np.mean(ma200_ratios):.2f}")
    
    # Test MA200 binning
    trades_df['ma200_range'] = pd.cut(trades_df['price_to_ma200'], 
                                    bins=[0, 0.9, 1.0, 1.1, 1.2, float('inf')],
                                    labels=['<90%', '90-100%', '100-110%', '110-120%', '>120%'])
    
    print(f"\nMA200 binning results:")
    print(trades_df['ma200_range'].value_counts())
    
    print("\n=== SUMMARY ===")
    print("The binning logic appears to work correctly with realistic data.")
    print("The issue is likely that:")
    print("1. The _add_eps_info method is not calculating the values correctly")
    print("2. All calculated values are falling into the same range")
    print("3. There might be an issue with data fetching or calculation logic")

if __name__ == "__main__":
    debug_binning_issue()