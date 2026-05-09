"""State paths and dry-run account adapter for paper trading.

Provides:
- ``StatePaths`` dataclass and ``get_state_paths()`` factory so live and
  dry-run paths share one resolution layer.
- ``DryRunAccount`` adapter that exposes the same surface as
  ``AlpacaOrderManager`` (``get_account_summary``, ``get_positions``,
  ``submit_market_order``, ``get_order_by_client_id``, ``cancel_order``)
  but reads from the dry-run state files and fills orders deterministically
  using a caller-supplied ``reference_price``. This lets dry-run cron run
  without ``ALPACA_API_KEY_PAPER`` and lets parity tests run without any
  live broker.

Design contract (per backtest-to-live parity plan, rev 12):
- ``DryRunAccount.submit_market_order`` is **read-only on state**. It only
  builds and returns a result dict. All persisted state mutations happen
  in ``execute_pending`` (``paper_auto_entry``) under the file lock.
- Portfolio value is derived from state + the day's pre-open price for each
  open position so the result is deterministic given (state, today_str).
- ``get_order_by_client_id`` always returns ``None`` because there is no
  underlying broker; the dry-run path never reaches the
  ``pending_unfilled`` branch in ``_submit_with_reconciliation``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import DEFAULTS

# ---------------------------------------------------------------------------
# State path resolution
# ---------------------------------------------------------------------------

# Resolve the project root once at import time. The module lives at
# ``src/paper_state.py`` so the project root is one directory up.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LIVE_STATE_DIR = os.path.join(_PROJECT_ROOT, 'data')
DRYRUN_STATE_DIR = os.path.join(_PROJECT_ROOT, 'data', 'dryrun')


@dataclass(frozen=True)
class StatePaths:
    """Concrete file paths under a single state directory."""
    state_dir: str
    trades: str
    pending_entries: str
    pending_exits: str
    lock: str


def get_state_paths(state_dir: Optional[str] = None) -> StatePaths:
    """Return the canonical paths under ``state_dir`` (defaults to live).

    Pass ``DRYRUN_STATE_DIR`` (or any path) for dry-run isolation. Caller
    is responsible for ensuring the directory exists; the cron wrapper
    runs ``mkdir -p`` before invoking python.
    """
    base = state_dir or LIVE_STATE_DIR
    return StatePaths(
        state_dir=base,
        trades=os.path.join(base, 'paper_trades.json'),
        pending_entries=os.path.join(base, 'pending_entries.json'),
        pending_exits=os.path.join(base, 'pending_exits.json'),
        lock=os.path.join(base, '.paper_state.lock'),
    )


# ---------------------------------------------------------------------------
# DryRunAccount
# ---------------------------------------------------------------------------

def _load_json(path: str) -> Any:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


class DryRunAccount:
    """Stand-in for AlpacaOrderManager during dry-run and parity tests.

    Reads positions from ``state_paths.trades`` (open trades). Portfolio
    value = ``initial_capital`` + realized P&L from closed legs +
    unrealized P&L on open positions valued at today's pre-open price.

    ``submit_market_order`` returns a deterministic ``filled`` result based
    on ``reference_price`` so callers can build trade records identical to
    what live execution would yield. **No state writes happen here.**
    """

    def __init__(
        self,
        state_paths: StatePaths,
        *,
        data_fetcher,
        today_str: str,
        initial_capital: float = DEFAULTS.initial_capital,
    ) -> None:
        self.paths = state_paths
        self.data_fetcher = data_fetcher
        self.today_str = today_str
        self.initial_capital = initial_capital

    # ----- Account / positions -----

    def _open_trades(self) -> List[Dict[str, Any]]:
        return [t for t in _load_json(self.paths.trades) if t.get('status') == 'open']

    def get_positions(self) -> List[Dict[str, Any]]:
        """Return list of position dicts compatible with AlpacaOrderManager.get_positions().

        Schema mirrors `_position_to_dict`: symbol, qty, avg_entry_price,
        market_value, current_price.
        """
        positions: List[Dict[str, Any]] = []
        for t in self._open_trades():
            symbol = t.get('symbol')
            shares = int(t.get('remaining_shares', 0) or 0)
            if shares <= 0 or not symbol:
                continue
            entry_price = float(t.get('entry_price', 0) or 0)
            current_price = self._current_price(symbol, fallback=entry_price)
            positions.append({
                'symbol': symbol,
                'qty': shares,
                'avg_entry_price': entry_price,
                'current_price': current_price,
                'market_value': shares * current_price,
                'unrealized_pl': (current_price - entry_price) * shares,
            })
        return positions

    def get_account_summary(self) -> Dict[str, Any]:
        """Return account summary compatible with AlpacaOrderManager.get_account_summary()."""
        trades = _load_json(self.paths.trades)
        realized_pnl = 0.0
        for t in trades:
            for leg in t.get('legs', []) or []:
                if str(leg.get('action', '')).startswith('exit'):
                    realized_pnl += float(leg.get('pnl', 0) or 0)
        positions = self.get_positions()
        unrealized = sum(p['unrealized_pl'] for p in positions)
        long_market_value = sum(p['market_value'] for p in positions)
        equity = self.initial_capital + realized_pnl + unrealized
        cash = equity - long_market_value
        return {
            'portfolio_value': equity,
            'cash': cash,
            'equity': equity,
            'buying_power': cash,
            'long_market_value': long_market_value,
        }

    def _current_price(self, symbol: str, *, fallback: float) -> float:
        try:
            pre = self.data_fetcher.get_preopen_price(symbol, self.today_str)
            if pre is not None:
                return float(pre)
        except Exception:
            pass
        return float(fallback)

    # ----- Order submission (read-only on state) -----

    def submit_market_order(
        self,
        symbol: str,
        qty: int,
        side: str = 'buy',
        client_order_id: Optional[str] = None,
        *,
        reference_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Build a deterministic 'filled' result. Does not persist state."""
        if qty <= 0:
            raise ValueError(f"qty must be > 0, got {qty}")
        if reference_price is None or reference_price <= 0:
            # Caller forgot to inject a reference price; signal an explicit error
            # rather than silently writing a 0-priced fill.
            raise ValueError(
                "DryRunAccount.submit_market_order requires a positive "
                "reference_price (raw pre_open or trigger price)."
            )
        return {
            'id': f'dryrun_{symbol}_{self.today_str}_{side}',
            'client_order_id': client_order_id,
            'status': 'filled',
            'filled_avg_price': float(reference_price),
            'filled_qty': int(qty),
            'symbol': symbol,
            'side': side,
            'submitted_at': datetime.now(timezone.utc).isoformat(),
        }

    def get_order_by_client_id(self, client_order_id: str) -> Optional[Dict[str, Any]]:
        """Always None: dry-run never reaches the unfilled-reconciliation branch."""
        return None

    def cancel_order(self, order_id: str) -> bool:
        """No-op cancel; deterministic dry-run fills never need cancellation."""
        return True
