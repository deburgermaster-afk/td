# TD – MetaTrader 5 AI Trading Bot

A Python-based trading bot that connects MetaTrader 5 with Claude AI (Anthropic) to analyse markets and execute trades automatically.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration (.env)](#configuration-env)
- [Running the Bot](#running-the-bot)
- [Troubleshooting](#troubleshooting)
- [Safety Notes](#safety-notes)

---

## Prerequisites

Before you begin, make sure you have:

- **MetaTrader 5** installed and a live/demo account with a broker
- **Python 3.9+** installed (`python --version` to check)
- An **Anthropic API key** – sign up at <https://console.anthropic.com> and copy your key (`sk-ant-...`)
- `pip` available (`pip --version` to check)

---

## Installation

1. **Open MetaTrader 5** and log in to your trading account.
2. **Clone or download this repository:**
   ```bash
   git clone https://github.com/deburgermaster-afk/td.git
   cd td
   ```
3. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Create your `.env` configuration file:**
   ```bash
   cp .env.example .env
   ```
   Then open `.env` in a text editor and fill in your credentials (see [Configuration](#configuration-env) below).

---

## Configuration (.env)

All secrets and connection details are stored in a `.env` file at the root of the project.  
**Never commit this file to version control.**

### Step-by-step guide

Copy `.env.example` to `.env`, then edit each value:

| Variable | Description | Example |
|---|---|---|
| `MT5_LOGIN` | Your MetaTrader 5 account number (provided by your broker) | `12345678` |
| `MT5_PASSWORD` | Your MetaTrader 5 account password | `MySecretPass!` |
| `MT5_SERVER` | Your broker's MT5 server name (shown in the MT5 login screen) | `BrokerName-Demo` |
| `ANTHROPIC_API_KEY` | Your Claude API key from <https://console.anthropic.com> | `sk-ant-api03-...` |
| `AI_MODEL` | *(Optional)* Claude model to use. Defaults to `claude-3-5-sonnet-20241022` | `claude-3-5-sonnet-20241022` |

### Example `.env` file

```dotenv
# MetaTrader 5 credentials
MT5_LOGIN=12345678
MT5_PASSWORD=MySecretPass!
MT5_SERVER=BrokerName-Demo

# Anthropic / Claude API
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# (Optional) Claude model – remove this line to use the default
AI_MODEL=claude-3-5-sonnet-20241022
```

> **Tip:** Your broker's server name appears on the MT5 login dialog.  
> Common formats: `ICMarkets-Demo01`, `Pepperstone-Demo`, `XM-MT5`.

---

## Running the Bot

1. **Ensure MetaTrader 5 is open and logged in** before starting the bot.
2. Activate your virtual environment (if using one):
   ```bash
   # Windows
   venv\Scripts\activate
   # macOS / Linux
   source venv/bin/activate
   ```
3. **Start the bot:**
   ```bash
   python main.py
   ```

### Expected console output (successful startup)

```
[2024-11-15 09:00:01] INFO  Connecting to MetaTrader 5...
[2024-11-15 09:00:02] INFO  Connected to MT5 account 12345678 on BrokerName-Demo
[2024-11-15 09:00:02] INFO  Initialising Claude AI (claude-3-5-sonnet-20241022)...
[2024-11-15 09:00:03] INFO  AI model ready.
[2024-11-15 09:00:03] INFO  Bot started. Monitoring markets...
```

If you see these lines the bot is running correctly. Press **Ctrl+C** to stop it gracefully.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `MT5 initialisation failed` | MT5 terminal is not open | Open MetaTrader 5 and log in first |
| `Invalid account` / `Auth error` | Wrong `MT5_LOGIN` or `MT5_PASSWORD` | Double-check credentials in `.env` |
| `Unknown server` | Wrong `MT5_SERVER` value | Copy the exact server name from the MT5 login screen |
| `AuthenticationError` from Anthropic | Invalid `ANTHROPIC_API_KEY` | Regenerate the key at <https://console.anthropic.com> |
| `ModuleNotFoundError` | Dependencies not installed | Run `pip install -r requirements.txt` |
| Bot connects but places no trades | Market closed or AI model not triggering | Check market hours; review logs for AI responses |

### Where are the logs?

- Errors and info messages are printed to the console.
- Check the terminal output for `ERROR` or `WARNING` lines for details.

---

## Safety Notes

- **Use a demo account first** until you are confident the bot behaves as expected.
- **Never share your `.env` file** – it contains your broker password and API key.
- Add `.env` to your `.gitignore` to prevent accidental commits:
  ```
  .env
  ```
- Set **position size limits** and **stop-loss orders** in MetaTrader 5 as a safety net.
- Monitor the bot regularly; automated trading carries financial risk.
- The authors of this project are **not responsible** for any trading losses.
