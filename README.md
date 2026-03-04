# AI-Powered Automated Trading Bot for MetaTrader 5

> **⚠️ DISCLAIMER:** This software is provided for **educational and research purposes only**.
> Automated trading involves significant financial risk. Past performance is not indicative of
> future results. **Never trade with money you cannot afford to lose.** Always test thoroughly
> on a **demo account** before considering any live deployment. The authors and contributors
> accept no liability for any financial losses arising from the use of this software.

---

## Table of Contents

1. [Overview](#overview)
2. [Folder Structure](#folder-structure)
3. [Requirements](#requirements)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Running the Bot](#running-the-bot)
7. [How It Works](#how-it-works)
8. [Safety & Risk Management](#safety--risk-management)
9. [Logging & Output](#logging--output)
10. [Example Outputs](#example-outputs)
11. [Troubleshooting](#troubleshooting)
12. [Recommendations](#recommendations)

---

## Overview

This bot connects to a live MetaTrader 5 broker account, fetches real-time OHLCV candle data,
computes a full suite of technical indicators, and packages everything into a rich market context
that is sent to **Anthropic's Claude AI** for a trading decision (BUY / SELL / SKIP).

When Claude recommends a trade, the bot:
- Computes ATR-based stop-loss and take-profit levels
- Sizes the position so that the risk never exceeds the configured percentage of equity
- Places the market order via the MT5 API
- Logs every event to CSV and a colorful console

A multi-layered risk management system runs **before** every trade to enforce daily limits,
position caps, and emergency safeguards.

---

## Folder Structure

```
td/
├── main.py              # Orchestrates the entire bot
├── mt5_connector.py     # MT5 connect, order send, candle fetch, position management
├── ai_brain.py          # Claude API integration, prompt building, response parsing
├── risk_manager.py      # Position sizing, risk rules, SL/TP, loss protection
├── market_data.py       # OHLCV enrichment, indicator computation, session/crash detection
├── trade_logger.py      # CSV and colorful console logging
├── config.py            # Reads all settings from environment variables / .env
├── .env.example         # Template – copy to .env and fill in your values
├── requirements.txt     # Python dependencies
└── README.md            # This file
```

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.10+ |
| MetaTrader 5 desktop app | Latest |
| MetaTrader5 Python package | ≥ 5.0.45 |
| Anthropic Python SDK | ≥ 0.39.0 |
| pandas | ≥ 2.0.0 |
| numpy | ≥ 1.24.0 |
| python-dotenv | ≥ 1.0.0 |
| colorama | ≥ 0.4.6 |

> The `MetaTrader5` Python package **only runs on Windows** (it interfaces with the MT5 desktop
> app via COM). If you are on Linux/macOS you will need a Windows VM or VPS.

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/deburgermaster-afk/td.git
cd td

# 2. Create and activate a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS (demo/testing only)

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy the example environment file
copy .env.example .env          # Windows
# cp .env.example .env          # Linux / macOS

# 5. Edit .env with your credentials (see Configuration section)
```

---

## Configuration

Open `.env` and fill in every value:

| Variable | Description | Default |
|---|---|---|
| `MT5_LOGIN` | Your MT5 account number | *required* |
| `MT5_PASSWORD` | Your MT5 account password | *required* |
| `MT5_SERVER` | Broker server name (e.g. `ICMarkets-Demo`) | *required* |
| `ANTHROPIC_API_KEY` | Your Claude API key | *required* |
| `AI_MODEL` | Claude model ID | `claude-opus-4-5` |
| `SYMBOLS` | Comma-separated symbols | `BTCUSD,XAUUSD` |
| `INITIAL_CAPITAL` | Starting capital (USD) | `50` |
| `DAILY_TARGET` | Daily profit target (informational) | `200` |
| `RISK_PER_TRADE` | Fraction of equity risked per trade | `0.03` |
| `MAX_DAILY_LOSS_PCT` | Max daily loss before bot halts | `0.20` |
| `EMERGENCY_EQUITY_FLOOR` | Bot halts if equity drops below this | `25` |
| `TRADE_INTERVAL_SECONDS` | Pause between trading cycles | `300` |
| `MAX_TRADES_PER_DAY` | Hard cap on daily trades | `20` |
| `MAX_OPEN_POSITIONS` | Max simultaneous open positions | `2` |
| `RR_RATIO` | Risk-to-reward ratio for TP | `2.0` |
| `CONSECUTIVE_LOSS_LIMIT` | Losses in a row before cooling-off | `3` |
| `LOSS_PAUSE_SECONDS` | Duration of cooling-off period | `1800` |
| `LOG_DIR` | Directory for log files | `logs` |
| `TRADE_LOG_FILE` | Name of CSV trade log | `trade_log.csv` |

---

## Running the Bot

```bash
python main.py
```

Stop it cleanly with **Ctrl+C** (SIGINT) — the bot will finish its current cycle then shut down
gracefully.

---

## How It Works

### 1. Market Data (`market_data.py`)
- Fetches the last 200 five-minute candles from MT5 for each configured symbol.
- Computes:
  - **EMA 9 & 21** (trend direction)
  - **RSI 14** (momentum / overbought/oversold)
  - **ATR 14** (volatility; used for SL/TP sizing)
  - **Bollinger Bands 20,2** (price range / squeeze)
  - **VWAP** (session fair value; resets each day)
- Detects active sessions (Sydney, Tokyo, London, New York).
- Flags crash/extreme-volatility days when the current ATR is > 3× its 20-period average.

### 2. AI Decision (`ai_brain.py`)
- Packages the last 20 enriched candles, account info, open positions, and risk context
  into a structured JSON prompt.
- Sends the prompt to **Claude** with a strict system instruction to respond with JSON only:
  ```json
  {
    "action": "BUY",
    "confidence": 0.78,
    "sl_pips": 45.0,
    "tp_pips": 90.0,
    "reasoning": "EMA crossover with RSI turning up from 42..."
  }
  ```
- Validates and parses the response; forces SKIP if confidence < 0.65.

### 3. Risk Manager (`risk_manager.py`)
- Runs a pre-trade gate check covering:
  - Emergency equity floor
  - Daily loss limit
  - Max open positions
  - Max trades per day
  - Cooling-off period
- Computes **ATR-based SL/TP** and **risk-based lot size** independently of the AI hint.

### 4. MT5 Connector (`mt5_connector.py`)
- Manages the MT5 session (login/logout).
- Places market orders with deviation protection (20 points).
- Tracks open positions; detects externally closed positions (SL/TP hit) for PnL bookkeeping.

---

## Safety & Risk Management

| Safeguard | Behaviour |
|---|---|
| **Max 3% risk per trade** | Lot size is calculated so a 1.5×ATR adverse move costs ≤ 3% of equity |
| **Max 2 open positions** | Bot skips new trades when 2 positions are already open |
| **Daily loss limit (20%)** | Bot halts all trading for the rest of the day |
| **Emergency equity floor ($25)** | Bot halts immediately if equity drops below this |
| **3 consecutive losses → 30-min pause** | Cooling-off period before the next trade attempt |
| **Max 20 trades/day** | Hard cap regardless of strategy signals |
| **Crash day detection** | Bot skips trading when ATR spikes to 3× its average |
| **AI confidence threshold** | BUY/SELL only actioned when Claude confidence ≥ 65% |
| **Graceful error handling** | Every error is caught, logged, and the bot continues |

---

## Logging & Output

All events are written to:
- **`logs/trade_log.csv`** – structured CSV with timestamp, event type, symbol, action, prices,
  PnL, equity, and reasoning.
- **Console** – colour-coded output:
  - 🟢 Green – BUY trades and profitable closes
  - 🔴 Red – SELL trades, losses, and errors
  - 🟡 Yellow – SKIP decisions
  - 🟣 Magenta – Risk events
  - 🔵 Cyan – Informational messages

---

## Example Outputs

### BUY trade placed
```
[2025-01-15 09:32:11] [TRADE] BTCUSD BUY | lot=0.02 | entry=97450.12500 | SL=96980.50000 | TP=98389.74000 | conf=78% | EMA crossover confirmed, RSI=44 rising
```

### SKIP – AI not confident
```
[2025-01-15 09:32:15] [SKIP] XAUUSD | AI SKIP (conf=52%): Mixed signals – BB squeeze but RSI overbought at 71
```

### Risk event – daily loss limit
```
[2025-01-15 14:05:02] [RISK] DAILY_LOSS_LIMIT | Daily PnL -10.20 <= -10.00
```

### Position closed by SL (detected next cycle)
```
[2025-01-15 09:47:11] [CLOSE] ? | PnL=-1.45 | ticket=123456 closed externally
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `MT5_LOGIN` / `MT5_PASSWORD` errors | Verify credentials in `.env`; ensure the MT5 desktop app is running and logged in |
| `MetaTrader5 package not installed` | Run `pip install MetaTrader5`; note: Windows only |
| `symbol_info() returned None` | Symbol name may differ by broker (e.g. `XAUUSD` vs `GOLD`). Check the Market Watch in MT5. |
| `Anthropic API error` | Verify `ANTHROPIC_API_KEY`; check your Anthropic account has credits |
| `Insufficient candle data` | Symbol may be outside trading hours or the broker doesn't offer it |
| Bot places no trades | Check if risk gates are blocking (daily loss, positions, cooling-off); review logs |
| Lot size is always minimum | ATR-based sizing may result in tiny lots on low-leverage accounts; acceptable behaviour |

---

## Recommendations

1. **Always start on a demo account.** Run for at least 2–4 weeks before considering live trading.
2. **Monitor the first few cycles manually** to confirm orders appear correctly in MT5.
3. **Review `logs/trade_log.csv`** regularly to understand the bot's decision patterns.
4. **Adjust `RISK_PER_TRADE`** down (e.g. `0.01`) for a more conservative initial run.
5. **Never disable the emergency floor or daily loss limit.**
6. **Keep your Anthropic API key secure** – never commit `.env` to version control.
7. **Use a VPS** (Windows) for 24/7 operation to avoid missing sessions.
8. **Keep MT5 running** – the bot requires the desktop application to be open and connected.
