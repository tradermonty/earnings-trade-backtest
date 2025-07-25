# Earnings Swing Trading Strategy Backtest

*Read this in other languages: [English](README.md), [日本語](README_ja.md)*

A comprehensive backtesting system for earnings-based swing trading strategies, specialized for mid and small-cap stocks using real-time data from EODHD API (Advanced plan) or FinancialModelingPrep (FMP) API (Starter plan).

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- [EODHD API](https://eodhistoricaldata.com/) key (Advanced plan, recommended)
- (Optional) [FinancialModelingPrep API](https://site.financialmodelingprep.com/) key – Premium plan required

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
# For EODHD (Advanced plan)
EODHD_API_KEY=your_eodhd_api_key

# For FMP (Starter plan) – optional
FMP_API_KEY=your_fmp_api_key
```

### Basic Execution

```bash
# Run with default settings (past 1 month)
python main.py

# Run with specific date range
python main.py --start_date 2025-01-01 --end_date 2025-06-30

# Display help
python main.py --help
```

## 📁 Project Structure

```
earnings-trade-backtest/
├── src/                               # Core source code modules
│   ├── data_fetcher.py               # EODHD / FMP unified data retrieval
│   ├── fmp_data_fetcher.py           # FMP-specific data utilities
│   ├── earnings_date_validator.py    # Earnings date cross-check utilities
│   ├── news_fetcher.py               # Earnings news enrichment
│   ├── data_filter.py                # Earnings and technical filters
│   ├── trade_executor.py             # Trade execution simulation
│   ├── risk_manager.py               # Risk management system
│   ├── analysis_engine.py            # Advanced performance analysis
│   ├── report_generator.py           # Enhanced HTML/CSV report generation
│   ├── metrics_calculator.py         # Trading metrics calculation
│   ├── config.py                     # Configuration management
│   └── main.py                       # Modular main execution
├── tests/                            # Comprehensive test suite
├── reports/                          # Generated analysis reports (after execution)
├── scripts/                          # Standalone analysis / debug scripts
├── docs/                             # Documentation and screenshots
├── main.py                          # Main entry point (recommended)
├── README.md                        # This file
├── README_ja.md                     # Japanese documentation
└── requirements.txt                 # Python dependencies
```

## 🎯 Strategy Overview

### 1. Entry Conditions
- **Earnings Surprise**: ≥5% above analyst expectations
- **Gap Up**: Post-earnings price movement ≥0%
- **Market Cap**: Mid/small-cap focus ($300M-$10B)
- **Volume**: ≥2x average daily volume
- **Price Filter**: ≥$10 (excludes penny stocks)

### 2. Exit Conditions
- **Stop Loss**: 6% loss triggers automatic exit
- **Trailing Stop**: Exit when price falls below 21-day MA
- **Maximum Holding**: 90-day forced exit
- **Partial Profit**: 35% position exit at 8% gain (day 1)

### 3. Risk Management
- **Position Size**: 6% of capital per trade
- **Margin Control**: Maximum 1.5x leverage (total positions vs capital)
- **Concurrent Positions**: Maximum 10 positions
- **Sector Diversification**: Max 30% per sector
- **Daily Risk Limit**: Stop new trades if losses exceed 6%

## 🔧 Detailed Parameter Configuration

### Command Line Arguments

#### Basic Settings
```bash
# Date range specification
--start_date 2025-01-01     # Start date (YYYY-MM-DD format)
--end_date 2025-06-30       # End date (YYYY-MM-DD format)

# Capital settings
--initial_capital 100000    # Initial capital (default: $100,000)
--position_size 6           # Position size % (default: 6%)
```

#### Risk Management Settings
```bash
# Stop-loss and profit-taking settings
--stop_loss 6               # Stop loss rate % (default: 6%)
--trail_stop_ma 21          # Trailing stop MA period (default: 21 days)
--max_holding_days 90       # Maximum holding period (default: 90 days)
--risk_limit 6              # Risk management limit % (default: 6%)
--margin_ratio 1.5          # Maximum position to capital ratio (default: 1.5x)

# Trading costs
--slippage 0.3              # Slippage % (default: 0.3%)
```

#### Stock Universe Filters
```bash
# Stock filters
--sp500_only                # Target S&P 500 stocks only
--no_mid_small_only         # Remove mid/small cap restriction (default: mid/small only)

# Pre-earnings price conditions
--pre_earnings_change -10   # Price change threshold % over past 20 days (default: 0%)
```

#### Additional Settings
```bash
# Profit strategy
--no_partial_profit         # Disable day-1 partial profit taking (default: enabled)

# Output language
--language ja               # Report language (ja/en, default: en)
```

### Practical Usage Examples

#### 1. Conservative Setup (Risk-focused)
```bash
python main.py \
  --start_date 2025-01-01 \
  --end_date 2025-06-30 \
  --stop_loss 4 \
  --position_size 4 \
  --max_holding_days 60 \
  --margin_ratio 1.2 \
  --sp500_only
```

#### 2. Aggressive Setup (Return-focused)
```bash
python main.py \
  --start_date 2025-01-01 \
  --end_date 2025-06-30 \
  --stop_loss 8 \
  --position_size 8 \
  --max_holding_days 120 \
  --margin_ratio 2.0 \
  --no_mid_small_only
```

#### 3. Mid/Small-Cap Specialized Long-Term Strategy
```bash
python main.py \
  --start_date 2025-01-01 \
  --end_date 2025-06-30 \
  --stop_loss 6 \
  --trail_stop_ma 50 \
  --max_holding_days 180 \
  --margin_ratio 1.5 \
  --pre_earnings_change -20
```

### Complete Parameter Reference

#### Basic Configuration Parameters

| Parameter | Default | Description | Recommended Range | Notes |
|-----------|---------|-------------|-------------------|-------|
| `start_date` | 1 month ago | Backtest start date | Past dates | YYYY-MM-DD format |
| `end_date` | Today | Backtest end date | Past dates | Future dates auto-adjusted |
| `initial_capital` | 100000 | Initial capital (USD) | 10000-1000000 | Too small reduces diversification |
| `language` | 'en' | Report language | 'en'/'ja' | Use 'ja' for Japanese |

#### Entry Condition Parameters

| Parameter | Default | Description | Recommended Range | Notes |
|-----------|---------|-------------|-------------------|-------|
| `pre_earnings_change` | 0% | 20-day price change threshold | -20-0% | Negative values target post-decline rebounds |
| **Internal Fixed** | 5% | Earnings surprise threshold | - | Fixed in code, requires development to change |
| **Internal Fixed** | 0% | Gap-up threshold | - | Captures post-earnings momentum |
| **Internal Fixed** | $10 | Minimum stock price | - | Excludes penny stocks |
| **Internal Fixed** | 200k shares | Minimum 20-day avg volume | - | Ensures liquidity |

#### Position Management Parameters

| Parameter | Default | Description | Recommended Range | Notes |
|-----------|---------|-------------|-------------------|-------|
| `position_size` | 6% | Capital allocation per trade | 4-8% | Higher increases risk, lower reduces returns |
| `margin_ratio` | 1.5 | Maximum position to capital ratio | 1.2-2.0 | Leverage control, prevents overexposure |
| `slippage` | 0.3% | Trading cost (slippage) | 0.1-0.5% | Reflects realistic trading environment |
| **Internal Fixed** | 10 stocks | Maximum concurrent positions | - | Prevents over-diversification |

#### Exit Condition Parameters

| Parameter | Default | Description | Recommended Range | Notes |
|-----------|---------|-------------|-------------------|-------|
| `stop_loss` | 6% | Loss limitation rate | 4-8% | Too low causes noise-triggered exits |
| `trail_stop_ma` | 21 days | Trailing stop MA period | 21-50 days | Shorter = earlier exits, longer = reduced gains |
| `max_holding_days` | 90 days | Maximum holding period | 60-180 days | Consider market cycles |
| `partial_profit` | True | Enable day-1 partial profit | True/False | 35% position exit at 8% profit |

#### Risk Management Parameters

| Parameter | Default | Description | Recommended Range | Notes |
|-----------|---------|-------------|-------------------|-------|
| `risk_limit` | 6% | Cumulative loss limit (stops new trades) | 5-10% | Circuit breaker for consecutive losses |

#### Stock Filter Parameters

| Parameter | Default | Description | Recommended Range | Notes |
|-----------|---------|-------------|-------------------|-------|
| `sp500_only` | False | Target S&P 500 stocks only | - | Large-cap focus, stability-oriented |
| `mid_small_only` | True | Target mid/small-cap only | - | S&P 400/600, growth-oriented |
| `no_mid_small_only` | False | Remove mid/small-cap restriction | - | Full market target |

### Exit Condition Details

#### 1. Partial Profit System (partial_profit=True)
```
Day 1 after entry:
├─ ≥8% profit → Sell 35% of position
└─ <8% profit → Hold full position
```

#### 2. Trailing Stop
```
Stock price falls below 21-day MA
└─ Sell full position at next day's open
```

#### 3. Stop Loss
```
6% decline from entry price
└─ Immediately sell full position
```

#### 4. Maximum Holding Period
```
90 days elapsed
└─ Force sell full position
```

### Parameter Tuning Tips

#### Conservative Settings (Risk Priority)
- `stop_loss`: 4%
- `position_size`: 4%
- `trail_stop_ma`: 15 days
- `max_holding_days`: 60 days

#### Aggressive Settings (Return Priority)
- `stop_loss`: 8%
- `position_size`: 8%
- `trail_stop_ma`: 50 days
- `max_holding_days`: 180 days

#### Mid/Small-Cap Specialized Settings
- `mid_small_only`: True
- `pre_earnings_change`: -15%
- `trail_stop_ma`: 30 days

## 📊 Results Analysis

### Generated Files

After backtest execution, the following files are automatically generated in the `reports/` directory:

```
reports/
├── earnings_backtest_report_2025-01-01_2025-06-30.html     # Main report
└── earnings_backtest_2025-01-01_2025-06-30.csv             # Trade data
```

### 1. Interactive HTML Report

The main report (`.html`) includes beautiful dark-themed charts and comprehensive analysis:

![Performance Summary](docs/backtest-report-1.png)
*Performance summary dashboard with key metrics*

![Monthly Analysis](docs/backtest-report-2.png)
*Monthly performance heatmap and sector analysis*

![Detailed Charts](docs/backtest-report-3.png)
*Detailed technical analysis and trade breakdown*

#### 📈 Included Charts
- **Equity Curve**: Time-series asset growth
- **Monthly Performance**: Monthly profit/loss breakdown
- **Sector Analysis**: Industry-wise profitability
- **Exit Reason Analysis**: Breakdown of exit triggers
- **Win Rate & P&L Analysis**: Trading performance statistics

#### 📊 Key Metrics
- **Total Return**: Overall period return rate
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Profit ÷ Loss ratio
- **Maximum Drawdown**: Largest asset decline
- **Sharpe Ratio**: Risk-adjusted returns

### 2. CSV Data Files

#### Trade Data (`.csv`) columns:
```
ticker          # Stock symbol
entry_date      # Entry date
exit_date       # Exit date
entry_price     # Entry price
exit_price      # Exit price
shares          # Number of shares
pnl             # Profit/loss amount
pnl_rate        # Profit/loss rate
exit_reason     # Exit trigger
sector          # Sector classification
holding_days    # Holding period
```

### 3. Reading the Reports

#### Performance Evaluation Criteria
- **Profit Factor > 1.5**: Good
- **Win Rate > 45%**: Excellent
- **Maximum Drawdown < 20%**: Acceptable range
- **Sharpe Ratio > 1.0**: Excellent

#### Sector Analysis Applications
- Check concentration risk in specific industries
- Analyze industry rotation effects
- Reference for portfolio diversification

### 4. Sample Execution Output

```bash
$ python main.py --start_date 2025-01-01 --end_date 2025-06-30

=== Earnings Trade Backtest (Refactored Version) ===
期間: 2025-01-01 から 2025-06-30
初期資金: $100,000
ポジションサイズ: 6%
ストップロス: 6%
マージン倍率制限: 1.5倍
対象: 中型・小型株 (S&P 400/600)

1. 決算データの取得を開始...
2. 第1段階フィルタリング: 決算サプライズ ≥ 5%
3. 第2段階フィルタリング: 技術的条件
4. バックテストの実行中...
5. バックテスト完了
6. 分析チャートを生成中...
7. レポートを生成中...

HTMLレポートを生成しました: reports/earnings_backtest_report_2025-01-01_2025-06-30.html
CSVレポートを生成しました: reports/earnings_backtest_2025-01-01_2025-06-30.csv
```

### 5. Troubleshooting

#### Common Errors and Solutions

```bash
# API key error
"ValueError: EODHD_API_KEY not set in .env file"
→ Check .env file configuration

# Date error
"Warning: End date is in the future"
→ Specify appropriate past dates

# Insufficient data error
"Not enough data for analysis"
→ Specify longer period or relax filter conditions
```

#### Performance Optimization
```bash
# Fast execution (short-term analysis)
python main.py --start_date 2025-06-01 --end_date 2025-06-30

# Detailed analysis (long-term, time-intensive)
python main.py --start_date 2024-01-01 --end_date 2025-06-30
```

## 📚 Theoretical Foundation

This earnings swing trading strategy is built upon established academic research and practical methodologies:

### Academic Foundation

**"Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?"**  
*Victor L. Bernard and Jacob K. Thomas*

This groundbreaking research discovered the **Post-Earnings Announcement Drift (PEAD) phenomenon**:

📈 **Key Findings**:
- Stocks with positive earnings surprises continue to **rise for days to weeks** after announcement
- This phenomenon indicates **market inefficiency**
- **Limited information processing capacity** of investors causes delayed full reflection of earnings in stock prices

🔬 **Application to This Strategy**:
- **5% surprise threshold**: Selects statistically significant earnings surprises
- **Average 20-day holding period**: Captures the period when PEAD effect is strongest
- **Swing trading methodology**: Avoids short-term noise while capturing medium-term trends

### Practical Methodology

**"How to master a setup: Episodic Pivots"**  
*Qullamaggie Trading*  
https://qullamaggie.com/how-to-master-a-setup-episodic-pivots/

Incorporates proven techniques from professional traders:

⚡ **Core Concepts**:
- **Episodic Pivot**: Price direction changes triggered by specific events like earnings announcements
- **Base Building**: Importance of price consolidation period before earnings (our 20-day pre-earnings change filter)
- **Volume Confirmation**: Verification of direction through volume spikes

🎯 **Implementation Elements**:
- **Gap-up filter**: Captures initial post-earnings momentum
- **Volume analysis**: Confirms institutional participation
- **Trailing stops**: Maximizes profits while limiting losses

### Strategy Integration Advantage

```
Academic Research (Theory) + Practical Methods (Technique) = Comprehensive Strategy
         ↓                      ↓                             ↓
    PEAD Effect          + Episodic Pivots        = This Strategy
(Continuation tendency)    (Specific methods)     (Proven results)
```

This fusion of theory and practice enables **scientifically-grounded trading** that eliminates emotional decision-making.

## ⚠️ Important Disclaimers

### About Backtesting
- **Backtest results are simulations based on historical data**
- **May differ from actual trading environment** (slippage, liquidity, etc.)
- **Does not guarantee future performance**

### About Investment Decisions
- This system is provided for **research and educational purposes**
- **Investment decisions are entirely your responsibility**
- **Consultation with professionals is recommended**

### System Limitations
- May not operate as expected during rapid market changes
- May miss trading opportunities due to API limitations or outages
- Strategy requires regular review and adjustment

## 🤝 Contributing

Bug reports, feature requests, and improvement suggestions are welcome via Issues.

## 📄 License

This project is released under the MIT License.

## 📚 Related Documentation

- [System Technical Documentation](CLAUDE.md)
- [Japanese Documentation](README_ja.md)

---

**Disclaimer**: This software and its analysis results are provided for informational purposes only and do not constitute investment advice. Investment decisions are your own responsibility.