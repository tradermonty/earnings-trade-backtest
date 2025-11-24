# バックテスト型決算スイング戦略 仕様書

## 概要

バックテスト型決算スイング戦略は、決算発表後のポジティブサプライズとギャップアップを狙ったスイングトレード戦略です。**ドリフト戦略と同じフィルタリング・ランキングロジック**を使用しています。

**参照ファイル:**
- `src/config.py` - 設定パラメータ
- `src/main.py` - メイン実行スクリプト
- `src/data_filter.py` - フィルタリングロジック
- `src/trade_executor.py` - トレード執行・ポジション管理
- `src/data_fetcher.py` - データ取得（FMP/EODHD）
- `scripts/screen_daily_candidates.py` - 日次スクリーナー

---

## 1. スクリーニング条件

### 1.1 FMPスクリーナーフィルター

| フィルター | 条件 | 設定パラメータ | ドリフト対応 |
|-----------|------|----------------|--------------|
| 時価総額 | $5B以上 | `min_market_cap: 5e9` | ✅ `cap: 5to` |
| 時価総額上限 | なし | `max_market_cap: 0` | ✅ |
| 平均出来高 | 200K株以上 | `screener_volume_min: 200_000` | ✅ `sh_avgvol: o200` |
| 株価 | $30以上 | `screener_price_min: 30.0` | ✅ `sh_price: o30` |
| EPSサプライズ | 5%以上 | `min_surprise_percent: 5.0` | ✅ |
| ギャップ率 | 0-10% | `max_gap_percent: 10.0` | ✅ `ta_gap: u10` |

### 1.2 二段階フィルタリング

#### Stage 1: 決算データフィルター（`data_filter._first_stage_filter`）

| フィルター | 条件 | 設定値 |
|-----------|------|--------|
| 国 | US（米国株のみ） | ハードコード |
| EPSサプライズ | >= min_surprise_percent | デフォルト: 5% |
| 実績EPS | > 0（黒字のみ） | ハードコード |

#### Stage 2: 価格・出来高フィルター（`data_filter._second_stage_filter`）

| フィルター | 条件 | 設定値 |
|-----------|------|--------|
| ギャップ率 | 0% <= gap <= max_gap_percent | デフォルト: 0-10% |
| 株価 | >= screener_price_min | デフォルト: $30 |
| 20日平均出来高 | >= screener_volume_min | デフォルト: 200K株 |
| 決算前20日変化率 | >= pre_earnings_change | デフォルト: 0% |

### 1.3 ギャップ計算

```python
# data_filter.py:251-256
gap = (pre_open_price - prev_day_data['Close']) / prev_day_data['Close'] * 100
```

**ルックアヘッドバイアスなし:** ギャップ計算は「前日終値 vs 当日始値（プレマーケット価格）」で行われます。

---

## 2. フィルタリング・ランキング処理フロー

ドリフト戦略と同じ処理フロー：

```
1. FMP決算カレンダーから決算データ取得
   ↓
2. Stage 1: EPSサプライズ >= 5% & 実績EPS > 0 でフィルター
   ↓
3. Stage 2: ギャップ 0-10% & 株価 >= $30 & 出来高 >= 200K でフィルター
   ↓
4. EPSサプライズ降順でソート
   ↓
5. 上位5銘柄を選定（1日あたり）
```

**参照:** `data_filter.py:361` - 上位5銘柄選定ロジック

---

## 3. エントリー設定

| パラメータ | バックテスト | ドリフト戦略 | 設定値 |
|-----------|-------------|--------------|--------|
| エントリータイミング | 寄り（デフォルト） | 寄り | `entry_timing: 'open'` |
| 引けエントリー | オプション | - | `entry_timing: 'close'` |
| ポジションサイズ | 資金の10% | - | `position_size: 10` |
| マージン倍率 | 1.5倍 | - | `margin_ratio: 1.5` |
| スリッページ | 1.0% | 実約定価格 | `slippage: 1.0` |

### 3.1 引けエントリー条件（オプション）

`--entry_timing close` を指定した場合、以下の追加条件が適用されます：

| パラメータ | 条件 | デフォルト値 |
|-----------|------|-------------|
| 日中レンジ位置 | 終値が日中レンジの上位X%以上 | `close_entry_min_intraday_position: 50%` |
| 終値 vs 始値 | 終値が始値のX%以上 | `close_entry_min_close_vs_open: 98%` |
| VWAP条件 | 終値がVWAP上 | `close_entry_require_above_vwap: True` |
| 出来高条件 | 20日平均のX倍以上 | `close_entry_min_volume_ratio: 1.5` |

---

## 4. エグジット設定

| パラメータ | 値 | 設定キー | ドリフト |
|-----------|-----|----------|----------|
| 損切りライン | 10% | `stop_loss: 10` | `stop_loss_pct: 0.10` |
| トレーリングMA期間 | 21日 | `trail_stop_ma: 21` | `trailing_ma_period: 21` |
| 部分利確ライン | 6% | `+6%で50%利確` | `partial_profit_pct: 0.06` |
| 部分利確割合 | 50% | `shares // 2` | `partial_profit_ratio: 0.5` |
| 最大保有日数 | 90日 | `max_holding_days: 90` | `max_holding_days: 90` |

### 4.1 エグジット優先順位

1. **ストップロス:** 日中安値がエントリー価格の-10%を下回った場合
2. **部分利確:** 終値がエントリー価格の+6%以上の場合、50%を利確
3. **トレーリングストップ:** 終値が21MAを下回った場合
4. **最大保有期間:** 90日経過

### 4.2 部分利確の実装

```python
# trade_executor.py:428付近
if current_return >= 0.06:  # +6%
    sell_shares = position['shares'] // 2  # 50%
```

---

## 5. ドリフト戦略との比較

### 5.1 統一済み項目

| 項目 | バックテスト | ドリフト戦略 | 状態 |
|------|-------------|--------------|------|
| EPSサプライズフィルター | >= 5% | >= 5% | ✅ 統一 |
| pre_earnings_change | >= 0% | >= 0% | ✅ 統一 |
| ランキング | EPSサプライズ降順 | EPSサプライズ降順 | ✅ 統一 |
| 銘柄数/日 | 上位5銘柄 | 上位5銘柄 | ✅ 統一 |
| ギャップ率 | 0-10% | ta_gap: u10 | ✅ 統一 |
| 損切り | 10% | 10% | ✅ 統一 |
| 部分利確 | +6%で50% | +6%で50% | ✅ 統一 |
| トレーリングMA | 21日 | 21日 | ✅ 統一 |
| 最大保有日数 | 90日 | 90日 | ✅ 統一 |
| 時価総額 | >= $5B | >= $5B | ✅ 統一 |
| 株価 | >= $30 | >= $30 | ✅ 統一 |
| 平均出来高 | >= 200K | >= 200K | ✅ 統一 |

### 5.2 実装上の差分（結果は同等）

| 項目 | バックテスト | ドリフト戦略 | 備考 |
|------|-------------|--------------|------|
| データソース | FMP API | Finviz | 同じ条件を適用 |
| エントリー方法 | 寄り価格で計算 | 寄り成行注文 | 実運用のため |
| ポジション分割 | 利確時に半分決済 | エントリー時に2分割 | 結果は同等 |
| スリッページ | 1.0%（シミュレーション） | 実約定価格 | バックテストは保守的見積もり |

---

## 6. リスク管理

### 6.1 マージン制御

```python
# risk_manager.py
if total_position_value > capital * margin_ratio:
    # 新規エントリーをスキップ
```

### 6.2 リスクリミット

```python
# config.py
risk_limit: float = 6  # 累積損失が6%を超えたら新規エントリー停止
```

### 6.3 1日あたりの銘柄数制限

```python
# data_filter.py:361
# 各日付の上位5銘柄のみを選定
```

---

## 7. 日次スクリーナー

### 7.1 概要

毎日の候補銘柄を自動検出するスクリプト：

```bash
python scripts/screen_daily_candidates.py --date 2024-06-15
```

### 7.2 スクリーニング条件（デフォルト）

| パラメータ | デフォルト値 | CLI引数 |
|-----------|-------------|---------|
| 最小EPSサプライズ | 5% | `--min_surprise` |
| 最大ギャップ | 10% | `--max_gap` |
| 最小株価 | $30 | `--min_price` |
| 最小時価総額 | $5B | `--min_market_cap` |
| 最小出来高 | 200K | `--min_volume` |

### 7.3 スコアリング

```python
# screen_daily_candidates.py:95-133
スコア = EPS貢献(0-40点) + Gap貢献(0-30点) + モメンタム貢献(0-30点)

# EPS Surprise貢献 (40%):
# - サプライズが高いほど高得点（50%で上限）

# Gap貢献 (30%):
# - 3-7%: 30点 (理想)
# - 1-3% or 7-10%: 20点
# - 0-1%: 10点

# Pre-earnings Momentum貢献 (30%):
# - 上昇トレンドほど高得点（20%で上限）
```

### 7.4 Cron設定（米国西海岸時間）

```bash
# 米国西海岸時間 12:00 PM (平日: 月〜金)
0 12 * * 1-5 /path/to/scripts/cron_daily_screener.sh >> /path/to/logs/screener.log 2>&1
```

### 7.5 出力ファイル

```
./reports/screener/daily_candidates_YYYY-MM-DD.csv
```

出力カラム:
- `date`, `symbol`, `score`, `sector`, `gap_percent`
- `eps_surprise_percent`, `pre_earnings_change`
- `market_cap`, `volume_20d_avg`
- `actual_eps`, `estimate_eps`, `prev_close`, `entry_price`

---

## 8. 実行方法

### 8.1 基本実行

```bash
python main.py --start_date 2024-01-01 --end_date 2024-12-31
```

### 8.2 カスタムパラメータ

```bash
python main.py \
  --start_date 2020-09-01 \
  --end_date 2025-11-21 \
  --stop_loss 10 \
  --position_size 15 \
  --margin_ratio 1.5 \
  --min_market_cap 5 \
  --screener_price_min 30 \
  --min_surprise 5 \
  --max_gap 10
```

### 8.3 引けエントリー

```bash
python main.py --entry_timing close --start_date 2024-01-01
```

### 8.4 日次スクリーナー

```bash
# 今日の候補
python scripts/screen_daily_candidates.py

# 指定日付の候補
python scripts/screen_daily_candidates.py --date 2024-06-15 --verbose
```

---

## 9. 設定ファイル

### 9.1 config.py（デフォルト値）

```python
@dataclass
class BacktestConfig:
    # 基本設定
    start_date: str
    end_date: str
    initial_capital: float = 100000

    # エグジット設定（ドリフト戦略と統一）
    stop_loss: float = 10              # 損切り: 10%
    trail_stop_ma: int = 21            # トレーリングMA: 21日
    max_holding_days: int = 90         # 最大保有: 90日
    partial_profit: bool = True        # 部分利確: 有効

    # ポジション設定
    position_size: float = 10          # ポジションサイズ: 10%
    margin_ratio: float = 1.5          # マージン倍率: 1.5x
    slippage: float = 1.0              # スリッページ: 1.0%

    # フィルタリング設定（ドリフト戦略と統一）
    min_surprise_percent: float = 5.0  # 最小EPSサプライズ: 5%
    max_gap_percent: float = 10.0      # 最大ギャップ: 10%
    pre_earnings_change: float = 0     # 決算前変化率: 0%

    # スクリーナー設定（ドリフト戦略と統一）
    screener_price_min: float = 30.0   # 最小株価: $30
    screener_volume_min: int = 200_000 # 最小出来高: 200K
    min_market_cap: float = 5e9        # 最小時価総額: $5B
    max_market_cap: float = 0          # 最大時価総額: なし

    # エントリータイミング
    entry_timing: str = "open"         # "open" or "close"

    # 引けエントリー条件
    close_entry_min_intraday_position: float = 50.0
    close_entry_min_close_vs_open: float = 98.0
    close_entry_require_above_vwap: bool = True
    close_entry_min_volume_ratio: float = 1.5
```

---

## 10. データソース

### 10.1 FMP (Financial Modeling Prep) - 推奨

- **精度:** 90%+ の決算日精度
- **制限:** 2020年8月以降のデータのみ
- **API:** `FMP_API_KEY` 環境変数が必要

### 10.2 EODHD

- **精度:** 44% の決算日精度
- **制限:** 2015年以前のデータも利用可能
- **API:** `EODHD_API_KEY` 環境変数が必要
- **用途:** 長期バックテスト用

---

## 更新履歴

| 日付 | 内容 |
|------|------|
| 2025-11-23 | 初版作成 |
| 2025-11-23 | ドリフト戦略との条件統一（stop_loss: 10%, min_market_cap: $5B, screener_price_min: $30） |
| 2025-11-23 | 引けエントリー機能を追加（entry_timing: 'close'） |
| 2025-11-23 | 日次スクリーナー仕様を追加 |
| 2025-11-23 | バックテストとドリフト戦略の比較表を追加 |
