"""
trade_logger.py - CSV and colorful console logging for all trade events.
"""

import csv
import os
import sys
from datetime import datetime

from colorama import Fore, Style, init as colorama_init

import config

colorama_init(autoreset=True)

# ── Ensure log directory exists ───────────────────────────────────────────────
os.makedirs(config.LOG_DIR, exist_ok=True)

LOG_PATH = os.path.join(config.LOG_DIR, config.TRADE_LOG_FILE)

CSV_HEADERS = [
    "timestamp",
    "event",
    "symbol",
    "action",
    "lot_size",
    "entry_price",
    "sl",
    "tp",
    "confidence",
    "reasoning",
    "pnl",
    "equity",
    "balance",
    "notes",
]

# Initialise CSV with header row if it does not already exist
if not os.path.exists(LOG_PATH):
    with open(LOG_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _write_csv(row: dict) -> None:
    row.setdefault("timestamp", _ts())
    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writerow(row)


def _console(color: str, tag: str, msg: str) -> None:
    ts = _ts()
    print(f"{color}[{ts}] [{tag}]{Style.RESET_ALL} {msg}", flush=True)


# ── Public API ────────────────────────────────────────────────────────────────

def log_trade(
    symbol: str,
    action: str,
    lot_size: float,
    entry_price: float,
    sl: float,
    tp: float,
    confidence: float,
    reasoning: str,
    equity: float,
    balance: float,
) -> None:
    """Log a trade execution to CSV and console."""
    msg = (
        f"{symbol} {action.upper()} | lot={lot_size} | entry={entry_price:.5f} "
        f"| SL={sl:.5f} | TP={tp:.5f} | conf={confidence:.0%} | {reasoning}"
    )
    color = Fore.GREEN if action.upper() == "BUY" else Fore.RED
    _console(color, "TRADE", msg)
    _write_csv(
        {
            "event": "TRADE",
            "symbol": symbol,
            "action": action.upper(),
            "lot_size": lot_size,
            "entry_price": entry_price,
            "sl": sl,
            "tp": tp,
            "confidence": confidence,
            "reasoning": reasoning,
            "equity": equity,
            "balance": balance,
        }
    )


def log_skip(symbol: str, reason: str, equity: float, balance: float) -> None:
    """Log a SKIP decision."""
    _console(Fore.YELLOW, "SKIP", f"{symbol} | {reason}")
    _write_csv(
        {
            "event": "SKIP",
            "symbol": symbol,
            "action": "SKIP",
            "reasoning": reason,
            "equity": equity,
            "balance": balance,
        }
    )


def log_close(symbol: str, pnl: float, equity: float, balance: float, notes: str = "") -> None:
    """Log a position close event."""
    color = Fore.GREEN if pnl >= 0 else Fore.RED
    _console(color, "CLOSE", f"{symbol} | PnL={pnl:.2f} | {notes}")
    _write_csv(
        {
            "event": "CLOSE",
            "symbol": symbol,
            "action": "CLOSE",
            "pnl": pnl,
            "equity": equity,
            "balance": balance,
            "notes": notes,
        }
    )


def log_risk_event(event: str, detail: str, equity: float = 0.0) -> None:
    """Log a risk-management event (daily loss hit, emergency floor, etc.)."""
    _console(Fore.MAGENTA, "RISK", f"{event} | {detail}")
    _write_csv(
        {
            "event": event,
            "action": "RISK",
            "reasoning": detail,
            "equity": equity,
        }
    )


def log_error(context: str, error: Exception) -> None:
    """Log an unexpected error without crashing."""
    msg = f"{context} | {type(error).__name__}: {error}"
    _console(Fore.RED + Style.BRIGHT, "ERROR", msg)
    _write_csv({"event": "ERROR", "notes": msg})


def log_info(msg: str) -> None:
    """Log a general informational message."""
    _console(Fore.CYAN, "INFO", msg)
    _write_csv({"event": "INFO", "notes": msg})
