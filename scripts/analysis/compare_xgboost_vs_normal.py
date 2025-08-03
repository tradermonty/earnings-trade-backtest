#!/usr/bin/env python3
"""
Compare XGBoost optimized results vs normal/all approach
earnings_backtest_2024_09_01_2025_07_30_finviz_xgboost_improvement3.csv vs
earnings_backtest_2024_09_01_2025_06_30_all_normal_additional-filter_.csv
"""

import pandas as pd
import numpy as np
from datetime import datetime

def calculate_metrics(df, label):
    """Calculate key performance metrics for a dataframe"""
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
    print(f"Total Trades: {len(df)}")
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
        'trades': len(df),
        'total_pnl': total_pnl,
        'avg_return': avg_pnl_rate,
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'expected_value': expected_value,
        'avg_holding': avg_holding
    }

def analyze_comparison():
    # Load both CSV files
    xgboost_df = pd.read_csv('../../reports/earnings_backtest_2024_09_01_2025_07_30_finviz_xgboost_improvement3.csv')
    normal_df = pd.read_csv('../../reports/earnings_backtest_2024_09_01_2025_06_30_all_normal_additional-filter_.csv')
    
    print("=== XGBOOST OPTIMIZED vs NORMAL APPROACH COMPARISON ===")
    print("XGBoost: 2024-09-01 to 2025-07-30 (finviz aggregated with optimization)")
    print("Normal: 2024-09-01 to 2025-06-30 (main.py with additional filters)")
    print()
    
    # Note the different date ranges
    print("⚠️  NOTE: Different date ranges!")
    print("XGBoost: 11 months (Sept 2024 - July 2025)")
    print("Normal: 10 months (Sept 2024 - June 2025)")
    print()
    
    # Convert dates for proper analysis
    xgboost_df['entry_date'] = pd.to_datetime(xgboost_df['entry_date'])
    normal_df['entry_date'] = pd.to_datetime(normal_df['entry_date'])
    
    # Filter XGBoost to same period as normal for fair comparison
    xgboost_filtered = xgboost_df[xgboost_df['entry_date'] <= '2025-06-30'].copy()
    
    print("=== PERIOD-MATCHED COMPARISON (Sept 2024 - June 2025) ===")
    print()
    
    # Calculate metrics for both
    xgboost_metrics = calculate_metrics(xgboost_filtered, "XGBOOST OPTIMIZED (10 months)")
    normal_metrics = calculate_metrics(normal_df, "NORMAL APPROACH (10 months)")
    
    # Additional analysis - exit reasons
    print("=== EXIT REASON DISTRIBUTION ===")
    print("XGBoost Optimized:")
    if 'exit_reason' in xgboost_filtered.columns:
        for reason, count in xgboost_filtered['exit_reason'].value_counts().items():
            print(f"  {reason}: {count} ({count/len(xgboost_filtered)*100:.1f}%)")
    
    print("\nNormal Approach:")
    if 'exit_reason' in normal_df.columns:
        for reason, count in normal_df['exit_reason'].value_counts().items():
            print(f"  {reason}: {count} ({count/len(normal_df)*100:.1f}%)")
    
    # Market cap analysis
    print("\n=== MARKET CAP DISTRIBUTION ===")
    for approach, df in [("XGBoost", xgboost_filtered), ("Normal", normal_df)]:
        print(f"\n{approach}:")
        if 'market_cap_category' in df.columns:
            cap_dist = df['market_cap_category'].value_counts()
            for cap, count in cap_dist.items():
                print(f"  {cap}: {count} ({count/len(df)*100:.1f}%)")
    
    # Surprise rate analysis
    print("\n=== EARNINGS SURPRISE ANALYSIS ===")
    if 'surprise_rate' in xgboost_filtered.columns:
        print(f"XGBoost - Average surprise: {xgboost_filtered['surprise_rate'].mean():.2f}%")
        print(f"XGBoost - Median surprise: {xgboost_filtered['surprise_rate'].median():.2f}%")
    if 'surprise_rate' in normal_df.columns:
        print(f"Normal - Average surprise: {normal_df['surprise_rate'].mean():.2f}%")
        print(f"Normal - Median surprise: {normal_df['surprise_rate'].median():.2f}%")
    
    # Performance improvement summary
    print("\n=== PERFORMANCE COMPARISON SUMMARY ===")
    
    pnl_diff = xgboost_metrics['total_pnl'] - normal_metrics['total_pnl']
    pnl_improvement = pnl_diff / abs(normal_metrics['total_pnl']) * 100 if normal_metrics['total_pnl'] != 0 else 0
    print(f"P&L Difference: ${pnl_diff:,.2f} ({pnl_improvement:+.1f}%)")
    
    trade_diff = xgboost_metrics['trades'] - normal_metrics['trades']
    print(f"Trade Count Difference: {trade_diff:+d} trades")
    
    wr_diff = xgboost_metrics['win_rate'] - normal_metrics['win_rate']
    print(f"Win Rate Difference: {wr_diff:+.1f}%")
    
    pf_diff = xgboost_metrics['profit_factor'] - normal_metrics['profit_factor']
    print(f"Profit Factor Difference: {pf_diff:+.2f}")
    
    ev_diff = xgboost_metrics['expected_value'] - normal_metrics['expected_value']
    print(f"Expected Value Difference: {ev_diff:+.2f}%")
    
    # Risk analysis
    print("\n=== RISK ANALYSIS ===")
    def calculate_max_drawdown(df):
        if len(df) == 0:
            return 0
        df_sorted = df.sort_values('entry_date')
        cumulative_pnl = df_sorted['pnl'].cumsum()
        running_max = cumulative_pnl.cummax()
        drawdown = (cumulative_pnl - running_max) / (100000 + running_max) * 100
        return drawdown.min()
    
    xgboost_dd = calculate_max_drawdown(xgboost_filtered)
    normal_dd = calculate_max_drawdown(normal_df)
    
    print(f"XGBoost Max Drawdown: {xgboost_dd:.2f}%")
    print(f"Normal Max Drawdown: {normal_dd:.2f}%")
    
    # Calculate annualized returns
    print("\n=== ANNUALIZED PERFORMANCE ===")
    days_period = 304  # Sept 1 to June 30 (approximate)
    
    xgboost_annual = (xgboost_metrics['total_pnl'] / 100000) * (365 / days_period) * 100
    normal_annual = (normal_metrics['total_pnl'] / 100000) * (365 / days_period) * 100
    
    print(f"XGBoost Annualized Return: {xgboost_annual:.2f}%")
    print(f"Normal Annualized Return: {normal_annual:.2f}%")
    
    # Summary verdict
    print("\n=== FINAL VERDICT ===")
    improvements = 0
    total_metrics = 4
    
    if xgboost_metrics['total_pnl'] > normal_metrics['total_pnl']:
        improvements += 1
        print("✓ XGBoost achieved higher total P&L")
    else:
        print("✗ XGBoost had lower total P&L")
    
    if xgboost_metrics['win_rate'] > normal_metrics['win_rate']:
        improvements += 1
        print("✓ XGBoost achieved higher win rate")
    else:
        print("✗ XGBoost had lower win rate")
    
    if xgboost_metrics['profit_factor'] > normal_metrics['profit_factor']:
        improvements += 1
        print("✓ XGBoost achieved higher profit factor")
    else:
        print("✗ XGBoost had lower profit factor")
    
    if abs(xgboost_dd) < abs(normal_dd):
        improvements += 1
        print("✓ XGBoost had lower maximum drawdown")
    else:
        print("✗ XGBoost had higher maximum drawdown")
    
    print(f"\nOverall: {improvements}/{total_metrics} metrics favored XGBoost approach")
    
    # Key insights
    print("\n=== KEY INSIGHTS ===")
    print("1. XGBoost optimization appears to provide:")
    if pnl_improvement > 0:
        print(f"   - Superior profitability (+{pnl_improvement:.1f}%)")
    if wr_diff > 0:
        print(f"   - Better trade selection (win rate +{wr_diff:.1f}%)")
    if trade_diff != 0:
        print(f"   - {'More selective' if trade_diff < 0 else 'More active'} trading ({trade_diff:+d} trades)")
    
    print("2. The XGBoost approach shows the benefit of:")
    print("   - P/S ratio filtering (max 10)")
    print("   - P/E ratio filtering (max 75)")
    print("   - Profit margin filtering (min 3%)")
    print("   - Optimized position sizing (15%)")
    print("   - Relaxed stop loss (6-8%)")

if __name__ == "__main__":
    analyze_comparison()