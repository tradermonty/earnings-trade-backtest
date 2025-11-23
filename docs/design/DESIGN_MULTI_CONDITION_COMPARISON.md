# 設計文書: 複数条件一括比較バックテスト

## 概要

高EPSサプライズ & 低ギャップの仮説を検証するため、複数のフィルタ条件を一括でバックテストし、結果を比較するスクリプトを作成する。

## 背景

分析結果により、以下の傾向が確認されている：

| 条件 | 件数 | 勝率 | 平均PnL |
|------|------|------|---------|
| Surprise>=30% & Gap<2% | 42 | 69.0% | 5.86% |
| Surprise>=20% & Gap<1% | 26 | 65.4% | 6.01% |
| Surprise>=20% & Gap<2% | 57 | 63.2% | 4.56% |
| 現在の条件 (Gap 0-10%, Surprise 5%+) | 347 | 60.5% | 2.50% |

**仮説**: 「EPSサプライズが大きいにもかかわらず、ギャップアップしていない銘柄」は、市場がまだ十分に反応していないため、エントリー後の上昇余地が大きい。

## 比較対象条件

| 条件名 | min_surprise | max_gap | 説明 |
|--------|--------------|---------|------|
| baseline | 5% | 10% | 現行条件（ベースライン） |
| condition_1 | 20% | 3% | 提案条件1: 高サプライズ + 中程度の低ギャップ |
| condition_2 | 20% | 2% | 提案条件2: 高サプライズ + 低ギャップ |
| condition_3 | 30% | 1% | 提案条件3: 超高サプライズ + 最低ギャップ |

## 実装計画

### 1. スクリプト構成

**ファイル**: `scripts/analysis/multi_condition_backtest.py`

```
scripts/analysis/multi_condition_backtest.py
├── 条件定義
├── バックテスト実行ループ
├── 結果収集・集計
└── 比較レポート出力
```

### 2. 主要機能

#### 2.1 条件定義
```python
CONDITIONS = [
    {"name": "baseline", "min_surprise": 5.0, "max_gap": 10.0},
    {"name": "condition_1", "min_surprise": 20.0, "max_gap": 3.0},
    {"name": "condition_2", "min_surprise": 20.0, "max_gap": 2.0},
    {"name": "condition_3", "min_surprise": 30.0, "max_gap": 1.0},
]
```

#### 2.2 バックテスト実行
- 各条件で `EarningsBacktest` を初期化
- 同一期間（デフォルト: 2024-01-01 〜 現在）でバックテストを実行
- メトリクス（勝率、平均PnL、トレード数、シャープレシオ等）を収集

#### 2.3 結果比較
- 条件別の結果をDataFrameに集約
- 比較テーブルをコンソールに出力
- CSV/JSONで結果を保存

### 3. 出力形式

#### 3.1 コンソール出力
```
=== Multi-Condition Backtest Comparison ===
Period: 2024-01-01 to 2024-12-31

| Condition    | Trades | Win Rate | Avg PnL | Total Return | Sharpe | Max DD |
|--------------|--------|----------|---------|--------------|--------|--------|
| baseline     | 347    | 60.5%    | 2.50%   | 45.2%        | 1.23   | -12.3% |
| condition_1  | 85     | 65.0%    | 4.50%   | 38.5%        | 1.45   | -8.5%  |
| condition_2  | 57     | 63.2%    | 4.56%   | 26.0%        | 1.38   | -7.2%  |
| condition_3  | 26     | 69.0%    | 6.01%   | 15.6%        | 1.62   | -5.1%  |
```

#### 3.2 ファイル出力
- `reports/multi_condition_comparison_YYYYMMDD.csv`: 詳細結果
- `reports/multi_condition_comparison_YYYYMMDD.json`: 構造化データ

### 4. CLI引数

```bash
python scripts/analysis/multi_condition_backtest.py \
    --start_date 2024-01-01 \
    --end_date 2024-12-31 \
    --output_dir reports \
    --verbose
```

| 引数 | デフォルト | 説明 |
|------|-----------|------|
| `--start_date` | 2024-01-01 | バックテスト開始日 |
| `--end_date` | 今日 | バックテスト終了日 |
| `--output_dir` | reports | 出力ディレクトリ |
| `--verbose` | False | 詳細ログ出力 |
| `--parallel` | False | 並列実行（将来実装） |

## 実装ステップ

### Phase 1: 基本実装
1. [ ] スクリプトの骨格作成
2. [ ] 条件定義とループ処理
3. [ ] EarningsBacktest の呼び出し
4. [ ] 結果収集とDataFrame化

### Phase 2: 出力機能
5. [ ] コンソール出力（比較テーブル）
6. [ ] CSV出力
7. [ ] JSON出力

### Phase 3: オプション機能
8. [ ] CLI引数のパース
9. [ ] 詳細ログオプション
10. [ ] エラーハンドリング

## 依存関係

- `src/main.py`: `EarningsBacktest`, `create_backtest_from_args`
- `src/config.py`: `BacktestConfig`
- `pandas`: 結果集計
- `argparse`: CLI引数

## テスト計画

1. **単体テスト**: 条件定義の正確性
2. **統合テスト**: バックテスト実行と結果収集
3. **手動テスト**: 短期間（1ヶ月）での動作確認

## 注意事項

- API呼び出し回数に注意（FMP rate limit: 600 calls/min）
- 条件によってはトレード数が少なくなり、統計的有意性が低下する可能性
- 実行時間は条件数 × 期間に比例（4条件 × 1年 ≈ 10-20分）

## 成功基準

1. 4つの条件すべてでバックテストが正常完了
2. 比較テーブルが正しく出力される
3. 結果ファイルが正しく保存される
4. 仮説（高サプライズ + 低ギャップの優位性）が検証可能なデータが得られる
