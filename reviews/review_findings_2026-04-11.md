# Critical Code Review Findings — ad0f42d

## Executive Summary

| Severity | Count |
|----------|-------|
| Critical | 2 |
| Major | 6 |
| Minor | 8 |
| Info | 2 |

**Overall Assessment**: Conditional — Critical 2件は修正済み。Major 6件は次スプリントで対応。
**Merge Readiness**: Conditional (Critical fixed in follow-up commit)

---

## Critical

### C-1. Friday AMC 決算が月曜スクリーナーから完全に脱落する

- **Location**: `src/data_filter.py:111-113`, `scripts/screen_daily_candidates.py:214-216`
- **Detected by**: Bug Hunter
- **Category**: State Transition / Cross-Module Consistency

**Problem**: `determine_trade_date()` は AMC 報告に対して `base_date + timedelta(days=1)` で翌日を返す。金曜 AMC の場合 `trade_date = Saturday` になる。月曜スクリーナーの stale フィルタ `c.get('trade_date') == date_str` は `Saturday != Monday` で候補を除外する。

**Bug Scenario**:
1. 企業が金曜 AMC で決算発表
2. 月曜にスクリーナー実行: `prev_bday = Friday`, 決算データは取得される
3. `determine_trade_date('Friday', 'AfterMarket')` → `Saturday`
4. stale フィルタ: `'Saturday' != 'Monday'` → 除外
5. 金曜 AMC の全銘柄がサイレントに消失

**Impact**: 毎週金曜の AMC 報告銘柄が月曜スクリーナーから永続的に消失。決算シーズン中は重大なデータ欠落。エラーや警告は一切出ない。バックテストは全 trade_date を処理するためこの問題はない（スクリーナー固有）。

**Fix**: `determine_trade_date()` で週末をスキップする:
```python
def determine_trade_date(self, report_date, market_timing):
    base_date = datetime.strptime(report_date, '%Y-%m-%d')
    if market_timing and 'Before' in market_timing:
        return base_date.strftime('%Y-%m-%d')
    else:
        next_day = base_date + timedelta(days=1)
        # Skip weekends
        while next_day.weekday() >= 5:  # Saturday=5, Sunday=6
            next_day += timedelta(days=1)
        return next_day.strftime('%Y-%m-%d')
```

---

### C-2. `pre_earnings_change` がスコアリングで常に 0 — ランキングの 30% が無効

- **Location**: `src/data_filter.py:332-343`, `scripts/screen_daily_candidates.py:229`
- **Detected by**: Bug Hunter
- **Category**: Cross-Module Consistency

**Problem**: `DataFilter._second_stage_filter()` の `stock_info` dict に `pre_change` キーが格納されない。`_check_price_change()` は bool のみ返し、計算値を捨てている。スクリーナーの `item.get('pre_change', 0)` は常に 0 を返す。`calculate_candidate_score()` の Pre-earnings momentum（30%ウェイト）が全候補で 0 点になり、EPS surprise と Gap だけで順位が決まる。

**Impact**: 候補スコアリングが体系的に不正確。プレアーニングスのモメンタムが異なる候補が同スコアになり、ランキングが誤る。テストは dict リテラルに `pre_earnings_change` を直接設定するため通過するが、本番コードパスでは到達しない値。

**Fix**: `_second_stage_filter()` で `pre_change` 値を `stock_info` に格納する。`_check_price_change()` の戻り値を `(passed: bool, value: float)` のタプルに変更する。

---

## Major

### M-1. `screener_volume_min` が CLI から stock_screener まで伝搬するが全層で無視される

- **Location**: `src/universe_builder.py:37,81`, `src/fmp_data_fetcher.py:1068`, `src/data_filter.py:408`
- **Detected by**: Veteran, TDD, Clean Code, Bug Hunter（全4名）

**Problem**: `--min_volume` CLI 引数が `build_target_universe()` → `stock_screener()` と伝搬するが、`stock_screener()` は docstring で「intentionally ignored」と明記。`DataFilter._check_final_conditions()` は 200,000 をハードコード。ユーザーが `--min_volume 1000000` を指定しても結果は変わらない。テスト `test_passes_screener_params_correctly` はパラメータ転送を検証するが、実際のフィルタ効果は検証していない。

**Fix**: `screener_volume_min` を `build_target_universe()` のシグネチャから削除するか、`DataFilter` に `volume_threshold` パラメータを追加して実際にフィルタする。

---

### M-2. `build_target_universe()` の `None` 返却がバックテストとスクリーナーで逆の意味を持つ

- **Location**: `src/universe_builder.py:96`, `src/main.py:54`, `scripts/screen_daily_candidates.py:159`
- **Detected by**: Veteran

**Problem**: `None` = スクリーナーでは abort（fail closed）、バックテストでは「全銘柄」（レガシー互換）。FMP API 障害時にバックテストは事前フィルタなしで実行され、このPRが解決しようとした乖離が無警告で再発する。

**Fix**: バックテスト側でも `None` 時に `logger.warning()` を出力し、silent fallback を可視化する。将来的には例外ベースに移行。

---

### M-3. `print()` が共有ライブラリ関数に混在し、logger と重複

- **Location**: `src/universe_builder.py:85,88-91,93-94`
- **Detected by**: Veteran, TDD, Clean Code（3名）

**Problem**: `build_target_universe()` は `logger.error()` と `print()` を同時に使用。cron ジョブでは stdout は予測不能な場所に出力される。テスト実行時にコンソールノイズが発生。日本語 print がスクリーナー（英語スクリプト）の出力に混入。

**Fix**: 全 `print()` を `logger.info()` / `logger.debug()` に置換。

---

### M-4. `getattr(data_fetcher, 'fmp_fetcher', None)` が 3 モジュールに分散

- **Location**: `src/universe_builder.py:66`, `src/main.py:211`, `src/data_filter.py:245`
- **Detected by**: Veteran, TDD, Clean Code（3名）

**Problem**: FMP 能力判定が `getattr` による属性探索で行われ、3ファイルに重複。`DataFetcher.fmp_fetcher` がリネームされると全箇所がサイレントに壊れる。型チェッカーでは検出不可。

**Fix**: `DataFetcher` に `has_fmp_screener() -> bool` メソッドを追加し、一元化。

---

### M-5. `_get_universe_source()` が `build_target_universe()` のモード選択ロジックを複製

- **Location**: `src/main.py:203-213`
- **Detected by**: Veteran, Bug Hunter（2名）

**Problem**: 条件分岐の順序と判定基準が `build_target_universe()` と微妙に異なる（`use_fmp_data` チェックの有無）。新モード追加時に二箇所の更新が必要。FMP init 失敗時にレポートのラベルが実態と乖離する可能性。

**Fix**: `build_target_universe()` がソースラベルも返すようにする（タプルまたは Result オブジェクト）。

---

### M-6. `screen_candidates()` が 108 行で 5 責務を持ち、`args` オブジェクトに結合

- **Location**: `scripts/screen_daily_candidates.py:137-244`
- **Detected by**: Clean Code, TDD（2名）

**Problem**: ユニバース構築、日付窓計算、決算データ取得、フィルタリング、スコアリングを 1 関数で実行。`argparse.Namespace` を直接受け取るため、テストで毎回 5 属性の Mock を手動構築する必要がある。`args.min_market_cap * 1e9` の変換が 2 箇所に重複。

**Fix**: 明示的パラメータに分解し、ヘルパー関数を抽出。

---

## Minor

### m-1. `min_market_cap * 1e9` 単位変換が 2 箇所に重複

- **Location**: `scripts/screen_daily_candidates.py:153,194`
- **Detected by**: Clean Code

### m-2. report_generator の HTML インライン条件式が複雑

- **Location**: `src/report_generator.py:292-297`
- **Detected by**: Clean Code

### m-3. `BacktestConfig` がスクリーナーで不要なフィールドのパラメータバッグとして使用

- **Location**: `scripts/screen_daily_candidates.py:188-196`
- **Detected by**: Veteran

### m-4. `max_market_cap >= 1e12` の境界テストが欠落

- **Location**: `src/universe_builder.py:70-73`
- **Detected by**: TDD

### m-5. `execute_backtest()` のステップ番号がずれている (1,2,6,7)

- **Location**: `src/main.py:127,135,151`
- **Detected by**: Clean Code

### m-6. `mid_small_only` 空結果のテストケースが欠落

- **Location**: `tests/test_universe_builder.py`
- **Detected by**: TDD

### m-7. `get_default_date()` の timezone フォールバックが local time になる

- **Location**: `scripts/screen_daily_candidates.py:36-41`
- **Detected by**: Veteran

### m-8. テストで no-op パラメータ転送を検証している

- **Location**: `tests/test_universe_builder.py:45-48`
- **Detected by**: Veteran, TDD

---

## Info

### i-1. テストメソッド内での reimport パターン

- **Location**: `tests/test_screen_daily_candidates.py:241,265,292`
- **Detected by**: TDD

### i-2. FMP 障害時の EODHD フォールバックが target_symbols を渡さない

- **Location**: `src/data_fetcher.py:205-213`
- **Detected by**: Bug Hunter

---

## Persona-Specific Insights

### Veteran Engineer
> この PR は構造的に正しい方向だが、「サイレント劣化」のリスクを新たに導入した。`None` 返却の二重意味、`screener_volume_min` の no-op パラメータは、今後の 3AM デバッグセッションの原因になる。インターフェースの嘘は最も高価な技術的負債。

### TDD Expert
> `build_target_universe()` の DI パターンは模範的。テストは行動を検証しており実装詳細に依存しすぎていない。ただし `1e12` 境界と `mid_small` 空結果のテスト欠落はリファクタリング安全性を損なう。`screen_candidates()` の `args` 依存はテスト設計の限界を示している。

### Clean Code Expert
> テストスイートが最も高品質な部分。`screen_candidates()` は 5 つの抽象レベルを混在させており分割が必要。`print()` を共有ライブラリに入れるのは CQS 違反。`lst`, `total` の命名は意図を伝えていない。

### Bug Hunter
> **金曜 AMC バグ**は見落とされやすい典型例。`timedelta(days=1)` vs `BDay(1)` の不整合が根本原因。テストは `Monday→Friday` を検証するが `Friday→Saturday→(dropped)` は検証していない。`pre_change` の非格納問題は「計算したが保存しなかった」パターンの典型。

---

## Improvement Priority

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| 1 | C-1: Friday AMC trade_date bug | Low (5 lines) | Critical — data loss |
| 2 | C-2: pre_earnings_change always 0 | Low (10 lines) | Critical — ranking broken |
| 3 | M-3: print() → logger | Low (5 lines) | High — operational |
| 4 | M-1: screener_volume_min dead param | Low (remove param) | High — interface trust |
| 5 | M-2: None dual semantics | Medium | High — silent degradation |
| 6 | M-4: getattr centralization | Medium | Medium — fragility |
| 7 | M-5: _get_universe_source | Medium | Medium — audit correctness |
| 8 | M-6: screen_candidates SRP | High (refactor) | Medium — maintainability |
