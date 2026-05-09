"""Tests for src.alpaca_order_manager.AlpacaOrderManager"""

import pytest
import math
from unittest.mock import Mock, patch, MagicMock
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.alpaca_order_manager import AlpacaOrderManager


class TestPositionSizing:

    def test_basic_sizing(self):
        shares = AlpacaOrderManager.calculate_position_size(
            portfolio_value=100000, position_size_pct=15.0,
            entry_price=50.0, slippage_pct=0.3,
        )
        # 100000 * 0.15 / (50 * 1.003) = 15000 / 50.15 = 299.1
        assert shares == 299

    def test_sizing_with_zero_slippage(self):
        shares = AlpacaOrderManager.calculate_position_size(
            portfolio_value=100000, position_size_pct=10.0,
            entry_price=100.0, slippage_pct=0.0,
        )
        assert shares == 100

    def test_sizing_floors_to_integer(self):
        shares = AlpacaOrderManager.calculate_position_size(
            portfolio_value=100000, position_size_pct=15.0,
            entry_price=33.14, slippage_pct=0.3,
        )
        expected = math.floor(15000 / (33.14 * 1.003))
        assert shares == expected

    def test_sizing_returns_zero_for_expensive_stock(self):
        shares = AlpacaOrderManager.calculate_position_size(
            portfolio_value=100, position_size_pct=1.0,
            entry_price=500.0, slippage_pct=0.3,
        )
        assert shares == 0


class TestClientOrderId:

    def test_entry_format(self):
        cid = AlpacaOrderManager.make_client_order_id(
            'VSNT', '2026-03-03', 'entry_amc', 'buy'
        )
        assert cid == 'VSNT_2026-03-03_entry_amc_buy'

    def test_exit_stop_format(self):
        cid = AlpacaOrderManager.make_client_order_id(
            'VSNT', '2026-03-10', 'exit_stop', 'sell'
        )
        assert cid == 'VSNT_2026-03-10_exit_stop_sell'

    def test_exit_partial_format(self):
        cid = AlpacaOrderManager.make_client_order_id(
            'VSNT', '2026-03-04', 'exit_partial', 'sell'
        )
        assert cid == 'VSNT_2026-03-04_exit_partial_sell'

    def test_exit_trail_format(self):
        cid = AlpacaOrderManager.make_client_order_id(
            'DY', '2026-03-20', 'exit_trail', 'sell'
        )
        assert cid == 'DY_2026-03-20_exit_trail_sell'


class TestSubmitMarketOrder:

    @patch.dict(os.environ, {
        'ALPACA_API_KEY_PAPER': 'test', 'ALPACA_SECRET_KEY_PAPER': 'test'
    })
    @patch('src.alpaca_order_manager.tradeapi.REST')
    def test_submit_buy_order(self, MockREST):
        mock_api = MockREST.return_value
        mock_order = Mock()
        mock_order.id = 'order123'
        mock_order.client_order_id = 'VSNT_2026-03-03_entry_amc_buy'
        mock_order.symbol = 'VSNT'
        mock_order.side = 'buy'
        mock_order.qty = '45'
        mock_order.filled_qty = '45'
        mock_order.filled_avg_price = '33.14'
        mock_order.status = 'filled'
        mock_order.type = 'market'
        mock_order.submitted_at = '2026-03-03T09:30:00Z'
        mock_api.submit_order.return_value = mock_order

        mgr = AlpacaOrderManager(account_type='paper')
        result = mgr.submit_market_order(
            'VSNT', 45, side='buy',
            client_order_id='VSNT_2026-03-03_entry_amc_buy',
        )

        assert result['symbol'] == 'VSNT'
        assert result['side'] == 'buy'
        assert result['status'] == 'filled'
        mock_api.submit_order.assert_called_once()

    @patch.dict(os.environ, {
        'ALPACA_API_KEY_PAPER': 'test', 'ALPACA_SECRET_KEY_PAPER': 'test'
    })
    @patch('src.alpaca_order_manager.tradeapi.REST')
    def test_duplicate_order_returns_status(self, MockREST):
        mock_api = MockREST.return_value
        mock_api.submit_order.side_effect = tradeapi.rest.APIError(
            {'message': 'Duplicate client_order_id'}
        )

        mgr = AlpacaOrderManager(account_type='paper')
        result = mgr.submit_market_order(
            'VSNT', 45, client_order_id='VSNT_2026-03-03_entry_amc_buy',
        )

        assert result['status'] == 'duplicate'

    @patch.dict(os.environ, {
        'ALPACA_API_KEY_PAPER': 'test', 'ALPACA_SECRET_KEY_PAPER': 'test'
    })
    @patch('src.alpaca_order_manager.tradeapi.REST')
    def test_rejects_zero_qty(self, MockREST):
        mgr = AlpacaOrderManager(account_type='paper')
        with pytest.raises(ValueError):
            mgr.submit_market_order('VSNT', 0)


class TestAccountSummary:

    @patch.dict(os.environ, {
        'ALPACA_API_KEY_PAPER': 'test', 'ALPACA_SECRET_KEY_PAPER': 'test'
    })
    @patch('src.alpaca_order_manager.tradeapi.REST')
    def test_returns_summary(self, MockREST):
        mock_api = MockREST.return_value
        mock_account = Mock()
        mock_account.id = 'acc123'
        mock_account.status = 'ACTIVE'
        mock_account.cash = '50000.00'
        mock_account.portfolio_value = '100000.00'
        mock_account.buying_power = '75000.00'
        mock_account.equity = '100000.00'
        mock_account.last_equity = '99000.00'
        mock_api.get_account.return_value = mock_account

        mgr = AlpacaOrderManager(account_type='paper')
        summary = mgr.get_account_summary()

        assert summary['portfolio_value'] == 100000.0
        assert summary['cash'] == 50000.0
        assert summary['status'] == 'ACTIVE'


# Import for APIError reference
import alpaca_trade_api as tradeapi
