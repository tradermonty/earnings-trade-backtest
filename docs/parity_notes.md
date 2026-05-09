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

#### 2021 calendar year — modest positive

| Metric | After fix |
|---|---|
| Trades | 81 |
| Win rate | 56.8% |
| Profit factor | 1.38 |
| Max drawdown | 7.79% |
| Avg holding period | 32.15d |
| Total return | **+14.76%** |

Exit reasons (after fix): trailing_stop=60, stop_loss=18, stop_loss_intraday=2,
partial_profit=1. (Strong post-COVID rally tape; the strategy
participated but did not match SPX's +27%. Lower stop_loss-rate (~25%)
correlated with cleaner trend continuation than the bear-tape years.)

#### 2022 calendar year — bear-tape modest positive

| Metric | After fix |
|---|---|
| Trades | 76 |
| Win rate | 50.0% |
| Profit factor | 1.10 |
| Max drawdown | 16.77% |
| Avg holding period | 27.32d |
| Total return | **+3.79%** |

Exit reasons (after fix): trailing_stop=50, stop_loss=23, partial_profit=2,
stop_loss_intraday=1. (S&P 500 closed -19% in 2022; the strategy
delivered a small positive return but with stop_loss exits at 30% of
trades — comparable degradation pattern to 2025.)

#### 2023 calendar year — modest positive

| Metric | After fix |
|---|---|
| Trades | 96 |
| Win rate | 57.3% |
| Profit factor | 1.12 |
| Max drawdown | 15.77% |
| Avg holding period | 29.2d |
| Total return | **+4.80%** |

Exit reasons (after fix): trailing_stop=61, stop_loss=22, partial_profit=9,
max_holding_days=3, stop_loss_intraday=1.

#### Year-by-year pattern (5 years observed)

| Year | Trades | Win % | PF | MDD | stop_loss % | Return | Note |
|---|---|---|---|---|---|---|---|
| 2022 | 76 | 50.0% | 1.10 | 16.77% | 30% | +3.79% | bear tape |
| 2023 | 96 | 57.3% | 1.12 | 15.77% | 23% | +4.80% | recovery year |
| 2024 | 82 | 68.3% | **2.79** | **3.04%** | 7% | **+45.47%** | trend-followed cleanly |
| 2025 | 104 | 53.9% | 0.93 | 16.01% | 27% | -3.91% | down-year |
| 2026 YTD | 35 | 62.9% | 1.51 | 6.34% | 17% | +7.01% | mark-to-market (10/35 open) |

**Average across 5 years**: arithmetic mean ≈ +11.4% / year, but this is
dominated by the 2024 result. **Excluding 2024** (which may be an
outlier): arithmetic mean ≈ +2.9% / year — a much weaker case.

**Stop-loss-rate pattern** (stop_loss + stop_loss_intraday) / trades:
2022=32%, 2023=24%, 2024=10%, 2025=32%, 2026 YTD=20%. Lower stop-loss
rate strongly correlates with better year-end return. The strategy is
**sensitive to whether positions trend cleanly past the 10% stop-loss
distance**, rather than chopping below it.

Annualized 2026 (extrapolating 7.01% over 4.3 months × 12/4.3): ~+19.6%
gross. Note 10/35 trades are still `end_of_data` (open at cutoff), so
the realized 2026 figure may shift up or down as those positions hit
trailing_stop / stop_loss / max_holding.

#### Critical implications

1. The +25.16% 2025 backtest was **not a clean out-of-sample result**. It
   relied on two distinct look-ahead leaks: same-day close in
   `_check_price_change` and post-earnings volume in
   `_second_stage_filter`.
2. The strategy is **regime-dependent**. Across 5 observed years
   (2022-2026 YTD), 4 of 5 years are positive but only 2024 is strongly
   positive. PF spans 0.93 to 2.79; MDD spans 3% to 17%. The 2024
   result (+45%, PF 2.79, MDD 3%) appears to be an outlier rather than
   the typical year — most years cluster around +3% to +7% with PF
   barely above 1 and MDD ~16%. 2025 is the only negative year in the
   sample.
3. Parameters were probably tuned against the inflated 2025 number; the
   corrected 2025 result puts that tuning on shaky ground. Parameter
   sweeps on **both** years (and any 2024 before-fix comparison if
   reproducible) are needed before live deployment.
4. **DO NOT revert the look-ahead fix.** It is a correctness change;
   reverting would knowingly use future data the live path cannot see at
   09:30 entry execution.

#### Action items (next session)

- Parameter sweeps (`min_surprise`, `max_gap`, `pre_earnings_change`,
  `position_size`, `stop_loss`) against the full 5-year window
  (2022-01-01..2026-05-09) jointly. Optimize on aggregated PF and MDD
  rather than any single year, given the 2024 outlier.
- Investigate the **stop_loss-rate driver**: years with stop_loss rate
  ≤10% (2024) drastically outperform years with stop_loss rate ≥24%
  (2022/2023/2025). What market characteristic predicts a low
  stop_loss-rate regime? Candidates: SPX trend strength, sector
  dispersion, earnings beat-and-raise follow-through.
- Consider widening the stop_loss distance or pairing it with an
  adaptive (volatility-scaled) stop. The current fixed 10% may be
  cutting too many positions in choppier tapes.
- Stratify by sector to see whether degradation concentrates in
  specific groups across the down-year sample (2022/2025).
- Decide on deployment posture given the 5-year picture:
  - **conservative**: ship with reduced position size (e.g. 7-8%
    instead of 15%) given the 4-of-5 years cluster around +3-7%;
  - **regime-aware**: add a top-of-book filter (only trade when SPX is
    in clean uptrend) to skip 2022/2025-like tapes;
  - **revisit thesis**: if no parameter set achieves PF>1.3 over the
    full 5-year window, reconsider the underlying setup.

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

Dry-run cron does **not** require `ALPACA_API_KEY_PAPER` once
`execute_pending` is rewired to construct `DryRunAccount` for dry-run.

**Status (2026-05-09):** `DryRunAccount` is implemented and unit-tested
(`tests/test_dry_run_account.py`, 12 PASS), but `execute_pending`'s
existing mainline still constructs `AlpacaOrderManager(account_type='paper')`
unconditionally and early-returns on `--dry-run` before any order placement.
Routing through `DryRunAccount` is part of the Phase 3c-body work.

### 4.3 Phase ordering in `execute_pending`

Strict order is exit → re-evaluate account → entry. Reversing it would
compute `margin_room` and `risk_gate` against the pre-exit portfolio and
cause spurious entry rejections.

**Status (2026-05-09):** the existing `execute_pending` already follows
exit-first ordering for the live path. The 6-phase rev-12 reorganization
(structured return, strict-fill via `_submit_with_reconciliation`,
DryRunAccount routing, state-dir injection, top-N post-stage-2) is
**Phase 3c work in progress**. Helpers (`_is_filled`, `_skip_entry`,
`_skip_exit`, `_submit_with_reconciliation` with polling/partial-fill)
are implemented and unit-tested but are not yet called from the mainline
`execute_pending` body. Until that wiring lands, the live path retains
its current behavior (`fill_price or prev_close` fallback at
`paper_auto_entry.py:543`, simple state writes), and dry-run still early-
returns at the existing point in the function.

### 4.4 Same-day re-entry

Forbidden: a symbol with any pending exit, placed exit, or failed-fill exit
on date D cannot re-enter on date D. Implemented via a single
`forbidden_today` set in Phase 4 of `execute_pending`.

### 4.5 Stale pending cleanup

`pending_entries` records older than 7 days are dropped by Phase 6.
Records with `submission_status=='pending'` (awaiting `reconcile_pending_orders`)
are exempt and require manual triage.

### 4.6 Reconcile coverage by skip outcome (design spec, not yet wired)

The reconcile policy below is **the design contract**, not the current
behavior. As of 2026-05-09 `scripts/reconcile_pending_orders.py` runs in
two modes:

- **Dry-run** (`--dry-run`): scans state, reports the count of records
  with `submission_status == 'pending'`, exits 0. Working as designed.
- **Live** (no flag): prints `"not yet wired"` and exits 0. The TODO at
  `scripts/reconcile_pending_orders.py:96` marks the spot for the live
  branch. It depends on Phase 3c-body annotating pending records with
  `submission_status='pending'` after polling exhaustion.

When the live branch is implemented (Phase 3c follow-up), the policy is:

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
