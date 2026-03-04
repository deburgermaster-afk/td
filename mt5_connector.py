"""
mt5_connector.py - Handles MetaTrader 5 connection, candle fetching,
                   order placement, position management, and symbol info.
"""

from __future__ import annotations

import time
from typing import Optional

import pandas as pd

import config
import trade_logger as tlog

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None  # type: ignore[assignment]


class MT5Connector:
    """Thin wrapper around the MetaTrader5 Python package."""

    def __init__(self) -> None:
        self._connected: bool = False

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Initialise and log into MT5.
        Returns True on success, False otherwise.
        """
        if not MT5_AVAILABLE:
            tlog.log_error("MT5Connector.connect", RuntimeError("MetaTrader5 package not installed"))
            return False

        if not mt5.initialize():
            tlog.log_error("MT5Connector.connect", RuntimeError(f"mt5.initialize() failed: {mt5.last_error()}"))
            return False

        auth = mt5.login(
            login=config.MT5_LOGIN,
            password=config.MT5_PASSWORD,
            server=config.MT5_SERVER,
        )
        if not auth:
            tlog.log_error(
                "MT5Connector.connect",
                RuntimeError(f"mt5.login() failed: {mt5.last_error()}"),
            )
            mt5.shutdown()
            return False

        self._connected = True
        tlog.log_info(f"MT5 connected – login={config.MT5_LOGIN} server={config.MT5_SERVER}")
        return True

    def disconnect(self) -> None:
        if MT5_AVAILABLE and self._connected:
            mt5.shutdown()
            self._connected = False
            tlog.log_info("MT5 disconnected")

    # ── Account info ──────────────────────────────────────────────────────────

    def account_info(self) -> dict:
        """Return a dict with balance, equity, margin, free_margin, profit."""
        if not MT5_AVAILABLE or not self._connected:
            return {}
        info = mt5.account_info()
        if info is None:
            return {}
        return {
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "profit": info.profit,
            "currency": info.currency,
            "leverage": info.leverage,
        }

    # ── Candle data ───────────────────────────────────────────────────────────

    def fetch_candles(
        self,
        symbol: str,
        timeframe=None,
        count: int = 200,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch *count* OHLCV candles for *symbol* on *timeframe*.
        Defaults to M5 (5-minute) candles.
        Returns a pandas DataFrame or None on error.
        """
        if not MT5_AVAILABLE or not self._connected:
            return None

        if timeframe is None:
            timeframe = mt5.TIMEFRAME_M5

        # Ensure the symbol is visible in the Market Watch
        if not mt5.symbol_select(symbol, True):
            tlog.log_error(
                "MT5Connector.fetch_candles",
                RuntimeError(f"Cannot select symbol {symbol}: {mt5.last_error()}"),
            )
            return None

        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) == 0:
            tlog.log_error(
                "MT5Connector.fetch_candles",
                RuntimeError(f"No data for {symbol}: {mt5.last_error()}"),
            )
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df

    # ── Symbol information ────────────────────────────────────────────────────

    def symbol_info(self, symbol: str) -> dict:
        """Return trading contract specs for a symbol."""
        if not MT5_AVAILABLE or not self._connected:
            return {}
        info = mt5.symbol_info(symbol)
        if info is None:
            return {}
        return {
            "bid": info.bid,
            "ask": info.ask,
            "spread": info.spread,
            "digits": info.digits,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "trade_tick_size": info.trade_tick_size,
            "trade_tick_value": info.trade_tick_value,
            "trade_contract_size": info.trade_contract_size,
            "currency_base": info.currency_base,
            "currency_profit": info.currency_profit,
        }

    # ── Position management ───────────────────────────────────────────────────

    def get_open_positions(self, symbol: str = None) -> list[dict]:
        """
        Return a list of open positions, optionally filtered by symbol.
        Each item is a plain dict.
        """
        if not MT5_AVAILABLE or not self._connected:
            return []

        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        if positions is None:
            return []

        result = []
        for p in positions:
            result.append(
                {
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                    "volume": p.volume,
                    "price_open": p.price_open,
                    "sl": p.sl,
                    "tp": p.tp,
                    "profit": p.profit,
                    "time": p.time,
                    "comment": p.comment,
                }
            )
        return result

    def get_all_open_positions(self) -> list[dict]:
        return self.get_open_positions()

    # ── Order placement ───────────────────────────────────────────────────────

    def send_market_order(
        self,
        symbol: str,
        action: str,
        lot_size: float,
        sl: float,
        tp: float,
        comment: str = "AI-Bot",
    ) -> Optional[dict]:
        """
        Place a market order.
        *action* must be 'BUY' or 'SELL'.
        Returns the MT5 order result dict on success, None on failure.
        """
        if not MT5_AVAILABLE or not self._connected:
            tlog.log_error("MT5Connector.send_market_order", RuntimeError("Not connected"))
            return None

        sym_info = mt5.symbol_info(symbol)
        if sym_info is None:
            tlog.log_error(
                "MT5Connector.send_market_order",
                RuntimeError(f"symbol_info({symbol}) returned None"),
            )
            return None

        price = sym_info.ask if action.upper() == "BUY" else sym_info.bid
        order_type = (
            mt5.ORDER_TYPE_BUY if action.upper() == "BUY" else mt5.ORDER_TYPE_SELL
        )

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 20250101,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            code = result.retcode if result else "None"
            comment_ret = result.comment if result else ""
            tlog.log_error(
                "MT5Connector.send_market_order",
                RuntimeError(f"order_send failed: retcode={code} | {comment_ret}"),
            )
            return None

        return {
            "order": result.order,
            "deal": result.deal,
            "retcode": result.retcode,
            "price": result.price,
            "volume": result.volume,
        }

    def close_position(self, ticket: int) -> bool:
        """
        Close a single position by ticket number.
        Returns True on success.
        """
        if not MT5_AVAILABLE or not self._connected:
            return False

        positions = mt5.positions_get()
        if positions is None:
            return False

        for p in positions:
            if p.ticket != ticket:
                continue

            close_type = (
                mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            )
            sym = mt5.symbol_info(p.symbol)
            price = sym.bid if p.type == mt5.ORDER_TYPE_BUY else sym.ask

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": p.symbol,
                "volume": p.volume,
                "type": close_type,
                "position": ticket,
                "price": price,
                "deviation": 20,
                "magic": 20250101,
                "comment": "AI-Bot close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return True
            tlog.log_error(
                "MT5Connector.close_position",
                RuntimeError(
                    f"Close failed: ticket={ticket} retcode={result.retcode if result else 'None'}"
                ),
            )
            return False

        tlog.log_error(
            "MT5Connector.close_position",
            RuntimeError(f"Position ticket={ticket} not found"),
        )
        return False
