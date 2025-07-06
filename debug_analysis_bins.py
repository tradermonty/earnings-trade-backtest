#!/usr/bin/env python3
"""
Debug script to analyze the binning issue in analysis charts
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import sys

# Load environment variables
load_dotenv()

# Add src directory to path
sys.path.append('src')

from data_fetcher import DataFetcher
from analysis_engine import AnalysisEngine

def debug_binning_issue():
    """Debug the binning issue with analysis charts"""
    
    # Load the most recent trades CSV
    csv_path = "/Users/takueisaotome/PycharmProjects/earnings-trade-backtest/reports/earnings_backtest_2025_01_01_2025_06_30.csv"
    
    print(f"Loading trades from: {csv_path}")
    trades_df = pd.read_csv(csv_path)
    
    print(f"Total trades: {len(trades_df)}")
    print("\nFirst few rows:")
    print(trades_df.head())
    
    # Initialize data fetcher and analysis engine
    api_key = os.getenv('EODHD_API_KEY')
    if not api_key:
        print("ERROR: EODHD_API_KEY not found in environment variables")
        return
    
    data_fetcher = DataFetcher(api_key)
    analysis_engine = AnalysisEngine(data_fetcher)
    
    # Debug the _add_eps_info method by examining just a few trades
    print("\n=== DEBUGGING PRE-EARNINGS CHANGE CALCULATION ===")
    
    # Take a sample of trades to debug
    sample_trades = trades_df.head(3).copy()
    
    # Manually calculate pre_earnings_change for debugging
    pre_earnings_changes = []
    for i, trade in sample_trades.iterrows():
        print(f"\nDebugging trade {i+1}: {trade['ticker']} on {trade['entry_date']}")
        
        # Calculate pre-earnings change (20 days before entry)
        pre_earnings_start = (pd.to_datetime(trade['entry_date']) - timedelta(days=30)).strftime('%Y-%m-%d')
        print(f"  Looking for data from {pre_earnings_start} to {trade['entry_date']}")
        
        try:
            stock_data = data_fetcher.get_historical_data(
                trade['ticker'],
                pre_earnings_start,
                trade['entry_date']
            )
            
            if stock_data is not None and len(stock_data) >= 20:
                print(f"  Retrieved {len(stock_data)} days of data")
                
                # Convert to DataFrame if it's a list of dicts
                if isinstance(stock_data, list):
                    stock_df = pd.DataFrame(stock_data)
                else:
                    stock_df = stock_data
                
                print(f"  Data shape: {stock_df.shape}")
                print(f"  Columns: {stock_df.columns.tolist()}")
                
                # Calculate 20-day change
                if len(stock_df) >= 20:
                    close_latest = stock_df['Close'].iloc[-1]
                    close_20_days_ago = stock_df['Close'].iloc[-20]
                    price_change = ((close_latest - close_20_days_ago) / close_20_days_ago) * 100
                    
                    print(f"  Close price 20 days ago: ${close_20_days_ago:.2f}")
                    print(f"  Close price latest: ${close_latest:.2f}")
                    print(f"  Pre-earnings change: {price_change:.2f}%")
                    
                    pre_earnings_changes.append(price_change)
                else:
                    print(f"  Not enough data for 20-day calculation")
                    pre_earnings_changes.append(0.0)
            else:
                print(f"  Failed to get sufficient data")
                pre_earnings_changes.append(0.0)
                
        except Exception as e:
            print(f"  Error: {str(e)}")
            pre_earnings_changes.append(0.0)
    
    sample_trades['pre_earnings_change'] = pre_earnings_changes
    print(f"\nCalculated pre_earnings_change values: {pre_earnings_changes}")
    
    # Now test the binning logic
    print("\n=== TESTING BINNING LOGIC ===")
    
    # Test with actual calculated values
    bins = [-float('inf'), -20, -10, 0, 10, 20, float('inf')]
    labels = ['<-20%', '-20~-10%', '-10~0%', '0~10%', '10~20%', '>20%']
    
    print(f"Bins: {bins}")
    print(f"Labels: {labels}")
    
    sample_trades['pre_earnings_range'] = pd.cut(sample_trades['pre_earnings_change'], 
                                               bins=bins, 
                                               labels=labels)
    
    print(f"\nBinning results:")
    for i, (idx, row) in enumerate(sample_trades.iterrows()):
        print(f"  {row['ticker']}: {row['pre_earnings_change']:.2f}% -> {row['pre_earnings_range']}")
    
    # Count by category
    print(f"\nCategory counts:")
    print(sample_trades['pre_earnings_range'].value_counts())
    
    # Test with a larger sample using dummy data
    print("\n=== TESTING WITH DUMMY DATA ===")
    
    # Create dummy data with known distribution
    dummy_changes = [-25, -15, -5, 5, 15, 25, -18, -8, 2, 12, 22, -30, -1, 0.5, 8, 18]
    dummy_df = pd.DataFrame({
        'pre_earnings_change': dummy_changes,
        'pnl_rate': [1.5] * len(dummy_changes),  # dummy P&L
        'pnl': [100] * len(dummy_changes)  # dummy P&L
    })
    
    print(f"Dummy data values: {dummy_changes}")
    
    dummy_df['pre_earnings_range'] = pd.cut(dummy_df['pre_earnings_change'], 
                                          bins=bins, 
                                          labels=labels)
    
    print(f"\nDummy data binning results:")
    print(dummy_df[['pre_earnings_change', 'pre_earnings_range']].to_string())
    
    print(f"\nDummy data category counts:")
    print(dummy_df['pre_earnings_range'].value_counts())
    
    # Test aggregation
    dummy_agg = dummy_df.groupby('pre_earnings_range', observed=True).agg({
        'pnl_rate': ['mean', 'count'],
        'pnl': 'sum'
    }).round(2)
    
    print(f"\nDummy aggregation result:")
    print(dummy_agg)

if __name__ == "__main__":
    debug_binning_issue()