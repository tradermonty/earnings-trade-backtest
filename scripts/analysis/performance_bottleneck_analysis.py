#!/usr/bin/env python3
"""
Analyze performance bottlenecks in the XGBoost-optimized strategy
Focus on why 4.84% return over 11 months is suboptimal
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def analyze_performance_bottlenecks():
    # Load XGBoost optimized results
    df = pd.read_csv('../../reports/earnings_backtest_2024_09_01_2025_07_30_finviz_xgboost.csv')
    
    print("=== PERFORMANCE BOTTLENECK ANALYSIS ===")
    print("Why 4.84% return over 11 months is suboptimal\n")
    
    # Convert dates
    df['entry_date'] = pd.to_datetime(df['entry_date'])
    df['exit_date'] = pd.to_datetime(df['exit_date'])
    
    # Basic stats
    total_trades = len(df)
    initial_capital = 100000
    final_capital = 104837.15
    total_return = 4.84
    
    print(f"Total trades: {total_trades}")
    print(f"Period: {df['entry_date'].min().date()} to {df['exit_date'].max().date()}")
    print(f"Days covered: {(df['exit_date'].max() - df['entry_date'].min()).days}")
    print(f"Final return: {total_return:.2f}%\n")
    
    # Problem 1: Capital Utilization Analysis
    print("=== PROBLEM 1: CAPITAL UTILIZATION ===")
    
    # Estimate average capital deployment
    position_size_pct = 10.0  # Default 10%
    avg_position_value = df['shares'] * df['entry_price']
    avg_capital_used = avg_position_value.mean()
    
    print(f"Average position size: ${avg_capital_used:,.2f}")
    print(f"Target position size (10% of capital): ${initial_capital * 0.1:,.2f}")
    print(f"Capital utilization efficiency: {avg_capital_used/(initial_capital*0.1)*100:.1f}%")
    
    # Problem 2: Trade Frequency Analysis
    print(f"\n=== PROBLEM 2: TRADE FREQUENCY ===")
    
    days_total = (df['exit_date'].max() - df['entry_date'].min()).days
    trades_per_month = total_trades / (days_total / 30.4)
    
    print(f"Trades per month: {trades_per_month:.1f}")
    print(f"Days between trades (average): {days_total / total_trades:.1f}")
    
    # Calculate idle periods
    df_sorted = df.sort_values('entry_date')
    df_sorted['prev_exit'] = df_sorted['exit_date'].shift(1)
    df_sorted['idle_days'] = (df_sorted['entry_date'] - df_sorted['prev_exit']).dt.days
    
    total_idle_days = df_sorted['idle_days'].sum()
    print(f"Total idle days (capital not deployed): {total_idle_days:.0f}")
    print(f"Idle time percentage: {total_idle_days/days_total*100:.1f}%")
    
    # Problem 3: Win/Loss Efficiency
    print(f"\n=== PROBLEM 3: WIN/LOSS EFFICIENCY ===")
    
    winners = df[df['pnl'] > 0]
    losers = df[df['pnl'] <= 0]
    
    win_rate = len(winners) / total_trades * 100
    avg_win_pct = winners['pnl_rate'].mean() * 100
    avg_loss_pct = losers['pnl_rate'].mean() * 100
    
    print(f"Win rate: {win_rate:.1f}%")
    print(f"Average win: {avg_win_pct:.2f}%")
    print(f"Average loss: {avg_loss_pct:.2f}%")
    print(f"Win/Loss ratio: {abs(avg_win_pct/avg_loss_pct):.2f}")
    
    # Expected value analysis
    expected_value_per_trade = (win_rate/100 * avg_win_pct/100) + ((100-win_rate)/100 * avg_loss_pct/100)
    print(f"Expected value per trade: {expected_value_per_trade*100:.2f}%")
    
    # Problem 4: Holding Period Analysis
    print(f"\n=== PROBLEM 4: HOLDING PERIOD EFFICIENCY ===")
    
    avg_holding_period = df['holding_period'].mean()
    print(f"Average holding period: {avg_holding_period:.1f} days")
    
    # Annualized return per position
    avg_daily_return = expected_value_per_trade / avg_holding_period * 100
    annualized_per_position = avg_daily_return * 365
    
    print(f"Daily return per position: {avg_daily_return:.3f}%")
    print(f"Annualized return per position: {annualized_per_position:.2f}%")
    
    # Problem 5: Stop Loss Impact
    print(f"\n=== PROBLEM 5: STOP LOSS IMPACT ===")
    
    stop_loss_trades = df[df['exit_reason'].str.contains('stop_loss')]
    stop_loss_rate = len(stop_loss_trades) / total_trades * 100
    stop_loss_impact = stop_loss_trades['pnl'].sum()
    
    print(f"Stop loss rate: {stop_loss_rate:.1f}%")
    print(f"Stop loss total impact: ${stop_loss_impact:,.2f}")
    print(f"Average stop loss: ${stop_loss_impact/len(stop_loss_trades):,.2f}")
    
    # Problem 6: Position Sizing Analysis
    print(f"\n=== PROBLEM 6: POSITION SIZING OPTIMIZATION ===")
    
    # Calculate what return would be with larger position sizes
    scenarios = [15, 20, 25]  # Position size percentages
    
    for size_pct in scenarios:
        multiplier = size_pct / 10.0  # Current is 10%
        estimated_return = total_return * multiplier
        print(f"With {size_pct}% position size: {estimated_return:.2f}% return")
    
    # Problem 7: Opportunity Cost
    print(f"\n=== PROBLEM 7: OPPORTUNITY COST ANALYSIS ===")
    
    # S&P 500 comparison (approximate)
    sp500_annual_return = 10.0  # Historical average
    benchmark_return = sp500_annual_return * (days_total / 365)
    
    print(f"S&P 500 benchmark (estimated): {benchmark_return:.2f}%")
    print(f"Strategy underperformance: {total_return - benchmark_return:.2f}%")
    
    # Problem 8: Risk-Adjusted Return
    print(f"\n=== PROBLEM 8: RISK-ADJUSTED ANALYSIS ===")
    
    # Calculate Sharpe-like ratio
    daily_returns = []
    for _, trade in df.iterrows():
        daily_return = trade['pnl_rate'] / trade['holding_period']
        daily_returns.extend([daily_return] * int(trade['holding_period']))
    
    if daily_returns:
        volatility = np.std(daily_returns) * np.sqrt(365) * 100
        sharpe_like = (total_return * 365 / days_total) / volatility if volatility > 0 else 0
        print(f"Annualized volatility: {volatility:.2f}%")
        print(f"Risk-adjusted ratio: {sharpe_like:.2f}")
    
    # SOLUTIONS SUMMARY
    print(f"\n=== IDENTIFIED BOTTLENECKS & SOLUTIONS ===")
    
    bottlenecks = []
    
    if trades_per_month < 10:
        bottlenecks.append("LOW TRADE FREQUENCY: Need more trading opportunities")
    
    if total_idle_days / days_total > 0.7:
        bottlenecks.append("HIGH IDLE TIME: Capital underutilized")
    
    if abs(avg_win_pct/avg_loss_pct) < 2:
        bottlenecks.append("POOR WIN/LOSS RATIO: Wins not big enough vs losses")
    
    if avg_holding_period > 30:
        bottlenecks.append("LONG HOLDING PERIODS: Capital tied up too long")
    
    if stop_loss_rate > 30:
        bottlenecks.append("HIGH STOP LOSS RATE: Exit strategy too conservative")
    
    if total_return < benchmark_return:
        bottlenecks.append("BENCHMARK UNDERPERFORMANCE: Strategy needs improvement")
    
    for i, bottleneck in enumerate(bottlenecks, 1):
        print(f"{i}. {bottleneck}")
    
    # Specific recommendations
    print(f"\n=== SPECIFIC RECOMMENDATIONS ===")
    print("1. INCREASE POSITION SIZE: Consider 15-20% per trade (with proper risk management)")
    print("2. REDUCE HOLDING PERIODS: Implement faster exit strategies")
    print("3. IMPROVE STOP LOSS: Use tighter stops or different exit methods")
    print("4. INCREASE TRADE FREQUENCY: Relax some filtering criteria")
    print("5. PORTFOLIO APPROACH: Allow multiple concurrent positions")
    print("6. DYNAMIC SIZING: Larger positions for higher-confidence trades")

if __name__ == "__main__":
    analyze_performance_bottlenecks()