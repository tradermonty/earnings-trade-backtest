# Earnings Swing Trading Strategy Backtest

*Read this in other languages: [English](README.md), [日本語](README_ja.md)*

A comprehensive backtesting system for earnings-based swing trading strategies, specialized for mid and small-cap stocks. Originally developed with EODHD API, the system has migrated to **FinancialModelingPrep (FMP) API** for significantly improved earnings date accuracy.

## ✨ Latest Updates (2025.08)

- **🚀 Dynamic Position Sizing**: Advanced position sizing based on market conditions and risk metrics
- **📊 Alpaca Integration**: Real-time pre-market price data via Alpaca API for improved entry timing
- **🔄 Data Source Migration**: Migrated from EODHD to FMP for 99.7% earnings date accuracy
- **🎯 Enhanced Filtering**: Two-stage filtering pipeline with technical and fundamental screens
- **⚡ Modular Architecture**: Reorganized codebase with clear separation of concerns
- **📈 Advanced Analytics**: Market breadth analysis, sector rotation, and XGBoost feature analysis

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- **[FinancialModelingPrep API](https://site.financialmodelingprep.com/) key (Premium plan, required)**
  - ⚠️ **Note**: FMP Premium plan only provides earnings data from August 2020 onwards
- (Optional) [EODHD API](https://eodhistoricaldata.com/) key (for historical data before 2020)
- (Optional) [Alpaca API](https://alpaca.markets/) key (for real-time pre-market data)

### Installation

```bash
# Clone the repository
git clone https://github.com/tradermonty/earnings-trade-backtest.git
cd earnings-trade-backtest

# Create and activate virtual environment
python3.11 -m venv venv
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### Environment Setup

Create a `.env` file and configure your API key(s):

```env
# Primary data source (99.7% accuracy) - Required
FMP_API_KEY=your_fmp_api_key

# Optional: Fallback data source for historical data before 2020
# EODHD_API_KEY=your_eodhd_api_key

# Optional: Real-time pre-market data
# ALPACA_API_KEY=your_alpaca_api_key
# ALPACA_SECRET_KEY=your_alpaca_secret_key
```

### Basic Execution

```bash
# Run with default settings (FMP data, all US stocks, past 30 days)
python main.py

# Run with specific date range
python main.py --start_date 2024-01-01 --end_date 2024-12-31

# Force EODHD usage (requires API key)
python main.py --use_eodhd

# Display help
python main.py --help
```

## 📊 Data Source Comparison

| Feature | **FMP (Primary)** | EODHD (Legacy) |
|---------|----------------------|-------|
| **Earnings Date Accuracy** | **99.7%** ✅ | ~44% ⚠️ |
| **Historical Data Range** | **~5 years** (2020-08+) ⚠️ | **10+ years** ✅ |
| **Data Coverage** | **95.5%** US stocks | ~90% US stocks |
| **API Reliability** | **Excellent** | Good |
| **Rate Limiting** | **Advanced** (600 calls/min) | Standard |
| **Required Plan** | Premium ($14/month) | Advanced ($50/month) |
| **Date Validation** | **Not needed** | Required (complex) |

*We migrated from EODHD to FMP due to the critical importance of accurate earnings dates for this strategy*

## 📁 Project Structure

```
earnings-trade-backtest/
├── src/                               # Core source code modules
│   ├── data_fetcher.py               # Unified data retrieval (FMP/EODHD)
│   ├── fmp_data_fetcher.py           # FMP-specific optimized API client
│   ├── alpaca_data_fetcher.py        # Alpaca real-time data integration
│   ├── earnings_date_validator.py    # EODHD date validation (legacy)
│   ├── news_fetcher.py               # Earnings news enrichment
│   ├── data_filter.py                # Two-stage filtering pipeline
│   ├── trade_executor.py             # Trade execution simulation
│   ├── risk_manager.py               # Risk management system
│   ├── analysis_engine.py            # Advanced performance analysis
│   ├── report_generator.py           # Enhanced HTML/CSV report generation
│   ├── metrics_calculator.py         # Trading metrics calculation
│   ├── config.py                     # Configuration management
│   ├── dynamic_position/             # Dynamic position sizing module
│   └── main.py                       # Modular main execution
├── scripts/                          # Utility and analysis scripts
│   ├── analysis/                     # Performance and strategy analysis
│   ├── comparison/                   # Result comparison tools
│   ├── dynamic/                      # Dynamic position sizing scripts
│   └── ...                          # Data validation utilities
├── tests/                            # Comprehensive test suite (44+ tests)
├── reports/                          # Generated analysis reports
├── docs/                             # Documentation and screenshots
├── main.py                          # Main entry point
├── README.md                        # This file
├── README_ja.md                     # Japanese documentation
└── requirements.txt                 # Python dependencies
```

## 🎯 Strategy Overview

### 1. Entry Conditions (Two-Stage Filtering)

**Stage 1 - Earnings Filter:**
- **Earnings Surprise**: ≥5% above analyst expectations (configurable via `--min_surprise`)
- **Positive Earnings**: Actual EPS > 0
- **Market**: US stocks only (automatically filtered)

**Stage 2 - Technical Filter:**
- **Gap Up**: Opening gap ≥0% (configurable max gap)
- **Price Filter**: ≥$10 (excludes penny stocks)
- **Volume**: 20-day average ≥200k shares
- **Pre-earnings Movement**: Configurable minimum price change in 20 days before earnings

### 2. Exit Conditions
- **Stop Loss**: 6% loss triggers automatic exit
- **Trailing Stop**: Exit when price falls below 21-day MA
- **Maximum Holding**: 90-day forced exit
- **Partial Profit**: 35% position exit at 8% gain (day 1)

### 3. Risk Management
- **Position Size**: 6-10% of capital per trade (configurable)
- **Dynamic Sizing**: Optional market-condition-based position adjustment
- **Margin Control**: Maximum 1.5x leverage (total positions vs capital)
- **Concurrent Positions**: Maximum 10 positions
- **Daily Risk Limit**: Stop new trades if losses exceed threshold
- **Currency**: USD only

## 🔧 Command Line Configuration

### Stock Universe Selection

```bash
# All US stocks (default with FMP)
python main.py

# S&P 500 only (large-cap focus)
python main.py --sp500_only

# Mid/small-cap focus (S&P 400/600)
python main.py --mid_small_only

# Use market cap filtering
python main.py --use_market_cap_filter --min_market_cap 1 --max_market_cap 50
```

### Data Source Options

```bash
# Use FMP (default, 99.7% accuracy)
python main.py

# Force EODHD usage
python main.py --use_eodhd

# Enable date validation (EODHD only)
python main.py --use_eodhd --enable_date_validation
```

### Risk & Position Management

```bash
# Conservative setup
python main.py --stop_loss 4 --position_size 4 --margin_ratio 1.2

# Aggressive setup  
python main.py --stop_loss 8 --position_size 8 --margin_ratio 2.0

# Custom risk limits
python main.py --risk_limit 10 --max_holding_days 120
```

### Complete Parameter Reference

| Parameter | Default | Description | Range |
|-----------|---------|-------------|-------|
| `--start_date` | 30 days ago | Backtest start date | YYYY-MM-DD |
| `--end_date` | Today | Backtest end date | YYYY-MM-DD |
| `--stop_loss` | 6 | Stop loss % | 2-10 |
| `--position_size` | 10 | Position size % | 2-20 |
| `--margin_ratio` | 1.5 | Max leverage | 1.0-3.0 |
| `--sp500_only` | False | Limit universe to S&P 500 constituents | Boolean |
| `--mid_small_only` | False | Limit universe to mid/small-cap stocks | Boolean |
| `--use_market_cap_filter` | False | Enable market cap filtering | Boolean |
| `--min_market_cap` | 1 | Minimum market-cap in billions USD | 0-∞ |
| `--max_market_cap` | 50 | Maximum market-cap in billions USD | 0-∞ |
| `--screener_price_min` | 10 | Minimum share price (USD) | ≥0 |
| `--screener_volume_min` | 200,000 | Minimum 20-day average volume | ≥0 |
| `--max_gap` | 10 | Maximum allowable opening gap % | ≥0 |
| `--min_surprise` | 5 | Minimum EPS surprise % | ≥0 |
| `--pre_earnings_change` | 0 | Min price change % in 20 days before earnings | Any |
| `--use_eodhd` | False | Force EODHD data source | Boolean |
| `--use_fmp` | True | Use FMP data source (default) | Boolean |
| `--enable_date_validation` | False | Enable earnings date validation | Boolean |
| `--language` | 'en' | Report language | 'en' / 'ja' |

## 📊 Performance Analysis

### Generated Reports

```
reports/
├── earnings_backtest_report_YYYY-MM-DD_YYYY-MM-DD.html  # Interactive dashboard
└── earnings_backtest_YYYY-MM-DD_YYYY-MM-DD.csv          # Detailed trade data
```

### Key Metrics Dashboard

![Performance Summary](docs/backtest-report-1.png)
*Detailed performance metrics and equity curve analysis*

### Analysis Features

- **📈 Interactive Charts**: Plotly-powered visualizations
- **📊 Sector Analysis**: Industry breakdown and rotation
- **🎯 Win Rate Analysis**: Success rate by holding period
- **📉 Drawdown Analysis**: Risk assessment metrics
- **🔄 Exit Reason Breakdown**: Performance by exit trigger

## 🧪 Testing & Quality Assurance

### Comprehensive Test Suite

```bash
# Run all tests
python -m pytest tests/ -v

# FMP-specific tests
python -m pytest tests/test_fmp_data_fetcher.py -v

# Integration tests (requires API key)
python -m pytest tests/test_fmp_integration.py -v

# Generate test report
python tests/test_fmp_comprehensive.py
```

### Test Coverage

- **44+ Test Cases**: Unit, integration, and end-to-end tests
- **Rate Limiting**: API call optimization and error handling
- **Data Processing**: Accuracy validation and edge cases  
- **Error Scenarios**: Comprehensive failure mode testing
- **Real API Testing**: Actual FMP/EODHD integration validation

## 🚀 Advanced Features

### Dynamic Position Sizing

```bash
# Run with dynamic position sizing based on market conditions
python scripts/dynamic/dynamic_main.py

# Run realistic dynamic backtest with actual data
python scripts/dynamic/run_dynamic_backtest_real.py
```

### Data Quality Validation

```bash
# Compare FMP vs reference data accuracy
python scripts/compare_fmp_finviz_accuracy.py

# Analyze earnings date validation statistics  
python scripts/analyze_date_validation_stats.py

# Debug FMP API responses
python scripts/debug_fmp_api.py
```

### Performance Analysis

```bash
# XGBoost feature importance analysis
python scripts/analysis/xgboost_feature_analysis.py

# Stop loss optimization analysis
python scripts/analysis/comprehensive_stop_loss_analysis.py

# Market breadth analysis
python scripts/analysis/market_breadth_analysis.py

# Compare backtest results
python scripts/comparison/compare_results.py
```

### Custom Analysis Scripts

```bash
# Analyze specific stock performance
python scripts/analyze_manh_entry.py

# Generate comprehensive validation report
python scripts/comprehensive_validation_report.py

# Aggregate multiple screening files
python scripts/aggregate_screen_files.py
```

## 📚 Theoretical Foundation

### Academic Research

**"Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?"**  
*Victor L. Bernard and Jacob K. Thomas*

- **PEAD Effect**: Stocks with earnings surprises continue trending 5-20 days post-announcement
- **Market Inefficiency**: Limited processing capacity causes delayed price adjustments
- **Statistical Edge**: 5% surprise threshold captures significant events

### Practical Implementation

**Professional Trading Methodologies**:
- **Episodic Pivots**: Event-driven price direction changes
- **Volume Confirmation**: Institutional participation validation
- **Risk-First Approach**: Capital preservation with profit maximization

## ⚠️ Important Notes

### Data Accuracy Validation

Based on comprehensive analysis of 648 earnings events (July 2025):

- **FMP Accuracy**: 99.7% (610/619 exact matches)
- **FMP Coverage**: 95.5% of earnings events
- **EODHD Legacy**: ~44% accuracy (requires validation)

### System Requirements

- **Required**: FMP Premium plan ($14/month) - Only API key needed
- **Optional**: EODHD Advanced plan ($50/month) - For fallback functionality
- **Minimum**: Python 3.11+, 4GB RAM
- **Network**: Stable internet for API calls
- **Storage**: ~100MB for historical data cache

### Limitations

- **FMP Historical Data**: Premium plan limited to ~5 years of earnings data (August 2020 onwards)
  - For backtests before 2020, use EODHD despite lower accuracy
- **Backtest simulation**: Results may differ from live trading
- **Market conditions**: Strategy performance varies by market regime
- **API dependencies**: Requires stable third-party data sources
- **US markets only**: Does not support international exchanges

## 🤝 Contributing

We welcome contributions! Please see our testing guidelines:

```bash
# Before submitting PR, ensure all tests pass
python -m pytest tests/ -v

# Add tests for new features
# Follow existing code patterns
# Update documentation accordingly
```

## 📄 License

This project is released under the MIT License.

## 📚 Documentation

- **[Technical Documentation](CLAUDE.md)**: Development and configuration guide
- **[Japanese Documentation](README_ja.md)**: 日本語版ドキュメント
- **[Test Documentation](tests/README.md)**: Testing framework details

---

**Disclaimer**: This software is provided for educational and research purposes only. Past performance does not guarantee future results. Investment decisions are your own responsibility. Please consult with financial professionals before making investment decisions.