#!/usr/bin/env python3
"""
Compare backtest results between main.py (normal) and run_backtest_from_aggregated.py (finviz) approaches
"""

import pandas as pd
import numpy as np

def load_and_analyze_results():
    # Load both CSV files
    normal_df = pd.read_csv('../../reports/earnings_backtest_2024_09_01_2024_12_31_sp500_normal.csv')
    finviz_df = pd.read_csv('../../reports/earnings_backtest_2024_09_01_2024_12_31_sp500_finviz.csv')
    
    print("=== BACKTEST COMPARISON ANALYSIS ===\n")
    print("Period: 2024-09-01 to 2024-12-31 (S&P 500)")
    print("Normal: main.py approach")
    print("Finviz: run_backtest_from_aggregated.py approach\n")
    
    # Basic statistics
    print("=== BASIC STATISTICS ===")
    print(f"Normal trades: {len(normal_df)}")
    print(f"Finviz trades: {len(finviz_df)}")
    print(f"Difference: {len(finviz_df) - len(normal_df)} trades\n")
    
    # Performance metrics
    print("=== PERFORMANCE METRICS ===")
    
    def calculate_metrics(df, label):
        total_pnl = df['pnl'].sum()
        total_return_rate = df['pnl_rate'].mean()
        win_rate = (df['pnl'] > 0).mean() * 100
        avg_win = df[df['pnl'] > 0]['pnl_rate'].mean() * 100 if (df['pnl'] > 0).any() else 0
        avg_loss = df[df['pnl'] < 0]['pnl_rate'].mean() * 100 if (df['pnl'] < 0).any() else 0
        avg_holding = df['holding_period'].mean()
        
        print(f"{label}:")
        print(f"  Total P&L: ${total_pnl:,.2f}")
        print(f"  Avg Return Rate: {total_return_rate*100:.2f}%")
        print(f"  Win Rate: {win_rate:.1f}%")
        print(f"  Avg Win: {avg_win:.2f}%")
        print(f"  Avg Loss: {avg_loss:.2f}%")
        print(f"  Avg Holding Period: {avg_holding:.1f} days")
        print()
        
        return {
            'total_pnl': total_pnl,
            'avg_return': total_return_rate,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'avg_holding': avg_holding
        }
    
    normal_metrics = calculate_metrics(normal_df, "Normal (main.py)")
    finviz_metrics = calculate_metrics(finviz_df, "Finviz (aggregated)")
    
    # Exit reason analysis
    print("=== EXIT REASON ANALYSIS ===")
    print("Normal:")
    normal_exits = normal_df['exit_reason'].value_counts()
    for reason, count in normal_exits.items():
        print(f"  {reason}: {count} ({count/len(normal_df)*100:.1f}%)")
    
    print("\nFinviz:")
    finviz_exits = finviz_df['exit_reason'].value_counts()
    for reason, count in finviz_exits.items():
        print(f"  {reason}: {count} ({count/len(finviz_df)*100:.1f}%)")
    print()
    
    # Stock overlap analysis
    print("=== STOCK OVERLAP ANALYSIS ===")
    normal_stocks = set(normal_df['ticker'].unique())
    finviz_stocks = set(finviz_df['ticker'].unique())
    
    common_stocks = normal_stocks.intersection(finviz_stocks)
    normal_only = normal_stocks - finviz_stocks
    finviz_only = finviz_stocks - normal_stocks
    
    print(f"Stocks in both: {len(common_stocks)} ({sorted(list(common_stocks))})")
    print(f"Normal only: {len(normal_only)} ({sorted(list(normal_only))})")
    print(f"Finviz only: {len(finviz_only)} ({sorted(list(finviz_only))})")
    print()
    
    # Surprise rate analysis
    print("=== SURPRISE RATE ANALYSIS ===")
    print(f"Normal - Avg surprise rate: {normal_df['surprise_rate'].mean():.2f}%")
    print(f"Normal - Max surprise rate: {normal_df['surprise_rate'].max():.2f}%")
    print(f"Normal - Min surprise rate: {normal_df['surprise_rate'].min():.2f}%")
    
    print(f"Finviz - Avg surprise rate: {finviz_df['surprise_rate'].mean():.2f}%")
    print(f"Finviz - Max surprise rate: {finviz_df['surprise_rate'].max():.2f}%")
    print(f"Finviz - Min surprise rate: {finviz_df['surprise_rate'].min():.2f}%")
    print()
    
    # Gap analysis
    print("=== GAP ANALYSIS ===")
    print(f"Normal - Avg gap: {normal_df['gap'].mean():.2f}%")
    print(f"Normal - Max gap: {normal_df['gap'].max():.2f}%")
    print(f"Normal - Min gap: {normal_df['gap'].min():.2f}%")
    
    print(f"Finviz - Avg gap: {finviz_df['gap'].mean():.2f}%")
    print(f"Finviz - Max gap: {finviz_df['gap'].max():.2f}%")
    print(f"Finviz - Min gap: {finviz_df['gap'].min():.2f}%")
    print()
    
    # Date distribution
    print("=== ENTRY DATE DISTRIBUTION ===")
    normal_df['entry_month'] = pd.to_datetime(normal_df['entry_date']).dt.strftime('%Y-%m')
    finviz_df['entry_month'] = pd.to_datetime(finviz_df['entry_date']).dt.strftime('%Y-%m')
    
    print("Normal:")
    normal_dates = normal_df['entry_month'].value_counts().sort_index()
    for month, count in normal_dates.items():
        print(f"  {month}: {count} trades")
    
    print("\nFinviz:")
    finviz_dates = finviz_df['entry_month'].value_counts().sort_index()
    for month, count in finviz_dates.items():
        print(f"  {month}: {count} trades")
    print()
    
    # Key differences summary
    print("=== KEY DIFFERENCES SUMMARY ===")
    pnl_diff = finviz_metrics['total_pnl'] - normal_metrics['total_pnl']
    print(f"P&L Difference: ${pnl_diff:,.2f} ({'better' if pnl_diff > 0 else 'worse'} for Finviz)")
    
    return_diff = finviz_metrics['avg_return'] - normal_metrics['avg_return']
    print(f"Avg Return Difference: {return_diff*100:.2f}% ({'better' if return_diff > 0 else 'worse'} for Finviz)")
    
    win_diff = finviz_metrics['win_rate'] - normal_metrics['win_rate']
    print(f"Win Rate Difference: {win_diff:.1f}% ({'better' if win_diff > 0 else 'worse'} for Finviz)")
    
    trade_diff = len(finviz_df) - len(normal_df)
    print(f"Trade Count Difference: {trade_diff} ({'more' if trade_diff > 0 else 'fewer'} trades for Finviz)")

if __name__ == "__main__":
    load_and_analyze_results()