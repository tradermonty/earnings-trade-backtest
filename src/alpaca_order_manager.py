"""
Alpaca Paper/Live order and position management.

Wraps the alpaca_trade_api REST client for:
- Market order submission (entry/exit)
- Position queries
- Account summary
- Order status and cancellation

Uses client_order_id for idempotency: {symbol}_{date}_{purpose}_{side}
"""

import os
import logging
import math
from typing import Optional, Dict, List, Any

import alpaca_trade_api as tradeapi
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()


class AlpacaOrderManager:
    """Manage orders and positions on Alpaca Paper or Live account."""

    def __init__(self, account_type: str = 'paper'):
        self.account_type = account_type

        if account_type == 'paper':
            base_url = 'https://paper-api.alpaca.markets'
            api_key = os.getenv('ALPACA_API_KEY_PAPER')
            secret_key = os.getenv('ALPACA_SECRET_KEY_PAPER')
        else:
            base_url = 'https://api.alpaca.markets'
            api_key = os.getenv('ALPACA_API_KEY_LIVE')
            secret_key = os.getenv('ALPACA_SECRET_KEY_LIVE')

        if not api_key or not secret_key:
            raise ValueError(
                f"Alpaca {account_type} API keys not found in .env"
            )

        self.api = tradeapi.REST(
            api_key, secret_key, base_url, api_version='v2'
        )
        logger.info("AlpacaOrderManager initialized (%s)", account_type)

    # --- Entry / Exit ---

    def submit_market_order(
        self,
        symbol: str,
        qty: int,
        side: str = 'buy',
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit a market order. Returns order dict or raises on failure."""
        if qty <= 0:
            raise ValueError(f"qty must be > 0, got {qty}")

        try:
            order = self.api.submit_order(
                symbol=symbol,
                qty=str(qty),
                side=side,
                type='market',
                time_in_force='day',
                client_order_id=client_order_id,
            )
            logger.info(
                "Order submitted: %s %s %d shares (client_order_id=%s, order_id=%s)",
                side, symbol, qty, client_order_id, order.id,
            )
            return self._order_to_dict(order)
        except tradeapi.rest.APIError as e:
            if 'duplicate client_order_id' in str(e).lower():
                logger.warning(
                    "Duplicate order skipped: %s (client_order_id=%s)",
                    symbol, client_order_id,
                )
                return {'status': 'duplicate', 'client_order_id': client_order_id}
            raise

    # --- Position Management ---

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions."""
        positions = self.api.list_positions()
        return [self._position_to_dict(p) for p in positions]

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get position for a specific symbol, or None if not held."""
        try:
            p = self.api.get_position(symbol)
            return self._position_to_dict(p)
        except tradeapi.rest.APIError:
            return None

    def close_position(
        self,
        symbol: str,
        qty: Optional[int] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Close position. qty=None closes all shares."""
        if qty is not None:
            return self.submit_market_order(
                symbol, qty, side='sell', client_order_id=client_order_id
            )
        else:
            order = self.api.close_position(symbol)
            logger.info("Position closed: %s (all shares)", symbol)
            return self._order_to_dict(order)

    # --- Account ---

    def get_account_summary(self) -> Dict[str, Any]:
        """Get account summary: cash, portfolio_value, buying_power."""
        account = self.api.get_account()
        return {
            'account_id': account.id,
            'status': account.status,
            'cash': float(account.cash),
            'portfolio_value': float(account.portfolio_value),
            'buying_power': float(account.buying_power),
            'equity': float(account.equity),
            'last_equity': float(account.last_equity),
        }

    # --- Orders ---

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """Get all open (unfilled) orders."""
        orders = self.api.list_orders(status='open')
        return [self._order_to_dict(o) for o in orders]

    def get_order_by_client_id(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        """Look up an existing order by client_order_id for reconciliation."""
        try:
            order = self.api.get_order_by_client_order_id(client_order_id)
            return self._order_to_dict(order)
        except tradeapi.rest.APIError:
            return None

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order by ID. Returns True if cancelled."""
        try:
            self.api.cancel_order(order_id)
            logger.info("Order cancelled: %s", order_id)
            return True
        except tradeapi.rest.APIError as e:
            logger.warning("Cancel failed for %s: %s", order_id, e)
            return False

    # --- Position Sizing ---

    @staticmethod
    def calculate_position_size(
        portfolio_value: float,
        position_size_pct: float,
        prev_close: float,
        slippage_pct: float = 0.3,
    ) -> int:
        """Calculate number of shares to buy.

        Matches RiskManager.calculate_position_size() logic:
        shares = floor(portfolio_value * pct / (price * (1 + slippage)))
        """
        adjusted_price = prev_close * (1 + slippage_pct / 100)
        position_value = portfolio_value * position_size_pct / 100
        shares = math.floor(position_value / adjusted_price)
        return max(shares, 0)

    # --- Client Order ID ---

    @staticmethod
    def make_client_order_id(
        symbol: str, date: str, purpose: str, side: str
    ) -> str:
        """Generate idempotent client_order_id.

        Format: {symbol}_{date}_{purpose}_{side}
        Examples:
          VSNT_2026-03-03_entry_amc_buy
          VSNT_2026-03-10_exit_trail_sell
          VSNT_2026-03-04_exit_partial_sell
        """
        return f"{symbol}_{date}_{purpose}_{side}"

    # --- Internal ---

    @staticmethod
    def _order_to_dict(order) -> Dict[str, Any]:
        return {
            'id': order.id,
            'client_order_id': order.client_order_id,
            'symbol': order.symbol,
            'side': order.side,
            'qty': order.qty,
            'filled_qty': order.filled_qty,
            'filled_avg_price': (
                float(order.filled_avg_price)
                if order.filled_avg_price else None
            ),
            'status': order.status,
            'type': order.type,
            'submitted_at': str(order.submitted_at),
        }

    @staticmethod
    def _position_to_dict(pos) -> Dict[str, Any]:
        return {
            'symbol': pos.symbol,
            'qty': int(pos.qty),
            'avg_entry_price': float(pos.avg_entry_price),
            'current_price': float(pos.current_price),
            'market_value': float(pos.market_value),
            'unrealized_pl': float(pos.unrealized_pl),
            'unrealized_plpc': float(pos.unrealized_plpc),
        }
