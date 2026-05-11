# Backtest-to-Live Parity Notes

This document captures **accepted divergences** between the `main.py` backtest
and the live paper-trading pipeline (`scripts/paper_auto_entry.py`,
`scripts/paper_exit_monitor.py`). It is required reading before any change to
the screener or trade-executor logic.

The companion implementation plan is `~/.claude/plans/zippy-dancing-treehouse.md`.

---

## 1. Look-ahead bias fixes

### 1.1 `pre_earnings_change` (price-change look-ahead)

**Before** (`src/data_filter.py:411-426`): `_check_price_change` indexed
`stock_data.loc[:trade_date].iloc[-1]['Close']` which equals the trade_date
close — a value not available at 09:30 entry execution.

**After** (Phase 2): delegates to
`src/filter_utils.py::compute_pre_earnings_change`, which slices
`prior = stock_data.loc[stock_data.index < trade_date]` (strictly before
trade_date) and returns `(prior.iloc[-1].Close - prior.iloc[-20].Close) /
prior.iloc[-20].Close * 100`. Distance preserved at 19 trading positions to
match prior backtest semantics. Returns `None` on insufficient history;
caller maps to "skip".

### 1.2 `avg_volume_20d` (volume look-ahead)

**Before** (`src/data_filter.py:328`): `stock_data['Volume'].tail(20).mean()`
included the trade_date row and any future rows that had been pre-fetched
into `stock_data`. Since the data fetch window extends
`trade_date + max_holding_days + 30` (`data_filter.py:281-283`), `tail(20)`
was effectively reading the **last 20 bars at the end of the fetched
window**, capturing post-earnings volume spikes that don't exist at 09:30
entry execution.

**After**: delegates to `compute_avg_volume_20d(stock_data, trade_date)`
which takes the mean of the last 20 Volume values **strictly before**
trade_date. Returns `None` on insufficient history.

### 1.3 `pre_open_price=None` fallback policy (decision)

**Decision: retain fallback** in `src/data_filter.py:319-326` for backtest;
live execution skips when pre-open is None.

**Rationale**: measured against the 2025 calendar year on 2026-05-09, FMP
pre-open coverage is materially below the threshold:

| Stage | Total | None | None % |
|---|---|---|---|
| Stage-2 candidates (post second-stage filter, pre top-N) | 465 | 128 | **27.53%** |
| Top-N candidates (after `_select_top_stocks`) | 318 | 75 | **23.58%** |
| Final size after fallback removal | 243 | — | — |

Both stage-2 and top-N None% exceed the 5% threshold defined in the parity
plan. Removing the backtest fallback would shrink the candidate universe
by ~24% in 2025, distorting historical results. Live execution at 09:30
genuinely lacks the daily-Open value, so live must skip.

**Implication**: live universe is smaller than backtest universe by the same
~24% on average. This is the dominant contributor to the
`pre_open != daily_Open` residual drift documented in §3.

**Reproducibility**:
- Measurement script: `scripts/measure_preopen_coverage.py`
- Execution date: 2026-05-09 14:20 UTC
- Window: 2025-01-01..2025-12-31
- Data source: FMP (`DataFetcher.get_preopen_price`)
- Full output: `reports/preopen_coverage_report.json`

If FMP coverage improves materially (e.g. plan upgrade or replacement to an
intraday-1m source), re-run the measurement and consider removing the
fallback to restore exact candidate parity.

### 1.4 Baseline impact (multi-year, run 2026-05-09)

The look-ahead fixes have a **material but year-dependent** effect on
historical results. The strategy still shows strong evidence of edge in
2024, but the 2025 results that the prior literature quoted were
significantly inflated.

#### 2025 calendar year — large drop

| Metric | Before fix | After fix | Δ |
|---|---|---|---|
| Trades | 103 | 104 | +1 |
| Win rate | 60.2% | 53.9% | **-6.3pp** |
| Profit factor | 1.52 | 0.93 | **-0.59** |
| Max drawdown | 3.05% | 16.01% | **+12.96pp** |
| Avg holding period | 28.74d | 25.63d | -3.11d |
| Total return | +25.16% | **-3.91%** | **-29.07pp** |

Exit reasons (after fix): trailing_stop=60, stop_loss=28, partial_profit=9,
stop_loss_intraday=5, max_holding_days=2.

#### 2020 partial year (Aug-Dec) — strong rebound tape

| Metric | After fix |
|---|---|
| Period | 5 months |
| Trades | 42 |
| Win rate | 54.8% |
| Profit factor | 2.43 |
| Max drawdown | 3.14% |
| Total return | **+22.53%** |

Exit reasons (after fix): trailing_stop=34, stop_loss=8.

#### 2021 calendar year — modest positive

| Metric | After fix |
|---|---|
| Trades | 81 |
| Win rate | 56.8% |
| Profit factor | 1.38 |
| Max drawdown | 7.79% |
| Avg holding period | 32.15d |
| Total return | **+14.76%** |

Exit reasons (after fix): trailing_stop=60, stop_loss=18,
partial_profit=1, stop_loss_intraday=2.

#### 2022 calendar year — bear-tape modest positive

| Metric | After fix |
|---|---|
| Trades | 76 |
| Win rate | 50.0% |
| Profit factor | 1.10 |
| Max drawdown | 16.77% |
| Avg holding period | 27.32d |
| Total return | **+3.79%** |

Exit reasons (after fix): trailing_stop=50, stop_loss=23,
partial_profit=2, stop_loss_intraday=1.

#### 2023 calendar year — modest positive

| Metric | After fix |
|---|---|
| Trades | 96 |
| Win rate | 57.3% |
| Profit factor | 1.12 |
| Max drawdown | 15.77% |
| Avg holding period | 29.2d |
| Total return | **+4.80%** |

Exit reasons (after fix): trailing_stop=61, stop_loss=22,
partial_profit=9, stop_loss_intraday=1, max_holding_days=3.

#### 2024 calendar year — strong corrected result

| Metric | After fix |
|---|---|
| Trades | 82 |
| Win rate | **68.3%** |
| Profit factor | **2.79** |
| Max drawdown | 3.04% |
| Avg holding period | 36.57d |
| Total return | **+45.47%** |

Exit reasons (after fix): trailing_stop=68, stop_loss=6, partial_profit=5,
stop_loss_intraday=2, max_holding_days=1. (No "before-fix" comparison
captured for 2024; the strategy ran on the buggy filter then too, but the
2024 universe gave good results regardless.)

#### 2026 year-to-date (Jan 1 – May 9) — recovery underway

| Metric | After fix |
|---|---|
| Trades | 35 |
| Win rate | **62.9%** |
| Profit factor | **1.51** |
| Max drawdown | 6.34% |
| Avg holding period | 26.09d |
| Total return | **+7.01%** (4.3 months elapsed) |

Exit reasons (after fix): trailing_stop=16, end_of_data=10, stop_loss=6,
partial_profit=2, stop_loss_intraday=1. (`end_of_data` = open positions
at the YTD cutoff; final P&L still pending exit triggers.)

#### Year-by-year pattern (6.4 years observed)

| Year | Period | Trades | Win % | PF | MDD | stop_loss % | Return |
|---|---|---|---|---|---|---|---|
| 2020 | Aug-Dec | 42 | 54.8% | 2.43 | 3.14% | 19% | **+22.53%** |
| 2021 | full year | 81 | 56.8% | 1.38 | 7.79% | 25% | **+14.76%** |
| 2022 | full year | 76 | 50.0% | 1.10 | 16.77% | 32% | **+3.79%** |
| 2023 | full year | 96 | 57.3% | 1.12 | 15.77% | 24% | **+4.80%** |
| 2024 | full year | 82 | 68.3% | **2.79** | **3.04%** | 7% | **+45.47%** |
| 2025 | full year | 104 | 53.9% | 0.93 | 16.01% | 27% | **-3.91%** |
| 2026 YTD | 4.3 months | 35 | 62.9% | 1.51 | 6.34% | 17% | **+7.01%** (m2m) |

Exit-reason counts:

| Year | trailing_stop | stop_loss | partial_profit | stop_loss_intraday | max_holding_days | end_of_data |
|---|---|---|---|---|---|---|
| 2020 | 34 | 8 | 0 | 0 | 0 | 0 |
| 2021 | 60 | 18 | 1 | 2 | 0 | 0 |
| 2022 | 50 | 23 | 2 | 1 | 0 | 0 |
| 2023 | 61 | 22 | 9 | 1 | 3 | 0 |
| 2024 | 68 | 6 | 5 | 2 | 1 | 0 |
| 2025 | 60 | 28 | 9 | 5 | 2 | 0 |
| 2026 YTD | 16 | 6 | 2 | 1 | 0 | 10 |

Annualized 2026 (extrapolating 7.01% over 4.3 months × 12/4.3): ~+19.6%
gross. Note 10/35 trades are still `end_of_data` (open at cutoff), so the
realized 2026 figure may shift up or down as those positions hit
trailing_stop / stop_loss / max_holding.

#### Critical implications

1. The +25.16% 2025 backtest was **not a clean out-of-sample result**. It
   relied on two distinct look-ahead leaks: same-day close in
   `_check_price_change` and post-earnings volume in
   `_second_stage_filter`.
2. The strategy is **regime-dependent** but has broadly positive expectancy
   in the observed window: 6 of 7 periods are positive after the look-ahead
   fix. 2020 H2 and 2024 are upside outliers; 2025 is the only negative
   period. Excluding the outlier years, the typical profile is much more
   modest than the 2024 result.
3. Parameters were probably tuned against the inflated 2025 number; the
   corrected 2025 result puts that tuning on shaky ground. Parameter sweeps
   should optimize robustness across regimes, not the best single year.
4. **DO NOT revert the look-ahead fix.** It is a correctness change;
   reverting would knowingly use future data the live path cannot see at
   09:30 entry execution.

#### Action items (next session)

- Run `scripts/parameter_sweep.py` for `min_surprise`, `max_gap`,
  `pre_earnings_change`, `position_size`, and optionally `stop_loss` across
  the full observed window. Rank by worst-period return first, not by the
  best single year.
- Investigate 2025 specifically: why did stop_loss exits more than
  quadruple (6 → 28) while trailing_stop exits dropped (68 → 60). Use
  `scripts/analyze_regime_diagnostics.py` to regenerate exit-reason,
  month, market-cap, and price-range breakdowns from existing trade CSVs.
- Consider stratifying by sector when the trade CSV contains a `sector`
  column. Current default reports reliably expose `market_cap_category`
  and `price_range_category`; the diagnostics script includes `sector`
  automatically when present.
- Decide: ship the strategy as regime-dependent (with documented
  drawdown years), add a regime filter, reduce position size, or seek a
  more robust variant.

### 1.5 Robust parameter candidate (sweep run 2026-05-10)

Multi-axis parameter sweeps using `scripts/parameter_sweep.py` against the
full 6.4-year window (2020 H2, 2021, 2022, 2023, 2024, 2025, 2026 YTD)
identified the following tentative best parameter set, ranked by
**worst-period return first**:

| Parameter | Current default | Sweep candidate |
|---|---|---|
| `min_surprise_percent` | 5.0 | **10.0** |
| `max_gap_percent` | 10.0 | **8.0** |
| `pre_earnings_change` | 0.0 | 0.0 |
| `stop_loss` | 10.0 | **8.0** |
| `position_size` | 15.0 | 15.0 |

#### 6.4-year aggregate metrics

| Metric | Value |
|---|---|
| Total trades | 498 |
| Worst-period return | **+1.98%** |
| Average return | +12.05% |
| Worst-period profit factor | 1.04 |
| Max drawdown | 13.31% |

#### Year-by-year return (candidate parameters)

| Period | Return |
|---|---|
| 2020 H2 | +5.54% |
| 2021 | +14.62% |
| 2022 | +16.36% |
| 2023 | +2.72% |
| 2024 | +38.02% |
| 2025 | +1.98% |
| 2026 YTD | +5.08% |

All 7 observed periods are positive — a meaningful robustness improvement
over the corrected current-default baseline (2025: −3.91%).

#### Axis-by-axis findings

- `max_gap=8` is more robust than 9 / 10.
- `pre_earnings_change > 0` worsens results.
- `min_surprise=10` is better than 8 / 12.5 / 15.
- `position_size=15` is better than 10 / 12.5.
- `stop_loss=8` is better than 7 / 9 / 10.

#### Source sweep artifacts (2026-05-10)

- `reports/parameter_sweep_gap_p15_long_20260510.csv`
- `reports/parameter_sweep_surprise_prechange_p15_long_20260510.csv`
- `reports/parameter_sweep_position_min10_long_20260510.csv`
- `reports/parameter_sweep_min_surprise_refine_long_20260510.csv`
- `reports/parameter_sweep_stop_loss_min10_long_20260510.csv`

#### Status

**Recorded, not yet applied.** Promoting these values to
`StrategyDefaults` is a behavior change with downstream impact (tests,
existing scripts, live cutover gate). The decision and rollout are
tracked separately from this documentation entry.

### 1.6 Regime sensitivity hypothesis (breadth correlation, 2026-05-10)

To make the "regime-dependent" framing in §1.4 / §1.5 concrete, the
candidate-parameter year-by-year returns were aligned with a market
breadth index series. The breadth index is a smoothed 8-day moving
average proxy for the share of constituents in an up-trend; `>0.7`
days are treated as **broad-participation** sessions and
bearish-signal days as **narrow-participation / risk-off** sessions.

Source: `https://tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv`
(remote, range 2016-05-10..2026-05-07). The earlier draft of this
section used a local snapshot ending 2025-08-15; the table and
correlations below have been re-computed using the full remote data so
that 2025 is full-year and 2026 YTD can be included.

| Year | Strategy | S&P 500 proxy | Breadth8 avg | Breadth>0.7 days | Bearish signal days |
|---|---|---|---|---|---|
| 2020 | +5.54% | +14.66% | 0.73 | 49.1% | 0.0% |
| 2021 | +14.62% | +30.51% | 0.83 | 91.3% | 29.0% |
| 2022 | +16.36% | −18.65% | 0.41 | 4.0% | 83.3% |
| 2023 | +2.72% | +26.71% | 0.58 | 17.2% | 20.8% |
| 2024 | +38.02% | +25.59% | 0.761 | 95.6% | 3.6% |
| 2025 | +1.98% | +18.01% | 0.573 | 0.0% | 48.8% |
| 2026 YTD | +5.08% | +7.38% | 0.607 | 0.0% | 46.0% |

**Data caveats.**
- The 2026 YTD row covers through 2026-05-07 only (remote CSV cutoff
  and strategy YTD share the same cutoff window — see §1.4 / §1.5).
  10 of 34 trades for 2026 are still `end_of_data` (open at cutoff),
  so the 2026 number is not yet a final P&L.
- 2020 is a partial year (Aug-Dec) on the strategy side; the breadth
  row covers the full calendar year.
- 2020-2024 and 2025 rows above are *full-year* breadth, full-year
  strategy. The earlier "S&P proxy partial-year" caveat that applied
  to the local snapshot has been resolved by the remote CSV.
- Sample size is 7 yearly observations. Treat all correlations below
  as hypothesis-generating, not confirmatory.

#### Pairwise correlations vs strategy return

| Counter-variable | Pearson r (n=7) |
|---|---|
| S&P 500 proxy return | **0.07** (essentially none) |
| Breadth8 yearly average | 0.32 (weak positive) |
| Breadth>0.7 days share | **0.70** |

The S&P 500 proxy ↔ strategy correlation of ~0.07 is the load-bearing
observation: **the strategy is not an index-level long.** The 0.70
correlation with broad-participation days is suggestive that the
strategy's edge tracks *breadth of follow-through*, not headline index
return. The mid-range Breadth8 *yearly average* correlation (0.32)
hides regime structure that the binary Breadth>0.7 metric exposes more
cleanly — see the regime split below.

#### Working hypothesis: two strong regimes, one weak regime

The yearly aggregate above is unimodal-looking, but trade-level
diagnostics (see §1.4 exit-reason tables and the earlier
`regime_diagnostics` work) suggest the strategy actually performs in
**two distinct strong regimes** that look opposite from a breadth
perspective, plus one specific weak regime.

**Strong regime A — high-breadth broad participation.**
- Breadth is wide; equal-weight / mid-small / non-mega-cap stocks
  participate.
- Post-earnings follow-through lasts long enough for the MA21 trailing
  stop to ride the move (`trailing_stop` exit count dominates).
- Bearish-signal days are scarce; positive earnings get re-rated
  rather than fading.
- 2024 is the textbook case: breadth high, bearish days <4%,
  `stop_loss` count near zero.
- 2021 also fits (Breadth8 avg 0.83, Breadth>0.7 share 91.3%).

**Strong regime B — low-breadth scarce-winner / washed-out tape.**
- Index is weak and breadth is thin (low Breadth8 average, very few
  Breadth>0.7 days), but the strategy still performs well because
  earnings beats are the scarce positive signal in a bear tape and
  get concentrated buying.
- 2022 is the informative case: Breadth8 avg 0.41, Breadth>0.7 share
  4.0%, bearish days 83.3% — yet the strategy returns +16.36%.
  Trade-level: low-breadth subset (<0.40) had ~30 trades, PF ~11.7,
  +27%, with stop_loss frequency under 7%.
- Implication: **low breadth alone is not the risk-off signal for
  this strategy**; the absence of follow-through in *mid* breadth
  while bearish signals dominate is.

**Weak regime — middle-breadth "stuck below 0.70".**
- Index can be flat or rising on narrow leadership, but breadth is
  neither high (so no broad participation) nor washed out (so no
  scarce-winner concentration). The signature is a Breadth8 that
  spends most of the year in the **0.55-0.70 band** without breaking
  above 0.70 (Breadth>0.7 share ≈ 0%).
- Earnings beats fail to follow through, or get sold the same day.
- Rotation is fast; individual trends do not mature before the stop
  hits.
- 2025 (full-year remote breadth): Breadth8 avg 0.573, Breadth>0.7
  share 0.0%, bearish days 48.8%, strategy +1.98% vs S&P proxy
  +18.01%. The full-year remote data shows bearish-day share is much
  lower than the local 2025-08-15 snapshot suggested (48.8% vs
  79.4%), so "bearish days dominate" alone is not the right
  explanation — the right explanation is "Breadth8 stuck in
  0.55-0.70 with no broad-participation days at all" (see 2025
  bucket breakdown below).
- 2026 YTD (through 2026-05-07): Breadth8 avg 0.607, Breadth>0.7
  share 0.0%, bearish days 46.0%. Same regime signature as 2025, but
  the strategy is +5.08% — partly because the 0.55-0.70 band is the
  *only* breadth bucket with material trade count and it has been
  productive YTD (see 2026 bucket breakdown). This is a hint that
  the weak regime is not deterministic; the strategy can still earn
  modestly inside it.
- 2023 partly fits: Breadth8 avg 0.58, Breadth>0.7 share 17.2%,
  strategy +2.72% vs S&P proxy +26.7% — the largest *relative*
  underperformance vs the index, despite a positive absolute number.

This three-regime split is internally consistent with the table at
the top of this section, where 2022 (low breadth) is co-classified as
strong with 2024 (high breadth).

#### Trade-level breakdown: 2022 vs 2025 under candidate params

Re-running the candidate parameter set (`min_surprise=10`, `max_gap=8`,
`stop_loss=8`, `position_size=15`) and joining each trade to the
breadth regime label gives:

**Aggregate by year:**

| Year | Trades | PF | Return | stop_loss% | Avg Breadth8 |
|---|---:|---:|---:|---:|---:|
| 2022 | 68 | 1.53 | +16.36% | 38.2% | 0.405 |
| 2025 | 100 | 1.04 | +1.98% | 40.0% | 0.538 |

**2022 by regime (positive year, low-breadth tape):**

| Regime | Trades | PF | Return contrib. | stop_loss% |
|---|---:|---:|---:|---:|
| low_breadth | 30 | **11.73** | **+27.27%** | 6.7% |
| middle_bearish_or_trend_down | 30 | 0.48 | −12.12% | 66.7% |

**2025 by regime (flat year, mid-breadth tape):**

| Regime | Trades | PF | Return contrib. | stop_loss% |
|---|---:|---:|---:|---:|
| middle_bearish_or_trend_down | 44 | 0.79 | −5.09% | 45.5% |
| no_breadth_data | 33 | 0.87 | −2.17% | 42.4% |
| low_breadth | 12 | 2.61 | +6.20% | 25.0% |
| middle_constructive | 11 | 1.79 | +3.04% | 27.3% |

Key reading:

- The **`middle_bearish_or_trend_down`** regime contributes negative
  returns and ~45–67% `stop_loss` exit share in both years. It is the
  one cohort that is loss-making across regimes in this comparison.
- In 2022, the strong `low_breadth` cohort (PF 11.73) more than
  offsets the bad middle-bearish cohort; in 2025 the middle-bearish
  cohort is too large a share of trades for the smaller `low_breadth`
  and `middle_constructive` cohorts to offset.
- This is the quantitative anchor for "not low-breadth = bad, but
  middle-breadth + bearish = bad."

Source artifacts (local, not committed):

- `reports/breadth_regime_best_2022_2025_joined_trades_20260510.csv`
- `reports/breadth_regime_best_2022_2025_combined_summary_20260510.csv`
- `reports/breadth_regime_best_2022_2025_bucket_summary_20260510.csv`
- `reports/breadth_regime_joined_trades_20260510.csv`
- `reports/breadth_regime_combined_summary_20260510.csv`

#### 2025 full-year refinement (remote breadth)

Joining 2025 candidate-parameter trades against the *full-year* remote
breadth series gives a cleaner picture than the local 2025-08-15
snapshot. Bucketing by Breadth8 at trade entry:

| 2025 Breadth8 bucket | Trades | PF | Return contrib. | stop_loss% |
|---|---:|---:|---:|---:|
| low (<0.40) | 11 | 2.24 | +4.80% | 27.3% |
| 0.40–0.55 | 13 | 1.82 | +5.09% | 38.5% |
| **0.55–0.70** | **76** | **0.80** | **−7.90%** | **42.1%** |
| ≥0.70 | 0 | — | 0.00% | — |

The 0.55–0.70 bucket holds 76% of trades and is the *only* negative
bucket. There is no `≥0.70` bucket because the year never produced a
Breadth>0.7 session. This sharpens the §1.6 weak-regime definition:
the danger is not "bearish-signal-day dominance" per se, it is
**Breadth8 stuck in 0.55–0.70 without breaking out**, which traps
the strategy in the bucket that historically follows through worst.

Monthly contribution within 2025 makes the timing concrete:

| 2025 month | Return contrib. | PF |
|---|---:|---:|
| Feb | −6.59% | 0.27 |
| Aug | −4.61% | 0.10 |
| Oct | −3.95% | 0.56 |
| Apr | +4.85% | 2.28 |
| Dec | +4.31% | 2.39 |

Roughly three months drive the full-year drawdown.

#### 2026 YTD refinement (through 2026-05-07)

| 2026 Breadth8 bucket | Trades | PF | Return contrib. | Note |
|---|---:|---:|---:|---|
| 0.55–0.70 | 32 | 1.42 | +5.19% | main bucket |
| 0.40–0.55 | 2 | 0.71 | −0.12% | small |
| ≥0.70 | 0 | — | 0.00% | not yet observed |

2026 YTD aggregate: 34 trades, PF 1.40, +5.08%, MDD 5.54%. Of the 34
trades, **10 are `end_of_data`** (open at cutoff), so April-onward
attribution is not final.

| 2026 month | Return contrib. | PF | Note |
|---|---:|---:|---|
| Jan | +3.94% | 2.40 | constructive |
| Feb | +4.33% | 3.13 | constructive |
| Mar | −3.73% | 0.06 | stop_loss heavy |
| Apr | +0.53% | 1.14 | many `end_of_data`, not final |

The 2026 YTD gain is concentrated in Jan-Feb. March was a regime
mini-shift (stop_loss-heavy), and April attribution depends on
positions still open at the cutoff.

Source artifacts (local, not committed):

- `reports/breadth_regime_remote_full_2025_buckets_20260510.csv`
- `reports/breadth_regime_remote_full_2025_monthly_20260510.csv`
- `reports/breadth_regime_remote_full_2026ytd_buckets_20260510.csv`
- `reports/breadth_regime_remote_full_2026ytd_monthly_20260510.csv`

(File names recorded for traceability; rename if local convention
differs.)

#### Implications

1. The strategy is best framed as a **breadth-participation long** on
   earnings surprises, not as a market-beta vehicle.
2. Years where the index rises on narrow leadership (e.g. 2023, 2025)
   are *expected* relative-underperformance years for this strategy.
   They are not bugs.
3. A breadth-regime overlay is a candidate enhancement, but the
   trade-level data **does not support a simple "low Breadth8 → de-risk"
   rule** — 2022's low-breadth subset was one of the strongest cohorts
   in the entire window, and 2025's `<0.40` and `0.40–0.55` buckets
   were both positive (PF 2.24 and 1.82). The refined candidate overlay
   shape is: **de-risk when Breadth8 is stuck in the 0.55–0.70 band
   without breaking above 0.70**, optionally further gated on
   bearish-signal-day share. Any overlay should be tested with the same
   out-of-sample discipline as parameter changes, not added by
   inference from n=7.
4. Performance attribution and live monitoring should pair strategy
   P&L with breadth state (not S&P 500 return alone), and should
   distinguish the two strong regimes from the "stuck 0.55–0.70" weak
   regime.

**Status: hypothesis, not action.** No code change follows from this
section. Recorded so the next regime decision (overlay filter, position
sizing by breadth, or "ship as regime-dependent and accept thin years")
starts from a written baseline.

#### Suggested next experiment

Test a regime overlay that, on a per-trade-date basis, either suppresses
new entries or scales `position_size` down when **Breadth8 is in the
0.55–0.70 band and has not produced a Breadth>0.70 session recently**
(operationalize "recently" via a rolling window, e.g. 20 sessions).
The refined target is sharper than "low breadth → de-risk" (which
2022 and the 2025 sub-0.55 buckets directly refute); the target is
the *stuck-middle* tape that traps trades in the worst-PF bucket.

Re-sweep over 2020 H2 – 2026 YTD using the remote breadth CSV and
compare robust-score-ranked output against the no-overlay candidate
set from §1.5. Mandatory checks:

1. 2025 full-year result improves (driven by reduced exposure to the
   0.55–0.70 bucket).
2. 2022 `low_breadth` cohort contribution is preserved (the overlay
   must not down-rank the `<0.40` bucket, since it is the largest
   source of upside in a bad-index year).
3. 2024 strong-breadth result is not materially harmed (overlay
   should pass-through during high-breadth tapes).
4. 2026 YTD `0.55–0.70` bucket (which was *productive* YTD,
   +5.19%) is reviewed separately — overlay must not assume the
   bucket is always loss-making; it is bucket-PF that varies.

---

## 2. Window distance preserved

Pre-earnings change distance is **19 trading positions** (`prior.iloc[-1]`
vs `prior.iloc[-20]`). The look-ahead fix only shifts this window back by
one trading day; it does not change the distance.

Historical backtest numbers, however, **changed materially** — see §1.4 for
the 2025 before/after table. The +25.16% → -3.91% delta means the prior
results were not directly comparable to the corrected numbers; they relied
on the same-day close that the fix removes. Treat any prior literature
quoting the old +25.16% figure as obsolete.

---

## 3. Live execution drift (accepted, bounded)

### 3.1 Entry-price source

| Path | Sizing input price |
|---|---|
| Backtest (`RiskManager.calculate_position_size`) | `trade_date_data['Open']` (daily Open) |
| Live 09:30 (`AlpacaOrderManager.calculate_position_size`) | `pre_open_price` (only available at 09:30:00) |
| Parity-test fixture | `pre_open_price == daily_Open` by construction |

Both paths pass **raw price** to a one-time-slippage sizer. Pre-multiplying
slippage is forbidden (would double-apply). Argument was renamed
`prev_close` → `entry_price` in `AlpacaOrderManager.calculate_position_size`
to reduce confusion.

Typical drift on accepted candidates: <0.5%.

### 3.2 Partial profit timing

| Path | Exit timing |
|---|---|
| Backtest | T+0 close (same trading day, end-of-day) |
| Live (Alpaca paper) | T+1 09:30 (next-day open via market order) |

Drift: ≤1 trading day P&L. Negligible over multi-week trade lifetimes.
Parity tests assert exit reasons match but allow `partial_profit` exit_date
to differ by exactly 1 trading day.

### 3.3 Slippage modeling

| Path | Slippage |
|---|---|
| Backtest | Synthetic 0.3% applied at sizing and at exit triggers |
| Live | Real Alpaca market-order fill |

Monitor weekly: if real fills consistently diverge from synthetic 0.3%,
re-tune `DEFAULTS.slippage` to the empirical median.

### 3.4 Market-cap source

Live uses current FMP screener snapshot (`build_target_universe` runs at
screening time). Backtest uses point-in-time market cap
(`DataFilter._check_historical_market_cap`). Stocks crossing the $5B
boundary mid-window may differ between paths. Impact: small.

### 3.5 `_filter_lightweight` empty-CSV days

Some BMO days produce empty `daily_candidates_*.csv` because no qualifying
earnings exist. This is not a parity bug — both paths see the same input.

---

## 4. Operational notes

### 4.1 Dry-run state location

- Live state: `data/paper_trades.json`, `data/pending_entries.json`,
  `data/pending_exits.json`, `data/.paper_state.lock`.
- Dry-run state: same filenames under `data/dryrun/` so cron screen→execute
  →exit handoff works without polluting live state.
- `cron_paper_dryrun.sh` runs `mkdir -p data/dryrun` before any python
  invocation.

### 4.2 `DryRunAccount`

Dry-run path replaces `AlpacaOrderManager` with `DryRunAccount`
(`src/paper_state.py`):

- Reads `paths.trades` for open positions.
- Portfolio value = `initial_capital` + realized P&L on closed legs +
  unrealized P&L valued at today's `pre_open_price`.
- `submit_market_order(..., reference_price=...)` returns a deterministic
  `filled` result. **Read-only on state**: all writes happen in
  `execute_pending` Phase 6 under the lock.
- `get_order_by_client_id` always returns `None` (no broker; the dry-run
  path never reaches the `pending_unfilled` reconciliation branch).

Dry-run cron does **not** require `ALPACA_API_KEY_PAPER`: `execute_pending`
constructs `DryRunAccount` when `dry_run=True` and no explicit
`alpaca_manager` is injected.

**Status (2026-05-09):** `DryRunAccount` is implemented, routed through
`execute_pending`, and covered by `tests/test_dry_run_account.py` plus
`tests/test_paper_auto_entry.py`.

### 4.3 Phase ordering in `execute_pending`

Strict order is exit → re-evaluate account → entry. Reversing it would
compute `margin_room` and `risk_gate` against the pre-exit portfolio and
cause spurious entry rejections.

**Status (2026-05-09):** `execute_pending` now uses the 6-phase structure:
short-lock plan, exit placement, post-exit account refresh, entry filtering,
entry placement, and short-lock state update. The body returns structured
`entries_*` / `exits_*` records, uses strict-fill reconciliation, persists
`submission_status='pending'` metadata for late fills, supports injected
`state_dir` / `data_fetcher` / `alpaca_manager`, and routes dry-run through
`DryRunAccount`.

### 4.4 Same-day re-entry

Forbidden: a symbol with any pending exit, placed exit, or failed-fill exit
on date D cannot re-enter on date D. Implemented via a single
`forbidden_today` set in Phase 4 of `execute_pending`.

### 4.5 Stale pending cleanup

`pending_entries` records older than 7 days are dropped by Phase 6.
Records with `submission_status=='pending'` (awaiting `reconcile_pending_orders`)
are exempt and require manual triage.

### 4.6 Reconcile coverage by skip outcome

As of 2026-05-09 `scripts/reconcile_pending_orders.py` runs in two modes:

- **Dry-run** (`--dry-run`): scans state, reports the count of records
  with `submission_status == 'pending'`, exits 0. Working as designed.
- **Live** (no flag): scans `pending_entries.json` and
  `pending_exits.json` for `submission_status == 'pending'`, looks up the
  submitted `client_order_id`, applies confirmed fills to `paper_trades.json`,
  removes rejected/cancelled records, and logs still-unresolved orders to
  `logs/paper_dryrun/orders_unresolved_{today}.log`.

The live policy is:

| Outcome | Pending retained? | Auto-reconciled? |
|---|---|---|
| `filled_full`, `filled_partial` | No | n/a |
| `pending_unfilled` (`not_filled`) | Yes (annotated) | Yes (16:03 ET cron) |
| `duplicate_unfilled` | Yes | No (deterministic cid; next-day duplicate path) |
| `rejected` | No | n/a |
| `submit_error_*` | Yes | No (manual triage; `logs/paper_dryrun/orders_unresolved_{today}.log`) |

---

## 5. Required reading order before code edits

If you are about to modify any of the following, read this document first
and update the relevant section if your change touches the contract:

- `src/data_filter.py` — second-stage filter, `_check_price_change`
- `src/filter_utils.py` — pre-earnings change / avg-volume helpers
- `src/trade_executor.py` — partial-profit, trailing stop, max-hold
- `scripts/screen_daily_candidates.py` — ranking, canonical fields
- `scripts/paper_auto_entry.py` — `execute_pending`, share-count basis,
  `check_risk_gate`, state path resolution
- `scripts/paper_exit_monitor.py` — exit conditions, dry-run state
- `src/paper_state.py` — `DryRunAccount`, `StatePaths`
- `src/config.py` — `StrategyDefaults`, `BacktestConfig`
