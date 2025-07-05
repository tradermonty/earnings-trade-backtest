# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an earnings-based swing trading backtest system that analyzes trades based on earnings surprises. The entire system is contained in a single file: `earnings_backtest.py`.

## Dependencies

The project requires these Python packages (no requirements.txt exists):
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
python earnings_backtest.py
```

Common command examples:
```bash
# Run backtest for specific date range
python earnings_backtest.py --start_date 2024-01-01 --end_date 2024-12-31

# Target only S&P 500 stocks with custom parameters
python earnings_backtest.py --sp500_only --stop_loss 5 --position_size 10

# Run for mid/small cap stocks only (default behavior)
python earnings_backtest.py --start_date 2024-01-01

# Generate report in Japanese
python earnings_backtest.py --language ja

# Disable mid/small cap filtering to include all stocks
python earnings_backtest.py --no_mid_small_only
```

## Key Architecture Components

### EarningsBacktest Class

The main class that orchestrates the entire backtesting process:

1. **Data Fetching**:
   - `get_earnings_data()`: Fetches earnings data from EODHD API in 5-year chunks
   - `get_historical_data()`: Retrieves price/volume data for individual stocks
   - `get_sp500_symbols()`: Scrapes S&P 500 list from Wikipedia
   - `get_mid_small_symbols()`: Fetches S&P 400/600 symbols via EODHD API

2. **Filtering Pipeline**:
   - Stage 1: Filters for US stocks with earnings surprise >= 5% and positive actual earnings
   - Stage 2: Filters for gap >= 0%, price >= $10, 20-day avg volume >= 200k shares

3. **Trade Execution Logic**:
   - Entry: On earnings surprise with gap up
   - Exit conditions:
     - Stop loss (default 6%)
     - Trailing stop based on MA (default 21-day)
     - Maximum holding period (default 90 days)
     - Partial profit taking on first day (35% of position at 8% gain)

4. **Risk Management**:
   - Position sizing (default 6% of capital)
   - Risk limit check (prevents new trades if losses exceed threshold)
   - Slippage modeling (default 0.3%)

5. **Reporting**:
   - Console output with trade statistics
   - HTML report generation with dark theme
   - Interactive Plotly charts showing equity curve and performance metrics

## Important Trading Parameters

- `stop_loss`: Stop loss percentage (default: 6%)
- `trail_stop_ma`: MA period for trailing stop (default: 21 days)
- `max_holding_days`: Maximum position holding period (default: 90 days)
- `position_size`: Position size as % of capital (default: 6%)
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