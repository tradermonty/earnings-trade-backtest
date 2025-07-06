# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an earnings-based swing trading backtest system that analyzes trades based on earnings surprises. The system has been refactored into a modular architecture under the `src/` directory, with `main.py` as the entry point.

## Dependencies

The project requires these Python packages (see requirements.txt):
```
requests
pandas
numpy
python-dotenv
tqdm
plotly
beautifulsoup4
```

## Environment Setup

1. Create a `.env` file with your EODHD API key:
   ```
   EODHD_API_KEY=your_api_key_here
   ```

2. The system uses EODHD API for fetching earnings and historical price data.

## Running the Backtest

Basic usage:
```bash
python main.py
```

Common command examples:
```bash
# Run backtest for specific date range
python main.py --start_date 2024-01-01 --end_date 2024-12-31

# Target only S&P 500 stocks with custom parameters
python main.py --sp500_only --stop_loss 5 --position_size 10

# Run for mid/small cap stocks only (default behavior)
python main.py --start_date 2024-01-01

# Generate report in Japanese
python main.py --language ja

# Set margin limit (default 1.5x leverage)
python main.py --margin_ratio 1.2

# Disable mid/small cap filtering to include all stocks
python main.py --no_mid_small_only
```

## Key Architecture Components

### Modular Architecture (src/)

The system is organized into specialized modules:

1. **Data Layer**:
   - `data_fetcher.py`: Handles all API interactions with EODHD
   - `data_filter.py`: Implements two-stage filtering pipeline for earnings data

2. **Trading Logic**:
   - `trade_executor.py`: Manages trade execution, position tracking, and exit logic
   - `risk_manager.py`: Handles risk checks and position sizing calculations

3. **Analysis & Reporting**:
   - `analysis_engine.py`: Generates advanced performance analytics and charts
   - `report_generator.py`: Creates HTML/CSV reports with interactive visualizations
   - `metrics_calculator.py`: Computes trading metrics (Sharpe ratio, drawdown, etc.)

4. **Configuration**:
   - `config.py`: Central configuration management
   - `main.py`: Entry point that orchestrates all components

### Key Features

1. **Filtering Pipeline**:
   - Stage 1: Filters for US stocks with earnings surprise >= 5% and positive actual earnings
   - Stage 2: Filters for gap >= 0%, price >= $10, 20-day avg volume >= 200k shares

2. **Trade Execution**:
   - Entry: On earnings surprise with gap up
   - Exit conditions:
     - Stop loss (default 6%)
     - Trailing stop based on MA (default 21-day)
     - Maximum holding period (default 90 days)
     - Partial profit taking on first day (35% of position at 8% gain)

3. **Risk Management**:
   - Position sizing (default 6% of capital)
   - **Margin control** (default 1.5x leverage limit)
   - Risk limit check (prevents new trades if losses exceed threshold)
   - Daily position tracking and monitoring

## Important Trading Parameters

- `stop_loss`: Stop loss percentage (default: 6%)
- `trail_stop_ma`: MA period for trailing stop (default: 21 days)
- `max_holding_days`: Maximum position holding period (default: 90 days)
- `position_size`: Position size as % of capital (default: 6%)
- `margin_ratio`: Maximum position to capital ratio (default: 1.5x)
- `risk_limit`: Max loss % before stopping new trades (default: 6%)
- `pre_earnings_change`: Min price change in 20 days before earnings (default: 0%)

## Output Files

The system generates:
- Console output with detailed trade logs
- HTML report file with interactive charts (opens automatically in browser)

## Notes

- The system defaults to targeting mid/small cap stocks (S&P 400/600)
- Language support for both English and Japanese reporting
- All dates should be in YYYY-MM-DD format
- If no date range is specified, it defaults to the last 30 days