---
layout: default
title: パラメータガイド
lang: ja
---

# 📋 詳細パラメータガイド

バックテストシステムの各パラメータの詳細説明と推奨設定を提供します。

## 🎯 基本パラメータ

### 期間設定
```bash
--start_date YYYY-MM-DD    # バックテスト開始日
--end_date YYYY-MM-DD      # バックテスト終了日
```

**推奨設定：**
- **短期テスト**: 1-3ヶ月（戦略の初期検証）
- **中期テスト**: 6-12ヶ月（季節性の考慮）
- **長期テスト**: 2-5年（市場サイクルの考慮）

### 資金管理
```bash
--initial_capital 100000   # 初期資金（デフォルト: $100,000）
--max_position_size 0.1    # 最大ポジションサイズ（デフォルト: 10%）
--commission_rate 0.005    # 手数料率（デフォルト: 0.5%）
```

## 📊 銘柄フィルタリング

### 時価総額フィルタ
```python
# config.py での設定例
MARKET_CAP_FILTER = {
    'min_market_cap': 300_000_000,    # 最小時価総額: $300M
    'max_market_cap': 50_000_000_000  # 最大時価総額: $50B
}
```

**時価総額別特徴：**
- **マイクロキャップ ($50M-$300M)**: 
  - 高ボラティリティ、高リターン機会
  - 流動性リスク、情報不足リスク
- **スモールキャップ ($300M-$2B)**:
  - バランスの取れたリスク・リターン
  - 決算サプライズの影響大
- **ミッドキャップ ($2B-$10B)**:
  - 安定性と成長性のバランス
  - 機関投資家の注目度中程度

### 決算フィルタ
```python
EARNINGS_FILTER = {
    'min_eps_surprise': 0.05,      # 最小EPSサプライズ: 5%
    'min_revenue_surprise': 0.03,  # 最小売上サプライズ: 3%
    'exclude_loss_companies': True # 赤字企業除外
}
```

## 🔍 テクニカル指標

### エントリー条件
```python
ENTRY_CONDITIONS = {
    'rsi_threshold': 70,           # RSI閾値
    'volume_surge_factor': 1.5,    # 出来高急増倍率
    'price_momentum_days': 5,      # 価格モメンタム期間
    'earnings_announcement_days': 2 # 決算発表後日数
}
```

### 出口条件
```python
EXIT_CONDITIONS = {
    'profit_target': 0.15,         # 利益確定: 15%
    'stop_loss': 0.08,             # 損切り: 8%
    'holding_period_max': 10,      # 最大保有期間: 10日
    'trailing_stop_activation': 0.10, # トレイリング開始: 10%
    'trailing_stop_distance': 0.05    # トレイリング幅: 5%
}
```

## 📈 リスク管理パラメータ

### ポジションサイジング
```python
POSITION_SIZING = {
    'method': 'fixed_fractional',  # 固定比率法
    'risk_per_trade': 0.02,        # 1取引あたりリスク: 2%
    'max_positions': 10,           # 最大同時ポジション数
    'correlation_threshold': 0.7    # 相関係数閾値
}
```

### リスク制限
```python
RISK_LIMITS = {
    'max_daily_loss': 0.05,        # 日次最大損失: 5%
    'max_drawdown': 0.20,          # 最大ドローダウン: 20%
    'concentration_limit': 0.25,   # セクター集中度制限: 25%
    'var_confidence': 0.95         # VaR信頼度: 95%
}
```

## 🎨 レポート設定

### チャート生成
```python
CHART_SETTINGS = {
    'generate_equity_curve': True,
    'generate_drawdown_chart': True,
    'generate_monthly_returns': True,
    'generate_sector_analysis': True,
    'chart_style': 'seaborn',
    'figure_size': (12, 8)
}
```

### パフォーマンス指標
```python
PERFORMANCE_METRICS = {
    'calculate_sharpe_ratio': True,
    'calculate_sortino_ratio': True,
    'calculate_calmar_ratio': True,
    'calculate_max_drawdown': True,
    'calculate_win_rate': True,
    'calculate_profit_factor': True,
    'benchmark_symbol': 'SPY'
}
```

## 🔧 高度なパラメータ

### マシンラーニング設定
```python
ML_SETTINGS = {
    'enable_ml_features': False,
    'feature_engineering': {
        'technical_indicators': True,
        'fundamental_ratios': True,
        'sentiment_analysis': False
    },
    'model_type': 'random_forest',
    'lookback_period': 60
}
```

### 最適化設定
```python
OPTIMIZATION = {
    'enable_parameter_optimization': False,
    'optimization_method': 'grid_search',
    'cross_validation_folds': 5,
    'optimization_metric': 'sharpe_ratio',
    'parallel_processing': True
}
```

## 💡 パラメータ調整のベストプラクティス

### 1. 段階的アプローチ
```
1. デフォルト設定でベースライン確立
2. 単一パラメータの感度分析
3. 組み合わせ効果の検証
4. アウトオブサンプルテスト
```

### 2. 過最適化の回避
- **インサンプル期間**: 全期間の70%
- **アウトオブサンプル期間**: 全期間の30%
- **最小取引回数**: 100回以上
- **統計的有意性**: p-value < 0.05

### 3. 堅牢性テスト
```python
ROBUSTNESS_TESTS = {
    'parameter_sensitivity': True,
    'market_regime_analysis': True,
    'monte_carlo_simulation': True,
    'bootstrap_analysis': True
}
```

## 📊 推奨設定プロファイル

### 保守的設定
```python
CONSERVATIVE_PROFILE = {
    'profit_target': 0.10,
    'stop_loss': 0.05,
    'max_position_size': 0.05,
    'risk_per_trade': 0.01,
    'min_market_cap': 1_000_000_000
}
```

### 積極的設定
```python
AGGRESSIVE_PROFILE = {
    'profit_target': 0.25,
    'stop_loss': 0.12,
    'max_position_size': 0.15,
    'risk_per_trade': 0.03,
    'min_market_cap': 300_000_000
}
```

### バランス設定
```python
BALANCED_PROFILE = {
    'profit_target': 0.15,
    'stop_loss': 0.08,
    'max_position_size': 0.10,
    'risk_per_trade': 0.02,
    'min_market_cap': 500_000_000
}
```

## 🔄 パラメータ更新の手順

1. **現在の設定をバックアップ**
2. **変更するパラメータを記録**
3. **小規模テストで検証**
4. **結果を既存設定と比較**
5. **統計的有意性を確認**
6. **本番環境に適用**

---

[トップページに戻る](index.md) | [レポート形式説明](reports.md) | [FAQ](faq.md) 