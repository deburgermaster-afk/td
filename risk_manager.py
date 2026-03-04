"""
risk_manager.py - Position sizing, risk rules enforcement, SL/TP computation,
                  daily loss tracking, and consecutive-loss protection.
"""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Optional

import config


class RiskManager:
    """
    Tracks all risk-related state for the trading session and exposes
    guard-rail methods used by main.py before every trade decision.
    """

    def __init__(self, starting_equity: float) -> None:
        self.starting_equity: float = starting_equity

        # Daily tracking (reset each new calendar day)
        self._day: date = datetime.utcnow().date()
        self.trades_today: int = 0
        self.daily_pnl: float = 0.0

        # Loss-streak tracking
        self.consecutive_losses: int = 0
        self._pause_until: float = 0.0  # epoch seconds

    # ── Daily reset ───────────────────────────────────────────────────────────

    def _maybe_reset_day(self) -> None:
        today = datetime.utcnow().date()
        if today != self._day:
            self._day = today
            self.trades_today = 0
            self.daily_pnl = 0.0
            self.consecutive_losses = 0
            self._pause_until = 0.0

    # ── Pre-trade checks ──────────────────────────────────────────────────────

    def can_trade(self, equity: float, open_positions: int) -> tuple[bool, str]:
        """
        Returns (True, '') if a new trade is allowed, or (False, <reason>).
        Checks are performed in priority order.
        """
        self._maybe_reset_day()

        # 1. Emergency equity floor
        if equity < config.EMERGENCY_EQUITY_FLOOR:
            return False, (
                f"Emergency floor hit: equity {equity:.2f} < "
                f"{config.EMERGENCY_EQUITY_FLOOR:.2f}"
            )

        # 2. Daily loss limit
        max_daily_loss = self.starting_equity * config.MAX_DAILY_LOSS_PCT
        if self.daily_pnl <= -max_daily_loss:
            return False, (
                f"Daily loss limit hit: daily PnL {self.daily_pnl:.2f} <= "
                f"-{max_daily_loss:.2f}"
            )

        # 3. Maximum open positions
        if open_positions >= config.MAX_OPEN_POSITIONS:
            return False, (
                f"Max open positions reached ({open_positions}/{config.MAX_OPEN_POSITIONS})"
            )

        # 4. Max trades per day
        if self.trades_today >= config.MAX_TRADES_PER_DAY:
            return False, (
                f"Max trades per day reached ({self.trades_today}/{config.MAX_TRADES_PER_DAY})"
            )

        # 5. Consecutive-loss pause
        if time.time() < self._pause_until:
            remaining = int(self._pause_until - time.time())
            return False, (
                f"Cooling-off period active after {config.CONSECUTIVE_LOSS_LIMIT} "
                f"consecutive losses – {remaining}s remaining"
            )

        return True, ""

    # ── Position sizing ───────────────────────────────────────────────────────

    def compute_lot_size(
        self,
        equity: float,
        atr: float,
        symbol_info: dict,
    ) -> float:
        """
        Risk-based lot size calculation.

        risk_amount = equity * RISK_PER_TRADE
        SL distance  = 1.5 × ATR  (in price units)
        lot_size     = risk_amount / (sl_distance × tick_value_per_lot)

        Returns the lot size rounded to the symbol's volume_step, clamped
        between volume_min and volume_max.
        """
        risk_amount = equity * config.RISK_PER_TRADE
        sl_distance = config.ATR_SL_MULTIPLIER * atr  # price units

        tick_value = symbol_info.get("trade_tick_value", 1.0)
        tick_size = symbol_info.get("trade_tick_size", 0.00001)
        if tick_size == 0:
            tick_size = 0.00001

        # Value of 1 lot moving by sl_distance
        value_per_lot = (sl_distance / tick_size) * tick_value
        if value_per_lot <= 0:
            return symbol_info.get("volume_min", 0.01)

        lot = risk_amount / value_per_lot

        # Clamp and round to step
        vol_min = symbol_info.get("volume_min", 0.01)
        vol_max = symbol_info.get("volume_max", 100.0)
        vol_step = symbol_info.get("volume_step", 0.01)

        if vol_step > 0:
            lot = round(lot / vol_step) * vol_step
        lot = max(vol_min, min(vol_max, lot))

        return round(lot, 8)

    # ── SL / TP computation ───────────────────────────────────────────────────

    def compute_sl_tp(
        self,
        action: str,
        entry: float,
        atr: float,
        rr_ratio: float = None,
    ) -> tuple[float, float]:
        """
        Returns (stop_loss, take_profit) prices.
        SL = 1.5 × ATR from entry; TP = SL distance × rr_ratio.
        """
        if rr_ratio is None:
            rr_ratio = config.RR_RATIO

        sl_distance = config.ATR_SL_MULTIPLIER * atr
        tp_distance = sl_distance * rr_ratio

        if action.upper() == "BUY":
            sl = entry - sl_distance
            tp = entry + tp_distance
        else:  # SELL
            sl = entry + sl_distance
            tp = entry - tp_distance

        return round(sl, 6), round(tp, 6)

    # ── Post-trade bookkeeping ────────────────────────────────────────────────

    def record_trade_opened(self) -> None:
        self._maybe_reset_day()
        self.trades_today += 1

    def record_trade_closed(self, pnl: float) -> None:
        self._maybe_reset_day()
        self.daily_pnl += pnl

        if pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= config.CONSECUTIVE_LOSS_LIMIT:
                self._pause_until = time.time() + config.LOSS_PAUSE_SECONDS
        else:
            self.consecutive_losses = 0

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def in_pause(self) -> bool:
        return time.time() < self._pause_until

    @property
    def pause_remaining(self) -> int:
        return max(0, int(self._pause_until - time.time()))

    def daily_loss_remaining(self) -> float:
        """How much more loss is tolerable today before the daily limit is hit."""
        max_loss = self.starting_equity * config.MAX_DAILY_LOSS_PCT
        return max(0.0, max_loss + self.daily_pnl)  # daily_pnl is negative when losing

    def risk_context(self) -> dict:
        """Return a serialisable dict summarising current risk state."""
        self._maybe_reset_day()
        return {
            "trades_today": self.trades_today,
            "max_trades_per_day": config.MAX_TRADES_PER_DAY,
            "daily_pnl": round(self.daily_pnl, 2),
            "daily_loss_limit": round(self.starting_equity * config.MAX_DAILY_LOSS_PCT, 2),
            "consecutive_losses": self.consecutive_losses,
            "in_pause": self.in_pause,
            "pause_remaining_s": self.pause_remaining,
            "risk_per_trade_pct": config.RISK_PER_TRADE * 100,
            "max_open_positions": config.MAX_OPEN_POSITIONS,
            "emergency_floor": config.EMERGENCY_EQUITY_FLOOR,
        }
