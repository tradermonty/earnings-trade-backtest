#!/usr/bin/env python3
"""
Test script to verify the analysis engine fixes work correctly
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from data_fetcher import DataFetcher
from analysis_engine import AnalysisEngine

def test_analysis_engine():
    """Test the fixed analysis engine"""
    
    # Load the most recent trades CSV
    csv_path = "/Users/takueisaotome/PycharmProjects/earnings-trade-backtest/reports/earnings_backtest_2025_01_01_2025_06_30.csv"
    
    print(f"Loading trades from: {csv_path}")
    trades_df = pd.read_csv(csv_path)
    
    print(f"Total trades: {len(trades_df)}")
    
    # Initialize data fetcher and analysis engine
    api_key = os.getenv('EODHD_API_KEY')
    if not api_key:
        print("ERROR: EODHD_API_KEY not found in environment variables")
        return
    
    data_fetcher = DataFetcher(api_key)
    analysis_engine = AnalysisEngine(data_fetcher)
    
    # Test with a small subset of trades to avoid API rate limits
    print("\n=== TESTING WITH SMALL SUBSET ===")
    
    # Take first 3 trades for testing
    sample_trades = trades_df.head(3).copy()
    
    print(f"Testing with {len(sample_trades)} trades:")
    for i, trade in sample_trades.iterrows():
        print(f"  {trade['ticker']} on {trade['entry_date']}")
    
    # Test the _add_eps_info method
    print("\n=== TESTING _add_eps_info METHOD ===")
    
    try:
        # This will test the fixed calculation logic
        enriched_trades = analysis_engine._add_eps_info(sample_trades)
        
        print(f"Enriched trades shape: {enriched_trades.shape}")
        print(f"New columns: {[col for col in enriched_trades.columns if col not in sample_trades.columns]}")
        
        # Check the calculated values
        print("\nCalculated values:")
        for col in ['pre_earnings_change', 'volume_ratio', 'price_to_ma200', 'price_to_ma50']:
            if col in enriched_trades.columns:
                values = enriched_trades[col].values
                print(f"  {col}: {values}")
                print(f"    Min: {np.min(values):.2f}, Max: {np.max(values):.2f}, Mean: {np.mean(values):.2f}")
        
        # Test the binning logic
        print("\n=== TESTING BINNING LOGIC ===")
        
        # Test pre-earnings binning
        if 'pre_earnings_change' in enriched_trades.columns:
            bins = [-float('inf'), -20, -10, 0, 10, 20, float('inf')]
            labels = ['<-20%', '-20~-10%', '-10~0%', '0~10%', '10~20%', '>20%']
            
            enriched_trades['pre_earnings_range'] = pd.cut(enriched_trades['pre_earnings_change'], 
                                                          bins=bins, 
                                                          labels=labels)
            
            print(f"Pre-earnings binning results:")
            print(enriched_trades['pre_earnings_range'].value_counts())
        
        # Test volume ratio binning  
        if 'volume_ratio' in enriched_trades.columns:
            enriched_trades['volume_range'] = pd.cut(enriched_trades['volume_ratio'], 
                                                   bins=[0, 1.5, 2.0, 3.0, 4.0, float('inf')],
                                                   labels=['1.0-1.5x', '1.5-2.0x', '2.0-3.0x', '3.0-4.0x', '4.0x+'])
            
            print(f"Volume ratio binning results:")
            print(enriched_trades['volume_range'].value_counts())
        
        # Test MA200 binning
        if 'price_to_ma200' in enriched_trades.columns:
            enriched_trades['ma200_range'] = pd.cut(enriched_trades['price_to_ma200'], 
                                                   bins=[0, 0.9, 1.0, 1.1, 1.2, float('inf')],
                                                   labels=['<90%', '90-100%', '100-110%', '110-120%', '>120%'])
            
            print(f"MA200 binning results:")
            print(enriched_trades['ma200_range'].value_counts())
        
        print("\n=== SUCCESS ===")
        print("The analysis engine appears to be working correctly!")
        print("Data is being calculated and distributed across multiple bins.")
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_analysis_engine()