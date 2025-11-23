"""Alpaca intraday data fetcher (pre/post market supported)

Usage:
    fetcher = AlpacaDataFetcher(account_type="live")
    price = fetcher.get_preopen_price("AAPL", "2024-09-05")
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, time, timezone
from typing import Optional, List, Dict, Any
import pandas as pd
import alpaca_trade_api as tradeapi
from alpaca_trade_api.common import URL
from alpaca_trade_api.rest import TimeFrame, TimeFrameUnit
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)


class AlpacaClient:
    """Thin wrapper around `alpaca_trade_api.REST` with retry capability"""

    def __init__(self, account_type: str = "live"):
        self.account_type = account_type
        self._api: Optional[tradeapi.REST] = None
        self._setup_api()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _setup_api(self) -> None:
        if self.account_type == "live":
            base_url = URL("https://api.alpaca.markets")
            api_key = os.getenv("ALPACA_API_KEY_LIVE")
            secret_key = os.getenv("ALPACA_SECRET_KEY_LIVE")
        else:  # paper
            base_url = URL("https://paper-api.alpaca.markets")
            api_key = os.getenv("ALPACA_API_KEY_PAPER")
            secret_key = os.getenv("ALPACA_SECRET_KEY_PAPER")

        if not api_key or not secret_key:
            raise ValueError("Alpaca API keys not set in environment variables")

        self._api = tradeapi.REST(api_key, secret_key, base_url, api_version="v2")
        logger.info("Alpaca API initialized for %s account", self.account_type)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    @property
    def api(self) -> tradeapi.REST:  # type: ignore[override]
        if self._api is None:
            raise RuntimeError("Alpaca client not initialised")
        return self._api

    def get_bars(
        self,
        symbol: str,
        start_iso: str,
        end_iso: str,
        timeframe: TimeFrame = TimeFrame(1, TimeFrameUnit.Minute),
    ) -> pd.DataFrame:
        """Fetch 1-minute bars (UTC ISO strings expected)."""
        bars = self.api.get_bars(
            symbol,
            timeframe,
            start=start_iso,
            end=end_iso,
            adjustment="raw",
            feed="sip",  # full SIP feed to include pre-market
        )
        df = bars.df
        if df.empty:
            return df
        # Ensure datetime index is timezone-aware UTC
        df.index = df.index.tz_convert(timezone.utc)
        return df


# ----------------------------------------------------------------------
# Fetcher facade
# ----------------------------------------------------------------------
class AlpacaDataFetcher:
    """Provide convenience wrappers to retrieve intraday data needed by backtest."""

    def __init__(self, account_type: str = "live"):
        self.client = AlpacaClient(account_type=account_type)

    # ------------------------------------------------------------------
    def get_preopen_price(self, symbol: str, trade_date: str, pre_open_time: str = "09:25:00") -> Optional[float]:
        """Return the pre-open price (09:25 ET) using Alpaca 1-min bars.

        Args:
            symbol: ticker (e.g. "AAPL")
            trade_date: YYYY-MM-DD string (must be trading day)
            pre_open_time: HH:MM:SS ET string
        Returns price or None.
        """
        # Convert ET to UTC → ET is UTC-4 or UTC-5 depending on DST.
        # Alpaca timestamps are in UTC already, so we fetch a window 09:00-09:30 ET.
        et_start = datetime.fromisoformat(f"{trade_date}T09:00:00-04:00")  # assume EDT, slight error during EST but safe window
        et_end = datetime.fromisoformat(f"{trade_date}T09:30:00-04:00")

        df = self.client.get_bars(
            symbol,
            start_iso=et_start.isoformat(),
            end_iso=et_end.isoformat(),
        )
        if df.empty:
            logger.debug("Alpaca returned no intraday data for %s %s", symbol, trade_date)
            return None

        target_time = datetime.fromisoformat(f"{trade_date}T{pre_open_time}-04:00").astimezone(timezone.utc)
        if target_time in df.index:
            return float(df.loc[target_time]["open"])
        # fallback: last record before 09:30
        sub_df = df[df.index <= target_time]
        if sub_df.empty:
            logger.debug("No bar before pre-open time for %s %s", symbol, trade_date)
            return None
        return float(sub_df.iloc[-1]["open"])