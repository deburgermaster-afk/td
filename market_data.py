"""
market_data.py - Fetches OHLCV candles from MT5, computes technical indicators,
                 detects trading sessions, and flags un-tradeable conditions.
"""

from __future__ import annotations

import datetime
from typing import Optional

import numpy as np
import pandas as pd

import config

# ── Indicator computation ─────────────────────────────────────────────────────


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()


def compute_bollinger_bands(
    series: pd.Series, period: int = 20, std_dev: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (upper, middle, lower)."""
    middle = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return upper, middle, lower


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    """Cumulative VWAP for the session (resets each day)."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    df = df.copy()
    df["_typical"] = typical
    df["_tv"] = typical * df["tick_volume"]
    # Group by date so VWAP resets each session day
    df["_date"] = pd.to_datetime(df["time"]).dt.date
    df["_cum_tv"] = df.groupby("_date")["_tv"].cumsum()
    df["_cum_vol"] = df.groupby("_date")["tick_volume"].cumsum()
    return df["_cum_tv"] / df["_cum_vol"]


# ── Main enrichment function ──────────────────────────────────────────────────


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Add all indicator columns to an OHLCV dataframe returned by MT5."""
    df = df.copy()

    # EMA
    df["ema_fast"] = compute_ema(df["close"], config.EMA_FAST)
    df["ema_slow"] = compute_ema(df["close"], config.EMA_SLOW)

    # RSI
    df["rsi"] = compute_rsi(df["close"], config.RSI_PERIOD)

    # ATR
    df["atr"] = compute_atr(df["high"], df["low"], df["close"], config.ATR_PERIOD)

    # Bollinger Bands
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = compute_bollinger_bands(
        df["close"], config.BB_PERIOD, config.BB_STD
    )

    # VWAP
    df["vwap"] = compute_vwap(df)

    return df


# ── Market snapshot (last N rows as dict) ─────────────────────────────────────


def build_snapshot(df: pd.DataFrame, n: int = 20) -> list[dict]:
    """Return the last *n* enriched rows as a list of plain dicts (JSON-serialisable)."""
    tail = df.tail(n).copy()
    # Convert numpy types to native Python for JSON safety
    records = []
    for _, row in tail.iterrows():
        record = {}
        for col, val in row.items():
            if col.startswith("_"):
                continue
            if isinstance(val, (np.integer,)):
                record[col] = int(val)
            elif isinstance(val, (np.floating,)):
                record[col] = round(float(val), 6) if not np.isnan(val) else None
            elif isinstance(val, float):
                record[col] = round(val, 6) if not np.isnan(val) else None
            else:
                record[col] = val
        records.append(record)
    return records


# ── Session detection ─────────────────────────────────────────────────────────

# UTC hour ranges for major sessions
_SESSIONS = {
    "Sydney":   (21, 6),   # 21:00–06:00 UTC
    "Tokyo":    (0, 9),    # 00:00–09:00 UTC
    "London":   (8, 17),   # 08:00–17:00 UTC
    "New York": (13, 22),  # 13:00–22:00 UTC
}


def current_sessions() -> list[str]:
    """Return list of currently active major Forex/Crypto sessions (UTC)."""
    hour = datetime.datetime.utcnow().hour
    active = []
    for name, (start, end) in _SESSIONS.items():
        if start < end:
            if start <= hour < end:
                active.append(name)
        else:  # spans midnight
            if hour >= start or hour < end:
                active.append(name)
    return active if active else ["Off-hours"]


# ── Tradeability check ────────────────────────────────────────────────────────


def is_tradeable(symbol: str, df: pd.DataFrame) -> tuple[bool, str]:
    """
    Returns (True, '') if the symbol is safe to trade, otherwise
    (False, <reason string>).
    """
    if df is None or len(df) < max(config.EMA_SLOW, config.BB_PERIOD, config.ATR_PERIOD) + 5:
        return False, "Insufficient candle data"

    last = df.iloc[-1]

    # Guard against zero ATR (frozen market / data issue)
    if pd.isna(last.get("atr")) or last["atr"] == 0:
        return False, "ATR is zero – market may be frozen or data unavailable"

    return True, ""


# ── Crash / high-volatility day detection ─────────────────────────────────────


def is_crash_day(df: pd.DataFrame, atr_multiplier: float = 3.0) -> bool:
    """
    Returns True if the current ATR is more than *atr_multiplier* times the
    20-period average ATR – a rough heuristic for extreme volatility days.
    """
    if df is None or "atr" not in df.columns or len(df) < 20:
        return False
    recent_atr = df["atr"].dropna()
    if len(recent_atr) < 5:
        return False
    avg_atr = recent_atr.iloc[-20:].mean()
    current_atr = recent_atr.iloc[-1]
    return current_atr > atr_multiplier * avg_atr
