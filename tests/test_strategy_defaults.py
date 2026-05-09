"""Phase 5 parity test: StrategyDefaults coherence + canonical-config invariants.

Catches accidental drift in the source of truth for strategy parameters.
If anyone reintroduces hardcoded constants in paper scripts or changes
``DEFAULTS`` field values without intent, these tests fail loudly.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import DEFAULTS, BacktestConfig, StrategyDefaults


class TestDefaultsCanonicalValues:
    """Lock in the values from the parity plan (rev 12, user-approved)."""

    def test_position_size_is_15(self):
        assert DEFAULTS.position_size == 15.0

    def test_slippage_is_0_3(self):
        assert DEFAULTS.slippage == 0.3

    def test_stop_loss_is_10(self):
        assert DEFAULTS.stop_loss == 10.0

    def test_margin_ratio_is_1_5(self):
        assert DEFAULTS.margin_ratio == 1.5

    def test_risk_limit_is_6(self):
        assert DEFAULTS.risk_limit == 6.0

    def test_partial_profit_threshold_is_6(self):
        assert DEFAULTS.partial_profit_threshold == 6.0

    def test_top_n_per_day_is_5(self):
        assert DEFAULTS.top_n_per_day == 5

    def test_min_volume_20d_is_200000(self):
        assert DEFAULTS.min_volume_20d == 200_000

    def test_screener_price_min_is_30(self):
        assert DEFAULTS.screener_price_min == 30.0

    def test_min_market_cap_is_5b(self):
        assert DEFAULTS.min_market_cap == 5e9

    def test_max_holding_days_is_90(self):
        assert DEFAULTS.max_holding_days == 90

    def test_trail_stop_ma_is_21(self):
        assert DEFAULTS.trail_stop_ma == 21


class TestDefaultsImmutability:
    def test_strategy_defaults_is_frozen(self):
        with pytest.raises(Exception):
            DEFAULTS.position_size = 99.0  # type: ignore[misc]

    def test_strategy_defaults_can_be_constructed(self):
        # Sanity: verify the dataclass can be instantiated with explicit values.
        d = StrategyDefaults(position_size=20.0)
        assert d.position_size == 20.0


class TestBacktestConfigInheritsDefaults:
    """BacktestConfig must read its defaults from DEFAULTS — no separate values."""

    def test_position_size_default_matches_defaults(self):
        cfg = BacktestConfig(start_date='2025-01-01', end_date='2025-12-31')
        assert cfg.position_size == DEFAULTS.position_size

    def test_slippage_default_matches_defaults(self):
        cfg = BacktestConfig(start_date='2025-01-01', end_date='2025-12-31')
        assert cfg.slippage == DEFAULTS.slippage

    def test_stop_loss_default_matches_defaults(self):
        cfg = BacktestConfig(start_date='2025-01-01', end_date='2025-12-31')
        assert cfg.stop_loss == DEFAULTS.stop_loss

    def test_margin_ratio_default_matches_defaults(self):
        cfg = BacktestConfig(start_date='2025-01-01', end_date='2025-12-31')
        assert cfg.margin_ratio == DEFAULTS.margin_ratio

    def test_risk_limit_default_matches_defaults(self):
        cfg = BacktestConfig(start_date='2025-01-01', end_date='2025-12-31')
        assert cfg.risk_limit == DEFAULTS.risk_limit

    def test_pre_earnings_change_default_matches_defaults(self):
        cfg = BacktestConfig(start_date='2025-01-01', end_date='2025-12-31')
        assert cfg.pre_earnings_change == DEFAULTS.pre_earnings_change

    def test_max_gap_default_matches_defaults(self):
        cfg = BacktestConfig(start_date='2025-01-01', end_date='2025-12-31')
        assert cfg.max_gap_percent == DEFAULTS.max_gap_percent

    def test_min_surprise_default_matches_defaults(self):
        cfg = BacktestConfig(start_date='2025-01-01', end_date='2025-12-31')
        assert cfg.min_surprise_percent == DEFAULTS.min_surprise_percent


class TestNoLeftoverHardcodedConstants:
    """Paper scripts must not redefine the constants we centralized.

    If anyone reintroduces ``POSITION_SIZE_PCT`` etc. on the paper modules,
    these tests fail. This protects against silent re-drift.
    """

    def test_paper_auto_entry_has_no_hardcoded_constants(self):
        import scripts.paper_auto_entry as m
        for name in (
            'POSITION_SIZE_PCT', 'SLIPPAGE_PCT', 'STOP_LOSS_PCT',
            'MARGIN_RATIO', 'RISK_LIMIT_PCT',
        ):
            assert not hasattr(m, name), (
                f'{name} reintroduced in paper_auto_entry.py; remove it and '
                f'reference DEFAULTS.{name.lower()} instead.'
            )

    def test_paper_exit_monitor_has_no_hardcoded_constants(self):
        import scripts.paper_exit_monitor as m
        for name in (
            'STOP_LOSS_PCT', 'TRAIL_STOP_MA', 'MAX_HOLDING_DAYS',
            'PARTIAL_PROFIT_THRESHOLD',
        ):
            assert not hasattr(m, name), (
                f'{name} reintroduced in paper_exit_monitor.py; reference '
                f'DEFAULTS.{name.lower()} instead.'
            )
