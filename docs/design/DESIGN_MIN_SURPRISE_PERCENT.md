# 設計変更文書: min_surprise_percent パラメータの追加

## 変更概要

`min_surprise_percent`（最小EPSサプライズ率）パラメータを `BacktestConfig` に追加し、コマンドライン引数から設定可能にする。

## 背景・目的

### 現状の問題
- `min_surprise_percent` は `DataFilter.__init__()` でデフォルト値 `5.0` がハードコードされている
- `BacktestConfig` には存在しない
- コマンドライン引数で変更できない

### 変更の動機
分析結果により、高EPSサプライズ（20%以上）かつ低ギャップ（0-2%）の銘柄が高パフォーマンスを示すことが判明：

| 条件 | 件数 | 勝率 | 平均PnL |
|------|------|------|---------|
| Surprise>=30% & Gap<2% | 42 | 69.0% | 5.86% |
| Surprise>=20% & Gap<1% | 26 | 65.4% | 6.01% |
| 現在の条件 (Gap 0-10%, Surprise 5%+) | 347 | 60.5% | 2.50% |

この仮説を検証するため、`min_surprise_percent` をパラメータ化して様々な閾値でバックテストを実行できるようにする。

## 影響範囲

### 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/config.py` | `BacktestConfig` に `min_surprise_percent` フィールド追加 |
| `src/main.py` | CLI引数 `--min_surprise` 追加、Config/DataFilter への受け渡し |

### 変更不要ファイル

| ファイル | 理由 |
|----------|------|
| `src/data_filter.py` | 既に `min_surprise_percent` を受け取る設計になっている |

## 詳細設計

### 1. src/config.py の変更

```python
@dataclass
class BacktestConfig:
    """バックテスト設定クラス"""
    start_date: str
    end_date: str
    stop_loss: float = 6
    # ... 既存フィールド ...

    # ギャップ上限設定
    max_gap_percent: float = 10.0  # デフォルト: 10%

    # 追加: 最小EPSサプライズ率
    min_surprise_percent: float = 5.0  # デフォルト: 5%
```

### 2. src/main.py の変更

#### 2.1 argparse への引数追加

```python
parser.add_argument('--min_surprise', type=float, default=5.0,
                    help='最小EPSサプライズ率 (%%) (default: 5.0)')
```

#### 2.2 BacktestConfig 生成時

```python
config = BacktestConfig(
    # ... 既存パラメータ ...
    min_surprise_percent=args.min_surprise,
)
```

#### 2.3 DataFilter 生成時

```python
data_filter = DataFilter(
    # ... 既存パラメータ ...
    min_surprise_percent=config.min_surprise_percent,
)
```

## インターフェース

### CLI使用例

```bash
# デフォルト (5%)
python main.py --start_date 2024-01-01

# 高サプライズのみ (20%)
python main.py --start_date 2024-01-01 --min_surprise 20

# 高サプライズ + 低ギャップ
python main.py --start_date 2024-01-01 --min_surprise 20 --max_gap 3
```

## テスト計画

### ユニットテスト

1. **BacktestConfig デフォルト値テスト**
   - `min_surprise_percent` が指定なしで `5.0` になること

2. **BacktestConfig カスタム値テスト**
   - `min_surprise_percent=20.0` を指定した場合に正しく設定されること

3. **CLI引数パーステスト**
   - `--min_surprise 20` が正しくパースされること
   - 引数省略時にデフォルト値 `5.0` が使用されること

### 統合テスト

4. **DataFilter への値受け渡しテスト**
   - `BacktestConfig` の値が `DataFilter` に正しく渡されること

## 互換性

- デフォルト値を `5.0` に設定するため、既存の動作に影響なし
- 既存のテストは修正不要（デフォルト値が同じため）

## 承認

- [ ] 設計レビュー完了
- [ ] TDD実装開始承認
