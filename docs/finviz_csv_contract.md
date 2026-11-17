# Finviz CSV 列・単位契約

保存済みの Finviz エクスポートを読む次の2スクリプトの入力仕様をまとめる。
実装は `src/finviz_csv.py`、テストは `tests/test_finviz_csv.py` と
`tests/fixtures/finviz/`。どれかを変えたら、ほかの2つも合わせて直す。

- `scripts/run_backtest_from_aggregated.py`（集約 CSV からのバックテスト）
- `scripts/compare_fmp_finviz_accuracy.py`（FMP と Finviz の決算日比較）

## 1. 単位の解釈

単位は、セルごとに表記から決める。値の大きさから単位を推測することはしない。
以前の実装は `|v| < 1` なら ×100 としていたため、`0.5%` を 50% と読んでいた。
また、1 以上の小数表記、たとえば `1.2864`（128.64%）を 1.29% と読んでいた。

| 種別 | 表記 | 解釈 |
|---|---|---|
| パーセント列 | `12.89%` のように `%` 付き | そのままパーセントポイント → 12.89 |
| パーセント列 | `0.1289` のように `%` なし | 小数（fraction）→ ×100 → 12.89 |
| Market Cap | 接尾辞なし `8642.57` | 百万ドル → 8.64257e9 USD |
| Market Cap | `K` / `M` / `B` / `T` 付き | 接尾辞どおり。`8.6B` → 8.6e9 USD |
| Average Volume | 接尾辞なし `2527.3` | 千株 → 2,527,300 株 |
| Average Volume | `K` / `M` / `B` / `T` 付き | 接尾辞どおり。`2.5M` → 2,500,000 株 |
| Price・P/S・P/E・P/B・RSI | 数値 | そのまま |

`$` と桁区切りの `,` は無視する。

**`%` なしの数値の扱い**: パーセント列の `%` なしの数値は、常に小数と解釈する。
これは過去の Finviz 数値エクスポートの形式で、`earnings/aggregated_screen*.csv`
では `EPS Surprise` と `Change` がこの形式になっている。パーセントポイントを
`%` なしで書いたファイル、たとえば 0.5% を `0.5` と書いたものは 50% と読まれる。
そのようなファイルは `%` を付けて書き出すこと。

パーセント列は次のとおり。
`EPS Surprise`、`Gap`、`Change`、`Performance (Month)`、`Performance (1 Hour)`、
`Performance (Week)`、`Profit Margin`、`Return on Assets`、`Volatility (Week)`。

## 2. 欠損と 0 の区別

- 空欄、`-`、`nan`、`none`、`na`、`N/A` は欠損として NaN にする。大文字小文字は
  問わない。pandas の `NA` も欠損として扱う。0 にはしない。
- `0`、`0%`、`0.00%` は測定値の 0 として通常どおり評価する。たとえば Gap 0% は
  `0 <= Gap` を満たす。
- 欠損値を持つ行は、その値を使う有効なフィルタで不合格になる。`Trade Date`、
  `Ticker`、`EPS Surprise` が欠損している行も除外する。件数は
  `[WARN] 欠損値のため除外: <フィルタ> -> n/N 行` と表示し、戻り値の
  `DataFrame.attrs["missing_report"]` にも入れる。
- 旧実装では、欠損値はほとんどのフィルタを通過していた。今は不合格になるため、
  任意のフィルタでも結果が変わる。たとえば赤字企業は P/E が空欄なので、
  `--max_pe_ratio` を指定すると除外される。2026-11-16 に実データで確かめたところ、
  `--max_pe_ratio 50` と §5 の CLI 既定値で `earnings/aggregated_screen*.csv` の
  2ファイルを処理すると、旧実装の候補 89 件のうち 16 件が P/E 欠損で、新実装では外れる。
- 上のどれにも当たらない値（例: `n.m.`）は `FinvizCsvError` で停止する。
  メッセージには列名、CSV の行番号（ヘッダーが1行目）、ティッカー、元の値が入る。

## 3. run_backtest_from_aggregated.py の必須列

常に必要な列は `Trade Date`、`Ticker`、`EPS Surprise` の3つ。`EPS Surprise` は
日別上位 N 件の順位付けに使う。

フィルタの列は、閾値が指定されて有効なときだけ必要になる。閾値が `None` なら
不要。CLI では `--min_eps`、`--min_price`、`--max_gap`、`--min_volume`、
`--min_market_cap`、`--pre_change`、`--min_perf1h` に既定値があり、常に有効になる。
これらは `none` か `off` を渡すと無効にできる。例: `--min_perf1h none`。
複数の名前があるものは、左から順に最初に見つかった列を使う。

| フィルタ（CLI 引数） | 必要な列 |
|---|---|
| `--min_eps` | `EPS Surprise` |
| `--min_price` | `Price` / `Open` / `Close` / `Entry Price` / `Entry` |
| `--max_gap`（`0 <= Gap` も含む） | `Gap` |
| `--min_volume`（千株） | `Average Volume` / `Avg Vol` / `Avg Vol (3 month)` |
| `--min_market_cap`（十億ドル） | `Market Cap` |
| `--pre_change` | `Performance (Month)` と `Change`。値は Perf(Month) − Change |
| `--min_perf1h` | `Performance (1 Hour)` |
| `--max_ps_ratio` / `--max_pe_ratio` / `--max_pb_ratio` | `P/S` / `P/E` / `P/B` |
| `--min_profit_margin` / `--min_roa` | `Profit Margin` / `Return on Assets` |
| `--max_volatility_week` | `Volatility (Week)` |
| `--min_perf_week` / `--max_perf_week` | `Performance (Week)` |
| `--max_perf_month` | `Performance (Month)` |
| `--max_rsi14` | `Relative Strength Index (14)` |

当日の出来高 `Volume` は平均出来高の代わりに使わない。以前は代替列に入っていたが、
単位も意味も違うため外した。

列が足りないときは、候補を選ぶ前に `FinvizCsvError` で停止する。足りない列は
すべてまとめて表示する。CLI では終了コード 2 になる。列の並び順は問わない。

`TradeExecutor` は候補リストの順に資金とマージンを計算する。そのため候補は
`Trade Date` の昇順に並べて渡す。同じ日の中は EPS Surprise の降順にする。
旧実装は期間全体を EPS 降順に並べていたので、日付順になっていなかった。

## 4. compare_fmp_finviz_accuracy.py の必須列

| 列 | 必須 | 形式 |
|---|---|---|
| `Ticker` | 必須 | 文字列。空欄の行は読み飛ばし、日付があるのに Ticker が空の行は件数を表示する |
| `Earnings Date` | 必須 | `7/1/25 8:30`、`7/1/2025`、`2025-07-01` のいずれか。時刻は無視する。空欄の行は読み飛ばして件数とティッカーを表示する。解析できない値はエラーにする |
| `Company` | 任意 | 文字列 |

## 5. 既存ファイルへの影響

`earnings/aggregated_screen.csv` と `earnings/aggregated_screen_.csv` は上の契約を
満たしており、エラーなく読める。ただし、旧実装の単位の誤変換が直ったため、
同じ閾値でも候補は変わる。2026-11-16 に CLI 既定値で照合した結果は次のとおり。

- 旧実装の候補は 101 件、新実装は 139 件。97 件は共通で、42 件が増え、4 件が減った。
- 増えた主な理由は2つ。0〜1% の Gap が 1〜99% と読まれて除外されていたことと、
  0〜−1% の Performance (1 Hour) が 0〜−100% と読まれて除外されていたこと。
- 減った理由は、1% 未満の Performance (Month) が大きく読まれ、pre_change を
  誤って通過していたこと。
- 共通の 97 件のうち 8 件は、1 以上の小数表記の EPS Surprise が正しい値になった。
  例: CYBR 1.0515 → 105.15%。
- 候補を渡す順番も、EPS 降順から日付順に変わった。そのため共通の候補でも、
  資金の複利計算とマージン判定の結果が変わり、損益が変わる。

旧実装で作ったバックテスト結果は、この修正の後では再現しない。
`earnings/aggregated_backtest_results.json` などの既存の結果ファイルは旧実装の出力で、
作り直していない。
