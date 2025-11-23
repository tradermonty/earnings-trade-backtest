#!/usr/bin/env python3
"""
TDD Tests for Close Entry (Market Close) Filter
引けエントリーフィルターのテスト

Test Cases:
1. 終値が日中レンジの上位50%以上 -> pass
2. 終値が日中レンジの下位50%未満 -> fail
3. 終値が始値の98%超 -> pass
4. 終値が始値の98%以下 -> fail
5. 出来高が20日平均の1.5倍以上 -> pass
6. 出来高が20日平均の1.5倍未満 -> fail
7. VWAP上で引け -> pass
8. VWAP下で引け -> fail
9. 全条件を満たす -> pass
10. 一つでも条件を満たさない -> fail
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import BacktestConfig
from src.trade_executor import TradeExecutor


class TestCloseEntryFilter:
    """引けエントリーフィルターのテストクラス"""

    @pytest.fixture
    def mock_config(self):
        """テスト用のconfig"""
        return BacktestConfig(
            start_date="2024-01-01",
            end_date="2024-12-31",
            entry_timing="close",
            close_entry_min_intraday_position=50.0,
            close_entry_min_close_vs_open=98.0,
            close_entry_require_above_vwap=True,
            close_entry_min_volume_ratio=1.5,
        )

    @pytest.fixture
    def mock_trade_executor(self, mock_config):
        """モックのTradeExecutor"""
        # Mock data fetcher and risk manager
        class MockDataFetcher:
            pass

        class MockRiskManager:
            pass

        executor = TradeExecutor(
            data_fetcher=MockDataFetcher(),
            risk_manager=MockRiskManager(),
            config=mock_config
        )
        return executor

    def create_stock_data(self, open_price, high, low, close, volume, volume_ma20=None):
        """テスト用の株価データを作成"""
        data = {
            'Open': [open_price],
            'High': [high],
            'Low': [low],
            'Close': [close],
            'Volume': [volume],
        }
        if volume_ma20 is not None:
            data['Volume_MA20'] = [volume_ma20]

        df = pd.DataFrame(data)
        df.index = pd.to_datetime(['2024-01-15'])
        return df

    # Test 1: 終値が日中レンジの上位50%以上 -> pass
    def test_close_in_upper_half_of_range_should_pass(self, mock_trade_executor):
        """終値が日中レンジの上位50%以上ならフィルター通過"""
        # Arrange: High=110, Low=100, Close=106 (60% of range from low)
        stock_data = self.create_stock_data(
            open_price=102,
            high=110,
            low=100,
            close=106,  # (106-100)/(110-100) = 60%
            volume=1000000,
            volume_ma20=500000
        )

        # Act
        passes, reason, close_price = mock_trade_executor._check_close_entry_filters(
            stock_data, '2024-01-15'
        )

        # Assert
        assert passes is True
        assert close_price == 106

    # Test 2: 終値が日中レンジの下位50%未満 -> fail
    def test_close_in_lower_half_of_range_should_fail(self, mock_trade_executor):
        """終値が日中レンジの下位50%未満ならフィルター失敗"""
        # Arrange: High=110, Low=100, Close=103 (30% of range from low)
        stock_data = self.create_stock_data(
            open_price=102,
            high=110,
            low=100,
            close=103,  # (103-100)/(110-100) = 30%
            volume=1000000,
            volume_ma20=500000
        )

        # Act
        passes, reason, close_price = mock_trade_executor._check_close_entry_filters(
            stock_data, '2024-01-15'
        )

        # Assert
        assert passes is False
        assert "終値位置" in reason

    # Test 3: 終値が始値の98%超 -> pass
    def test_close_above_98_percent_of_open_should_pass(self, mock_trade_executor):
        """終値が始値の98%超ならフィルター通過"""
        # Arrange: Open=100, Close=100 (100% of open)
        stock_data = self.create_stock_data(
            open_price=100,
            high=105,
            low=95,
            close=100,  # 100/100 = 100%
            volume=1000000,
            volume_ma20=500000
        )

        # Act
        passes, reason, close_price = mock_trade_executor._check_close_entry_filters(
            stock_data, '2024-01-15'
        )

        # Assert
        assert passes is True

    # Test 4: 終値が始値の98%以下 -> fail
    def test_close_below_98_percent_of_open_should_fail(self, mock_trade_executor):
        """終値が始値の98%以下ならフィルター失敗"""
        # Arrange: Open=100, Close=97 (97% of open < 98%)
        # 但し終値位置は上位50%以上にする (97-90)/(100-90) = 70%
        stock_data = self.create_stock_data(
            open_price=100,
            high=100,  # High = Open
            low=90,    # Low is lower
            close=97,  # 97/100 = 97% < 98%, but (97-90)/(100-90) = 70% > 50%
            volume=1000000,
            volume_ma20=500000
        )

        # Act
        passes, reason, close_price = mock_trade_executor._check_close_entry_filters(
            stock_data, '2024-01-15'
        )

        # Assert
        assert passes is False
        assert "終値/始値" in reason

    # Test 5: 出来高が20日平均の1.5倍以上 -> pass
    def test_volume_above_1_5x_average_should_pass(self, mock_trade_executor):
        """出来高が20日平均の1.5倍以上ならフィルター通過"""
        # Arrange: Volume=800000, MA20=500000 (1.6x)
        stock_data = self.create_stock_data(
            open_price=100,
            high=105,
            low=98,
            close=103,  # in upper half, above 98% of open
            volume=800000,  # 1.6x of MA20
            volume_ma20=500000
        )

        # Act
        passes, reason, close_price = mock_trade_executor._check_close_entry_filters(
            stock_data, '2024-01-15'
        )

        # Assert
        assert passes is True

    # Test 6: 出来高が20日平均の1.5倍未満 -> fail
    def test_volume_below_1_5x_average_should_fail(self, mock_trade_executor):
        """出来高が20日平均の1.5倍未満ならフィルター失敗"""
        # Arrange: Volume=600000, MA20=500000 (1.2x)
        stock_data = self.create_stock_data(
            open_price=100,
            high=105,
            low=98,
            close=103,
            volume=600000,  # 1.2x of MA20 < 1.5x
            volume_ma20=500000
        )

        # Act
        passes, reason, close_price = mock_trade_executor._check_close_entry_filters(
            stock_data, '2024-01-15'
        )

        # Assert
        assert passes is False
        assert "出来高比率" in reason

    # Test 7: VWAP上で引け -> pass
    def test_close_above_vwap_should_pass(self, mock_trade_executor):
        """VWAP上で引けるならフィルター通過"""
        # Arrange: typical_price = (H+L+C)/3 = (105+95+102)/3 = 100.67
        # Close=102 > typical_price -> pass
        stock_data = self.create_stock_data(
            open_price=100,
            high=105,
            low=95,
            close=102,
            volume=1000000,
            volume_ma20=500000
        )

        # Act
        passes, reason, close_price = mock_trade_executor._check_close_entry_filters(
            stock_data, '2024-01-15'
        )

        # Assert
        assert passes is True

    # Test 8: VWAP下で引け -> fail
    def test_close_below_vwap_should_fail(self, mock_trade_executor):
        """VWAP下で引けるならフィルター失敗"""
        # Arrange: 他の条件を全て満たしつつ、VWAPのみ下回るデータ
        # High=110, Low=100, Close=104 -> intraday position = (104-100)/(110-100) = 40% -> 50%未満でNG
        # なので、VWAP条件のみ失敗させるには:
        # High=106, Low=100, Close=103 -> intraday = (103-100)/(106-100) = 50%
        # Open=100, Close=103 -> close vs open = 103%
        # typical = (106+100+103)/3 = 103 -> Close=103 >= typical -> Pass
        # VWAPで失敗させるには、closeが典型価格より下にある必要がある
        # High=110, Low=100, Close=102 -> typical = (110+100+102)/3 = 104
        # intraday = (102-100)/(110-100) = 20% -> NG
        #
        # 別アプローチ: VWAPチェックを無効化したconfigでテスト
        # または、VWAPが高くなる条件を作る
        # High=120, Low=100, Close=106 -> typical = (120+100+106)/3 = 108.67
        # intraday = (106-100)/(120-100) = 30% -> NG
        #
        # 結論: VWAPのみ失敗させるデータを作るのは困難なため、
        # 他条件を満たすフィルター設定でテストする
        mock_trade_executor.config.close_entry_min_intraday_position = 10.0  # 緩和

        stock_data = self.create_stock_data(
            open_price=98,  # low open so close is > 98% of open
            high=110,
            low=98,
            close=100,  # (100-98)/(110-98) = 16.7% > 10%, VWAP = (110+98+100)/3 = 102.67
            volume=1000000,
            volume_ma20=500000
        )

        # Act
        passes, reason, close_price = mock_trade_executor._check_close_entry_filters(
            stock_data, '2024-01-15'
        )

        # Assert
        assert passes is False
        assert "VWAP" in reason

    # Test 9: 全条件を満たす -> pass
    def test_all_conditions_met_should_pass(self, mock_trade_executor):
        """全条件を満たす場合はフィルター通過"""
        # Arrange: すべての条件を満たすデータ
        # intraday position: (105-100)/(110-100) = 50%
        # close vs open: 105/100 = 105%
        # volume ratio: 800000/500000 = 1.6x
        # VWAP: typical = (110+100+105)/3 = 105, close=105 >= typical
        stock_data = self.create_stock_data(
            open_price=100,
            high=110,
            low=100,
            close=105,
            volume=800000,
            volume_ma20=500000
        )

        # Act
        passes, reason, close_price = mock_trade_executor._check_close_entry_filters(
            stock_data, '2024-01-15'
        )

        # Assert
        assert passes is True
        assert reason == "OK"
        assert close_price == 105

    # Test 10: データが存在しない日付 -> fail
    def test_missing_date_should_fail(self, mock_trade_executor):
        """データが存在しない日付ではフィルター失敗"""
        stock_data = self.create_stock_data(
            open_price=100,
            high=110,
            low=100,
            close=105,
            volume=800000,
            volume_ma20=500000
        )

        # Act
        passes, reason, close_price = mock_trade_executor._check_close_entry_filters(
            stock_data, '2024-01-20'  # 存在しない日付
        )

        # Assert
        assert passes is False
        assert "データなし" in reason


class TestEntryTimingConfig:
    """エントリータイミング設定のテスト"""

    def test_default_entry_timing_is_open(self):
        """デフォルトのエントリータイミングは寄り付き"""
        config = BacktestConfig(start_date="2024-01-01", end_date="2024-12-31")
        assert config.entry_timing == "open"

    def test_can_set_close_entry_timing(self):
        """引けエントリーを設定できる"""
        config = BacktestConfig(
            start_date="2024-01-01",
            end_date="2024-12-31",
            entry_timing="close"
        )
        assert config.entry_timing == "close"

    def test_close_entry_filter_defaults(self):
        """引けエントリーフィルターのデフォルト値"""
        config = BacktestConfig(start_date="2024-01-01", end_date="2024-12-31")
        assert config.close_entry_min_intraday_position == 50.0
        assert config.close_entry_min_close_vs_open == 98.0
        assert config.close_entry_require_above_vwap is True
        assert config.close_entry_min_volume_ratio == 1.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
