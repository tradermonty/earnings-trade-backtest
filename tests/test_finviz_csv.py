"""Offline tests for the Finviz CSV column / unit contract (issue #11).

Contract: docs/finviz_csv_contract.md
"""

import math
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.finviz_csv import (  # noqa: E402
    FinvizCsvError,
    compare_earnings_dates,
    load_finviz_earnings_dates,
    parse_avg_volume,
    parse_market_cap,
    parse_percent,
)
from run_backtest_from_aggregated import (  # noqa: E402
    build_candidates_from_csv,
    filter_dataframe,
)

FIXTURES = ROOT / "tests" / "fixtures" / "finviz"

# Default CLI-like thresholds used across tests
PARAMS = dict(
    min_eps=5.0,
    min_price=10.0,
    max_gap=10.0,
    min_volume=200,          # thousands of shares
    min_market_cap_b=1.0,
    pre_change=0.0,
    min_perf1h=-10.0,
    max_trades_per_day=10,
)

EXPECTED_EPS = {"CCC": 128.64, "AAA": 51.36, "DDD": 10.0, "EEE": 8.0}


def _load(name):
    return pd.read_csv(FIXTURES / name)


# -----------------------------------------------------------------------------
# Unit parsing
# -----------------------------------------------------------------------------


class TestParsePercent:
    def test_explicit_percent_is_percentage_points(self):
        assert parse_percent("0.5%") == pytest.approx(0.5)
        assert parse_percent("-0.49%") == pytest.approx(-0.49)
        assert parse_percent("12.89%") == pytest.approx(12.89)

    def test_bare_number_is_fraction(self):
        assert parse_percent(0.005) == pytest.approx(0.5)
        assert parse_percent("0.005") == pytest.approx(0.5)
        assert parse_percent(0.5136) == pytest.approx(51.36)

    def test_bare_fraction_above_one_is_not_magnitude_guessed(self):
        # 1.2864 is a 128.64% surprise, not 1.29%
        assert parse_percent(1.2864) == pytest.approx(128.64)

    def test_zero_is_measured_not_missing(self):
        assert parse_percent("0%") == 0.0
        assert parse_percent("0.00%") == 0.0
        assert parse_percent(0) == 0.0

    @pytest.mark.parametrize("raw", [None, float("nan"), "", "-", "  "])
    def test_missing_tokens_become_nan(self, raw):
        assert math.isnan(parse_percent(raw))

    def test_unparseable_raises(self):
        with pytest.raises(FinvizCsvError):
            parse_percent("abc%")


class TestMagnitudeSuffixes:
    def test_market_cap_bare_is_millions(self):
        assert parse_market_cap(8642.57) == pytest.approx(8.64257e9)
        assert parse_market_cap("8642.57") == pytest.approx(8.64257e9)

    def test_market_cap_suffixes(self):
        assert parse_market_cap("8.6B") == pytest.approx(8.6e9)
        assert parse_market_cap("450M") == pytest.approx(450e6)
        assert parse_market_cap("$1.2T") == pytest.approx(1.2e12)

    def test_avg_volume_bare_is_thousands(self):
        assert parse_avg_volume(2527.3) == pytest.approx(2_527_300)
        assert parse_avg_volume("2.5M") == pytest.approx(2_500_000)
        assert parse_avg_volume("900K") == pytest.approx(900_000)

    def test_unparseable_raises(self):
        with pytest.raises(FinvizCsvError):
            parse_market_cap("big")


# -----------------------------------------------------------------------------
# filter_dataframe on fixtures
# -----------------------------------------------------------------------------


class TestFilterFixtures:
    @pytest.mark.parametrize("fixture", ["historical.csv", "reordered_explicit_units.csv"])
    def test_expected_candidates(self, fixture):
        out = filter_dataframe(_load(fixture), **PARAMS)
        assert sorted(out["Ticker"]) == sorted(EXPECTED_EPS)
        got = dict(zip(out["Ticker"], out["_eps"]))
        for t, eps in EXPECTED_EPS.items():
            assert got[t] == pytest.approx(eps)

    def test_historical_and_new_headers_agree(self):
        a = filter_dataframe(_load("historical.csv"), **PARAMS)
        b = filter_dataframe(_load("reordered_explicit_units.csv"), **PARAMS)
        cols = ["Ticker", "_eps", "_gap", "_mcap", "_vol", "_perf1h"]
        pd.testing.assert_frame_equal(
            a[cols].sort_values("Ticker").reset_index(drop=True),
            b[cols].sort_values("Ticker").reset_index(drop=True),
        )

    def test_half_percent_surprise_is_excluded(self):
        # BBB: "0.5%" (explicit) and 0.0050 (fraction) both mean 0.5%
        for fixture in ["historical.csv", "reordered_explicit_units.csv"]:
            out = filter_dataframe(_load(fixture), **PARAMS)
            assert "BBB" not in set(out["Ticker"])

    def test_small_gap_and_small_negative_perf1h_are_kept(self):
        out = filter_dataframe(_load("historical.csv"), **PARAMS)
        row = out.set_index("Ticker")
        assert row.loc["CCC", "_gap"] == pytest.approx(0.5)      # not 50
        assert row.loc["EEE", "_perf1h"] == pytest.approx(-0.49)  # not -49

    def test_valid_zero_gap_passes(self):
        out = filter_dataframe(_load("historical.csv"), **PARAMS)
        assert out.set_index("Ticker").loc["DDD", "_gap"] == 0.0

    def test_missing_gap_cell_is_excluded_and_reported(self):
        out = filter_dataframe(_load("historical.csv"), **PARAMS)
        assert "GGG" not in set(out["Ticker"])
        assert out.attrs["missing_report"] == {"0 <= Gap <= 10.0%": 1}

    def test_negative_pre_change_is_excluded(self):
        # HHH: Perf(Month) 0.64% - Change 9.82% < 0
        out = filter_dataframe(_load("historical.csv"), **PARAMS)
        assert "HHH" not in set(out["Ticker"])

    def test_daily_top_n_ranks_by_eps(self):
        params = dict(PARAMS, max_trades_per_day=2)
        out = filter_dataframe(_load("historical.csv"), **params)
        assert list(out["Ticker"]) == ["CCC", "AAA"]


class TestColumnValidation:
    def test_missing_required_column_raises_before_selection(self):
        with pytest.raises(FinvizCsvError) as exc:
            filter_dataframe(_load("missing_gap.csv"), **PARAMS)
        msg = str(exc.value)
        assert "Gap" in msg and "missing column" in msg

    def test_column_only_required_when_filter_enabled(self):
        params = dict(PARAMS, max_gap=None)
        out = filter_dataframe(_load("missing_gap.csv"), **params)
        assert list(out["Ticker"]) == ["AAA"]

    def test_optional_filter_column_required_when_enabled(self):
        with pytest.raises(FinvizCsvError, match="P/B"):
            filter_dataframe(_load("historical.csv"), **dict(PARAMS, max_pb_ratio=5))

    def test_all_missing_columns_reported_together(self):
        df = _load("historical.csv").drop(columns=["Gap", "Market Cap", "Ticker"])
        with pytest.raises(FinvizCsvError) as exc:
            filter_dataframe(df, **PARAMS)
        msg = str(exc.value)
        for name in ["Gap", "Market Cap", "Ticker"]:
            assert name in msg

    def test_unparseable_cell_names_column_and_ticker(self):
        df = _load("historical.csv")
        df["Market Cap"] = df["Market Cap"].astype(object)
        df.loc[df["Ticker"] == "DDD", "Market Cap"] = "n.m."
        with pytest.raises(FinvizCsvError, match=r"Market Cap.*DDD"):
            filter_dataframe(df, **PARAMS)


class TestBuildCandidates:
    def test_percent_and_gap_are_percentage_points(self):
        out = filter_dataframe(_load("historical.csv"), **PARAMS)
        cands = {c["code"]: c for c in build_candidates_from_csv(out)}
        assert cands["CCC"]["percent"] == pytest.approx(128.64)
        assert cands["CCC"]["gap"] == pytest.approx(0.5)
        assert cands["DDD"]["gap"] == 0.0
        assert cands["AAA"]["trade_date"] == "2025-01-02"


# -----------------------------------------------------------------------------
# FMP-vs-Finviz date comparison input
# -----------------------------------------------------------------------------


class TestDateComparison:
    def test_reordered_headers_and_formats(self):
        recs = load_finviz_earnings_dates(_load("earnings_dates.csv"))
        got = {r["symbol"]: r["finviz_date"] for r in recs}
        assert got == {
            "AAA": "2025-07-01",
            "BBB": "2025-07-02",
            "CCC": "2025-07-10",
            "EEE": "2025-07-03",
        }  # DDD has no date and is skipped

    def test_statuses(self):
        recs = load_finviz_earnings_dates(_load("earnings_dates.csv"))
        fmp = [
            {"symbol": "AAA", "fmp_date": "2025-07-01", "time": "bmo"},
            {"symbol": "BBB", "fmp_date": "2025-07-03", "time": "amc"},
            {"symbol": "BBB", "fmp_date": "2025-04-03", "time": "amc"},
            {"symbol": "CCC", "fmp_date": "2025-07-14", "time": "amc"},
        ]
        status = {r["symbol"]: (r["status"], r["date_diff_days"])
                  for r in compare_earnings_dates(recs, fmp)}
        assert status == {
            "AAA": ("EXACT_MATCH", 0),
            "BBB": ("CLOSE_MATCH", 1),
            "CCC": ("LARGE_DIFF", 4),
            "EEE": ("NO_FMP_DATA", None),
        }

    def test_missing_earnings_date_header_raises(self):
        df = _load("earnings_dates.csv").drop(columns=["Earnings Date"])
        with pytest.raises(FinvizCsvError, match="Earnings Date"):
            load_finviz_earnings_dates(df)

    def test_unparseable_date_raises(self):
        df = _load("earnings_dates.csv")
        df.loc[0, "Earnings Date"] = "TBD"
        with pytest.raises(FinvizCsvError, match="AAA"):
            load_finviz_earnings_dates(df)

    def test_skipped_rows_are_reported(self, capsys):
        load_finviz_earnings_dates(_load("earnings_dates.csv"))
        assert "Earnings Date missing, skipped 1 row(s): DDD" in capsys.readouterr().out


# -----------------------------------------------------------------------------
# Review follow-ups
# -----------------------------------------------------------------------------


class TestMissingVersusZero:
    def test_bare_fraction_zero_is_measured(self):
        df = _load("historical.csv")
        df.loc[df["Ticker"] == "AAA", "Change"] = 0.0
        out = filter_dataframe(df, **PARAMS).set_index("Ticker")
        assert out.loc["AAA", "_change"] == 0.0

    def test_zero_eps_passes_zero_threshold(self):
        df = _load("historical.csv")
        df.loc[df["Ticker"] == "BBB", "EPS Surprise"] = 0.0
        out = filter_dataframe(df, **dict(PARAMS, min_eps=0.0))
        assert "BBB" in set(out["Ticker"])

    def test_missing_optional_metric_fails_enabled_filter(self):
        # CCC has no P/E (loss-maker): unknown is not "<= 50"
        out = filter_dataframe(_load("historical.csv"), **dict(PARAMS, max_pe_ratio=50))
        assert "CCC" not in set(out["Ticker"])
        assert out.attrs["missing_report"]["P/E <= 50"] == 1

    def test_missing_eps_reported_once(self):
        df = _load("historical.csv")
        df["EPS Surprise"] = df["EPS Surprise"].astype(object)
        df.loc[df["Ticker"] == "AAA", "EPS Surprise"] = "-"
        out = filter_dataframe(df, **PARAMS)
        report = out.attrs["missing_report"]
        assert report.get("EPS Surprise >= 5.0%") == 1
        assert "EPS Surprise ranking" not in report

    def test_pd_na_is_missing(self):
        assert math.isnan(parse_percent(pd.NA))
        assert math.isnan(parse_market_cap(pd.NA))

    def test_today_volume_is_not_used_as_average_volume(self):
        df = _load("historical.csv").rename(columns={"Average Volume": "Volume"})
        with pytest.raises(FinvizCsvError, match="Average Volume"):
            filter_dataframe(df, **PARAMS)


class TestOrderingAndErrors:
    def test_candidates_are_chronological(self):
        df = pd.concat([_load("historical.csv"), _load("historical.csv")], ignore_index=True)
        df.loc[8:, "Trade Date"] = "2024-12-31"   # second copy is earlier
        df.loc[8:, "Ticker"] = df.loc[8:, "Ticker"] + "2"
        cands = build_candidates_from_csv(filter_dataframe(df, **PARAMS))
        dates = [c["trade_date"] for c in cands]
        assert dates == sorted(dates)
        # within a day, EPS order is kept
        same_day = [c["code"] for c in cands if c["trade_date"] == "2025-01-02"]
        assert same_day == ["CCC", "AAA", "DDD", "EEE"]

    def test_error_reports_original_csv_line(self):
        from src.finviz_csv import add_csv_line_numbers
        df = add_csv_line_numbers(_load("historical.csv"))
        df["Market Cap"] = df["Market Cap"].astype(object)
        df.loc[df["Ticker"] == "DDD", "Market Cap"] = "n.m."
        df = df[df["Ticker"] != "AAA"].reset_index(drop=True)  # shift the index
        with pytest.raises(FinvizCsvError, match=r"CSV line 5 \(DDD\).*'n\.m\.'"):
            filter_dataframe(df, **PARAMS)


class TestCli:
    def test_optional_float(self):
        from run_backtest_from_aggregated import _optional_float
        assert _optional_float("none") is None
        assert _optional_float("OFF") is None
        assert _optional_float("-10") == -10.0

    def test_disabled_filters_do_not_require_columns(self):
        params = dict(PARAMS, max_gap=None, min_price=None, min_volume=None,
                      min_market_cap_b=None, pre_change=None, min_perf1h=None)
        df = _load("historical.csv")[["Trade Date", "Ticker", "EPS Surprise"]]
        out = filter_dataframe(df, **params)
        # only EPS >= 5% applies; BBB (0.5%) is the sole exclusion
        assert sorted(out["Ticker"]) == ["AAA", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]

    def test_main_exits_2_on_missing_column(self, monkeypatch, capsys):
        import run_backtest_from_aggregated as mod
        monkeypatch.setattr(sys, "argv", [
            "prog", str(FIXTURES / "missing_gap.csv"),
            "--start_date", "2025-01-01", "--end_date", "2025-01-31",
        ])
        with pytest.raises(SystemExit) as exc:
            mod.main()
        assert exc.value.code == 2
        assert "Gap" in capsys.readouterr().err
