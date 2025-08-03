#!/usr/bin/env python3
"""
Compare backtest results between XGBoost-optimized and baseline approaches
for the full period 2024-09-01 to 2025-07-30
"""

import pandas as pd
import numpy as np
from datetime import datetime

def load_and_analyze_comparison():
    # Load both CSV files
    baseline_df = pd.read_csv('../../reports/earnings_backtest_2024_09_01_2025_07_30_all_finviz.csv')
    xgboost_df = pd.read_csv('../../reports/earnings_backtest_2024_09_01_2025_07_30_finviz_xgboost.csv')
    
    print("=== XGBOOST PARAMETER COMPARISON ANALYSIS ===")
    print("Period: 2024-09-01 to 2025-07-30")
    print("Baseline: Standard finviz parameters (no XGBoost optimization)")
    print("XGBoost: With optimized parameters (P/S, P/E, ROA, etc.)\n")
    
    # Basic statistics
    print("=== BASIC STATISTICS ===")
    print(f"Baseline trades: {len(baseline_df)}")
    print(f"XGBoost trades: {len(xgboost_df)}")
    print(f"Trade reduction: {len(baseline_df) - len(xgboost_df)} ({(1 - len(xgboost_df)/len(baseline_df))*100:.1f}% fewer trades)\n")
    
    # Performance metrics calculation
    def calculate_metrics(df, label):
        total_pnl = df['pnl'].sum()
        avg_pnl_rate = df['pnl_rate'].mean()
        win_rate = (df['pnl'] > 0).mean() * 100
        
        # Separate wins and losses
        winners = df[df['pnl'] > 0]
        losers = df[df['pnl'] <= 0]
        
        avg_win = winners['pnl_rate'].mean() * 100 if len(winners) > 0 else 0
        avg_loss = losers['pnl_rate'].mean() * 100 if len(losers) > 0 else 0
        profit_factor = abs(winners['pnl'].sum() / losers['pnl'].sum()) if len(losers) > 0 and losers['pnl'].sum() != 0 else float('inf')
        
        avg_holding = df['holding_period'].mean()
        
        # Calculate expected value per trade
        expected_value = (win_rate/100 * avg_win + (1-win_rate/100) * avg_loss)
        
        print(f"=== {label} ===")
        print(f"Total P&L: ${total_pnl:,.2f}")
        print(f"Average Return per Trade: {avg_pnl_rate*100:.2f}%")
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Average Win: {avg_win:.2f}%")
        print(f"Average Loss: {avg_loss:.2f}%")
        print(f"Profit Factor: {profit_factor:.2f}")
        print(f"Expected Value: {expected_value:.2f}%")
        print(f"Average Holding Period: {avg_holding:.1f} days")
        print()
        
        return {
            'total_pnl': total_pnl,
            'avg_return': avg_pnl_rate,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'expected_value': expected_value,
            'avg_holding': avg_holding
        }
    
    baseline_metrics = calculate_metrics(baseline_df, "BASELINE (No XGBoost)")
    xgboost_metrics = calculate_metrics(xgboost_df, "XGBOOST OPTIMIZED")
    
    # Exit reason analysis
    print("=== EXIT REASON DISTRIBUTION ===")
    print("Baseline:")
    for reason, count in baseline_df['exit_reason'].value_counts().items():
        print(f"  {reason}: {count} ({count/len(baseline_df)*100:.1f}%)")
    
    print("\nXGBoost:")
    for reason, count in xgboost_df['exit_reason'].value_counts().items():
        print(f"  {reason}: {count} ({count/len(xgboost_df)*100:.1f}%)")
    
    # Time period analysis
    print("\n=== TEMPORAL DISTRIBUTION ===")
    baseline_df['entry_month'] = pd.to_datetime(baseline_df['entry_date']).dt.to_period('M')
    xgboost_df['entry_month'] = pd.to_datetime(xgboost_df['entry_date']).dt.to_period('M')
    
    print("Monthly trade distribution:")
    all_months = sorted(set(baseline_df['entry_month'].unique()) | set(xgboost_df['entry_month'].unique()))
    
    for month in all_months:
        baseline_count = (baseline_df['entry_month'] == month).sum()
        xgboost_count = (xgboost_df['entry_month'] == month).sum()
        print(f"  {month}: Baseline={baseline_count}, XGBoost={xgboost_count}")
    
    # Surprise rate comparison
    print("\n=== EARNINGS SURPRISE ANALYSIS ===")
    print(f"Baseline - Average surprise: {baseline_df['surprise_rate'].mean():.2f}%")
    print(f"Baseline - Median surprise: {baseline_df['surprise_rate'].median():.2f}%")
    print(f"XGBoost - Average surprise: {xgboost_df['surprise_rate'].mean():.2f}%")
    print(f"XGBoost - Median surprise: {xgboost_df['surprise_rate'].median():.2f}%")
    
    # Market cap distribution
    print("\n=== MARKET CAP DISTRIBUTION ===")
    for approach, df in [("Baseline", baseline_df), ("XGBoost", xgboost_df)]:
        print(f"\n{approach}:")
        cap_dist = df['market_cap_category'].value_counts()
        for cap, count in cap_dist.items():
            print(f"  {cap}: {count} ({count/len(df)*100:.1f}%)")
    
    # Performance comparison summary
    print("\n=== PERFORMANCE IMPROVEMENT SUMMARY ===")
    pnl_diff = xgboost_metrics['total_pnl'] - baseline_metrics['total_pnl']
    print(f"P&L Difference: ${pnl_diff:,.2f} ({pnl_diff/abs(baseline_metrics['total_pnl'])*100:+.1f}%)")
    
    wr_diff = xgboost_metrics['win_rate'] - baseline_metrics['win_rate']
    print(f"Win Rate Difference: {wr_diff:+.1f}%")
    
    pf_diff = xgboost_metrics['profit_factor'] - baseline_metrics['profit_factor']
    print(f"Profit Factor Difference: {pf_diff:+.2f}")
    
    ev_diff = xgboost_metrics['expected_value'] - baseline_metrics['expected_value']
    print(f"Expected Value Difference: {ev_diff:+.2f}%")
    
    # Risk-adjusted performance
    print("\n=== RISK-ADJUSTED METRICS ===")
    
    # Calculate drawdown for both
    def calculate_max_drawdown(df):
        df_sorted = df.sort_values('entry_date')
        cumulative_pnl = df_sorted['pnl'].cumsum()
        running_max = cumulative_pnl.cummax()
        drawdown = (cumulative_pnl - running_max) / (100000 + running_max) * 100
        return drawdown.min()
    
    baseline_dd = calculate_max_drawdown(baseline_df)
    xgboost_dd = calculate_max_drawdown(xgboost_df)
    
    print(f"Baseline Max Drawdown: {baseline_dd:.2f}%")
    print(f"XGBoost Max Drawdown: {xgboost_dd:.2f}%")
    
    # Final verdict
    print("\n=== FINAL ANALYSIS ===")
    improvements = 0
    total_metrics = 5
    
    if xgboost_metrics['total_pnl'] > baseline_metrics['total_pnl']:
        improvements += 1
        print("✓ Total P&L improved")
    else:
        print("✗ Total P&L decreased")
    
    if xgboost_metrics['win_rate'] > baseline_metrics['win_rate']:
        improvements += 1
        print("✓ Win rate improved")
    else:
        print("✗ Win rate decreased")
    
    if xgboost_metrics['profit_factor'] > baseline_metrics['profit_factor']:
        improvements += 1
        print("✓ Profit factor improved")
    else:
        print("✗ Profit factor decreased")
    
    if xgboost_metrics['expected_value'] > baseline_metrics['expected_value']:
        improvements += 1
        print("✓ Expected value improved")
    else:
        print("✗ Expected value decreased")
    
    if abs(xgboost_dd) < abs(baseline_dd):
        improvements += 1
        print("✓ Maximum drawdown reduced")
    else:
        print("✗ Maximum drawdown increased")
    
    print(f"\nOverall: {improvements}/{total_metrics} metrics improved")
    
    # Period-specific insights
    print("\n=== KEY INSIGHTS ===")
    print("1. XGBoost parameters resulted in significantly fewer trades, showing stricter filtering")
    print("2. The approach seems to work better in certain market conditions")
    print("3. Consider dynamic parameter adjustment based on market regime")

if __name__ == "__main__":
    load_and_analyze_comparison()