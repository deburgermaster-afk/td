"""
config.py - Loads all configuration from environment variables / .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _get_env(key: str, default=None, required: bool = False):
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(f"Required environment variable '{key}' is not set.")
    return value


# ── MetaTrader 5 credentials ──────────────────────────────────────────────────
MT5_LOGIN = int(_get_env("MT5_LOGIN", required=True))
MT5_PASSWORD = _get_env("MT5_PASSWORD", required=True)
MT5_SERVER = _get_env("MT5_SERVER", required=True)

# ── Anthropic / Claude ────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = _get_env("ANTHROPIC_API_KEY", required=True)
AI_MODEL = _get_env("AI_MODEL", "claude-opus-4-5")

# ── Trading universe ──────────────────────────────────────────────────────────
SYMBOLS = [s.strip() for s in _get_env("SYMBOLS", "BTCUSD,XAUUSD").split(",")]

# ── Capital & risk ────────────────────────────────────────────────────────────
INITIAL_CAPITAL = float(_get_env("INITIAL_CAPITAL", "50"))
DAILY_TARGET = float(_get_env("DAILY_TARGET", "200"))
RISK_PER_TRADE = float(_get_env("RISK_PER_TRADE", "0.03"))       # 3 %
MAX_DAILY_LOSS_PCT = float(_get_env("MAX_DAILY_LOSS_PCT", "0.20"))  # 20 %
EMERGENCY_EQUITY_FLOOR = float(_get_env("EMERGENCY_EQUITY_FLOOR", "25"))

# ── Execution ─────────────────────────────────────────────────────────────────
TRADE_INTERVAL_SECONDS = int(_get_env("TRADE_INTERVAL_SECONDS", "300"))
MAX_TRADES_PER_DAY = int(_get_env("MAX_TRADES_PER_DAY", "20"))
MAX_OPEN_POSITIONS = int(_get_env("MAX_OPEN_POSITIONS", "2"))
RR_RATIO = float(_get_env("RR_RATIO", "2.0"))

# ── Loss-streak protection ────────────────────────────────────────────────────
CONSECUTIVE_LOSS_LIMIT = int(_get_env("CONSECUTIVE_LOSS_LIMIT", "3"))
LOSS_PAUSE_SECONDS = int(_get_env("LOSS_PAUSE_SECONDS", str(30 * 60)))  # 30 min

# ── Indicator parameters ──────────────────────────────────────────────────────
EMA_FAST = int(_get_env("EMA_FAST", "9"))
EMA_SLOW = int(_get_env("EMA_SLOW", "21"))
RSI_PERIOD = int(_get_env("RSI_PERIOD", "14"))
ATR_PERIOD = int(_get_env("ATR_PERIOD", "14"))
BB_PERIOD = int(_get_env("BB_PERIOD", "20"))
BB_STD = float(_get_env("BB_STD", "2.0"))

# ── Risk calculation constants ─────────────────────────────────────────────────
# ATR multiplier used to compute stop-loss distance (1.5 × ATR)
ATR_SL_MULTIPLIER = float(_get_env("ATR_SL_MULTIPLIER", "1.5"))

# Minimum AI confidence to act on a BUY or SELL signal (0.65 = 65%)
AI_MIN_CONFIDENCE = float(_get_env("AI_MIN_CONFIDENCE", "0.65"))

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR = _get_env("LOG_DIR", "logs")
TRADE_LOG_FILE = _get_env("TRADE_LOG_FILE", "trade_log.csv")
