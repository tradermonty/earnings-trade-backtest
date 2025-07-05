---
layout: default
title: レポート形式説明
lang: ja
---

# 📊 レポート形式説明

バックテストシステムが生成する各種レポートの詳細説明と読み方を提供します。

## 📋 レポートの種類

### 1. 📈 パフォーマンス サマリー
```
=== PERFORMANCE SUMMARY ===
Total Return: 23.45%
Annualized Return: 18.67%
Sharpe Ratio: 1.42
Maximum Drawdown: -12.34%
Win Rate: 62.50%
```

**主要指標の説明：**
- **Total Return**: 期間全体の総リターン
- **Annualized Return**: 年換算リターン
- **Sharpe Ratio**: リスク調整後リターン（1.0以上が良好）
- **Maximum Drawdown**: 最大下落率
- **Win Rate**: 勝率（一般的に60%以上が良好）

### 2. 📊 取引統計
```
=== TRADING STATISTICS ===
Total Trades: 124
Winning Trades: 78 (62.90%)
Losing Trades: 46 (37.10%)
Average Trade Duration: 6.2 days
Average Win: +12.34%
Average Loss: -6.78%
Profit Factor: 2.31
```

**取引統計の読み方：**
- **Profit Factor**: 総利益÷総損失（1.5以上が良好）
- **Average Trade Duration**: 平均保有期間
- **Risk-Reward Ratio**: 平均勝ち÷平均負け

### 3. 📅 月次リターン
```
=== MONTHLY RETURNS ===
     Jan    Feb    Mar    Apr    May    Jun
2024  2.3%   4.1%  -1.2%   3.8%   1.9%   2.7%
2023  1.5%   3.2%   0.8%   2.4%   1.1%   3.6%
```

**月次分析のポイント：**
- 季節性パターンの確認
- 一貫性の評価
- 月次ボラティリティの測定

## 🎯 詳細レポートの構成

### A. エグゼクティブサマリー
```
EXECUTIVE SUMMARY
=================
Strategy: Earnings Swing Trading
Period: 2023-01-01 to 2024-12-31
Initial Capital: $100,000
Final Portfolio Value: $123,450

Key Highlights:
• Outperformed S&P 500 by 8.3%
• Maintained consistent profitability
• Low correlation with market volatility
```

### B. リスク分析
```
RISK ANALYSIS
=============
Value at Risk (95%): -$2,340
Expected Shortfall: -$3,120
Beta vs SPY: 0.73
Correlation with SPY: 0.45
Volatility: 14.2%
```

**リスク指標の解釈：**
- **VaR**: 95%信頼度での最大損失予想
- **Beta**: 市場感応度（1.0未満は市場より低リスク）
- **Correlation**: 市場との相関度（0.5未満は分散効果あり）

### C. セクター分析
```
SECTOR ANALYSIS
===============
Technology: 28.5% (Win Rate: 68%)
Healthcare: 22.1% (Win Rate: 71%)
Consumer Discretionary: 18.3% (Win Rate: 59%)
Financial: 15.7% (Win Rate: 64%)
Others: 15.4% (Win Rate: 57%)
```

## 📈 チャート・グラフの説明

### 1. 資産推移チャート
```
Portfolio Value Over Time
125,000 |                    /\
        |                   /  \
120,000 |                  /    \
        |                 /      \
115,000 |               /        \
        |              /          \
110,000 |             /            \
        |            /              \
105,000 |           /                \
        |          /                  \
100,000 |_________/____________________\
        Jan  Mar  May  Jul  Sep  Nov  Dec
```

### 2. ドローダウンチャート
```
Drawdown Analysis
   0% |████████████████████████████████
      |
  -5% |        ████████████████████████
      |
 -10% |              ████████████████████
      |
 -15% |                    ████████████
      |
 -20% |________________________
        Jan  Mar  May  Jul  Sep  Nov  Dec
```

### 3. 月次リターンヒートマップ
```
Monthly Returns Heatmap
     J  F  M  A  M  J  J  A  S  O  N  D
2024 █  █  ▓  █  ▓  █  ▓  █  ▓  █  ▓  █
2023 ▓  █  ▓  █  ▓  █  ▓  █  ▓  █  ▓  █

█ = Positive Return  ▓ = Negative Return
```

## 🔍 詳細取引ログ

### 取引履歴の形式
```
TRADE DETAILS
=============
Trade #1: AAPL
Entry Date: 2024-01-15
Exit Date: 2024-01-22
Entry Price: $185.50
Exit Price: $201.23
Quantity: 100 shares
P&L: +$1,573 (+8.47%)
Reason: Earnings beat expectations
```

### 取引分析
```
TRADE ANALYSIS
==============
Best Trade: NVDA +$3,245 (+18.2%)
Worst Trade: TSLA -$1,890 (-9.1%)
Longest Hold: MSFT 14 days
Shortest Hold: AMZN 3 days
```

## 📊 パフォーマンス指標の詳細

### 1. リターン指標
```
RETURN METRICS
==============
Arithmetic Mean: 1.8% per month
Geometric Mean: 1.7% per month
Compound Annual Growth Rate: 22.4%
Risk-Free Rate: 2.5%
Excess Return: 19.9%
```

### 2. リスク指標
```
RISK METRICS
============
Standard Deviation: 18.3%
Downside Deviation: 12.4%
Tracking Error: 8.9%
Information Ratio: 1.34
Maximum Drawdown Duration: 45 days
```

### 3. 効率性指標
```
EFFICIENCY METRICS
==================
Sharpe Ratio: 1.42
Sortino Ratio: 1.89
Calmar Ratio: 1.81
Omega Ratio: 1.67
```

## 📋 レポートの出力形式

### 1. HTML形式 (デフォルト)
```html
<!DOCTYPE html>
<html>
<head>
    <title>Backtest Report</title>
    <style>
        .summary { background: #f0f8ff; }
        .positive { color: green; }
        .negative { color: red; }
    </style>
</head>
<body>
    <h1>Backtest Results</h1>
    <!-- 詳細なHTMLレポート -->
</body>
</html>
```

### 2. JSON形式
```json
{
    "summary": {
        "total_return": 0.2345,
        "sharpe_ratio": 1.42,
        "max_drawdown": -0.1234,
        "win_rate": 0.625
    },
    "trades": [
        {
            "symbol": "AAPL",
            "entry_date": "2024-01-15",
            "exit_date": "2024-01-22",
            "pnl": 1573.0,
            "return": 0.0847
        }
    ]
}
```

### 3. CSV形式
```csv
Date,Symbol,Action,Price,Quantity,PnL,Portfolio_Value
2024-01-15,AAPL,BUY,185.50,100,0,98150
2024-01-22,AAPL,SELL,201.23,100,1573,101573
```

## 🎨 レポートカスタマイズ

### 設定オプション
```python
REPORT_CONFIG = {
    'include_charts': True,
    'chart_style': 'seaborn',
    'show_trade_details': True,
    'include_benchmark': True,
    'benchmark_symbol': 'SPY',
    'output_format': ['html', 'json', 'csv'],
    'save_location': 'reports/'
}
```

### チャート設定
```python
CHART_CONFIG = {
    'equity_curve': True,
    'drawdown_chart': True,
    'monthly_returns': True,
    'sector_analysis': True,
    'correlation_matrix': True,
    'risk_metrics': True
}
```

## 💡 レポートの読み方のコツ

### 1. 最初に確認すべき指標
1. **Total Return**: 絶対的な成果
2. **Sharpe Ratio**: リスク調整後の効率性
3. **Maximum Drawdown**: 最大リスク
4. **Win Rate**: 戦略の安定性

### 2. 警告サインの見方
- **Win Rate < 50%**: 戦略の見直しが必要
- **Sharpe Ratio < 1.0**: リスクに見合わないリターン
- **Drawdown > 20%**: 高リスク戦略
- **Correlation > 0.8**: 市場依存度が高い

### 3. 改善のヒント
- **月次リターン**: 季節性の活用
- **セクター分析**: 有効セクターの特定
- **取引分析**: エントリー/エグジットの最適化

## 🔄 レポートの更新

### 自動更新設定
```python
AUTO_REPORT = {
    'schedule': 'daily',
    'email_notification': True,
    'recipients': ['trader@example.com'],
    'dashboard_update': True
}
```

---

[トップページに戻る](index.md) | [パラメータガイド](parameters.md) | [FAQ](faq.md) 