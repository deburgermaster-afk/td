"""
main.py - Orchestrates the AI-powered MetaTrader 5 trading bot.

Loop:
  For each configured symbol:
    1. Fetch candles & enrich with indicators
    2. Check tradeability & risk gates
    3. Call AI brain for a decision
    4. Execute trade (BUY/SELL) or log SKIP
    5. Scan open positions for SL/TP events (already managed by MT5, but tracked here)
  Sleep TRADE_INTERVAL_SECONDS, then repeat.
"""

from __future__ import annotations

import signal
import sys
import time

import config
import market_data as md
import trade_logger as tlog
from ai_brain import AIBrain
from mt5_connector import MT5Connector
from risk_manager import RiskManager


def main() -> None:
    tlog.log_info("=== AI Trading Bot starting ===")
    tlog.log_info(f"Symbols: {config.SYMBOLS}")
    tlog.log_info(f"Interval: {config.TRADE_INTERVAL_SECONDS}s | Risk/trade: {config.RISK_PER_TRADE*100:.1f}%")

    connector = MT5Connector()
    if not connector.connect():
        tlog.log_error("main", RuntimeError("Failed to connect to MT5 – exiting"))
        sys.exit(1)

    # Seed risk manager with actual starting equity
    acct = connector.account_info()
    starting_equity = acct.get("equity", config.INITIAL_CAPITAL)
    risk_mgr = RiskManager(starting_equity)
    tlog.log_info(f"Starting equity: {starting_equity:.2f} {acct.get('currency', '')}")

    brain = AIBrain()

    # ── Graceful shutdown on SIGINT / SIGTERM ─────────────────────────────────
    shutdown = {"requested": False}

    def _on_signal(signum, frame):
        tlog.log_info("Shutdown signal received – finishing current cycle then stopping")
        shutdown["requested"] = True

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    # ── Track closed positions for PnL bookkeeping ────────────────────────────
    # Map ticket -> profit at last observation
    known_positions: dict[int, float] = {}

    # ── Main trading loop ─────────────────────────────────────────────────────
    while not shutdown["requested"]:
        try:
            acct = connector.account_info()
            if not acct:
                tlog.log_error("main loop", RuntimeError("account_info() returned empty"))
                time.sleep(config.TRADE_INTERVAL_SECONDS)
                continue

            equity = acct["equity"]
            balance = acct["balance"]

            # ── Check for newly closed positions ──────────────────────────────
            current_positions = connector.get_all_open_positions()
            current_tickets = {p["ticket"] for p in current_positions}

            for ticket, last_profit in list(known_positions.items()):
                if ticket not in current_tickets:
                    # Position was closed by SL/TP or manually
                    risk_mgr.record_trade_closed(last_profit)
                    tlog.log_close(
                        symbol="?",
                        pnl=last_profit,
                        equity=equity,
                        balance=balance,
                        notes=f"ticket={ticket} closed externally",
                    )
                    del known_positions[ticket]

            # Update known positions with current profit snapshot
            for p in current_positions:
                known_positions[p["ticket"]] = p["profit"]

            open_count = len(current_positions)

            # ── Per-symbol decision cycle ─────────────────────────────────────
            for symbol in config.SYMBOLS:
                if shutdown["requested"]:
                    break

                # Risk pre-check
                can, reason = risk_mgr.can_trade(equity, open_count)
                if not can:
                    tlog.log_skip(symbol, reason, equity, balance)
                    continue

                # Fetch & enrich candles
                df = connector.fetch_candles(symbol, count=200)
                if df is None:
                    tlog.log_skip(symbol, "Candle fetch failed", equity, balance)
                    continue

                df = md.enrich_dataframe(df)

                # Tradeability check
                tradeable, reason = md.is_tradeable(symbol, df)
                if not tradeable:
                    tlog.log_skip(symbol, reason, equity, balance)
                    continue

                # Market context
                sessions = md.current_sessions()
                crash_day = md.is_crash_day(df)

                if crash_day:
                    tlog.log_skip(symbol, "Crash/extreme-volatility day detected", equity, balance)
                    continue

                # Build snapshot for AI
                snapshot = md.build_snapshot(df, n=20)

                # Symbol contract specs
                sym_info = connector.symbol_info(symbol)

                # Position status for this symbol
                sym_positions = connector.get_open_positions(symbol)

                # Risk context dict for AI
                risk_ctx = risk_mgr.risk_context()

                # AI decision
                decision = brain.get_decision(
                    symbol=symbol,
                    snapshot=snapshot,
                    account_info=acct,
                    positions=sym_positions,
                    risk_ctx=risk_ctx,
                    sessions=sessions,
                    crash_day=crash_day,
                )

                action = decision["action"]
                confidence = decision["confidence"]
                reasoning = decision["reasoning"]

                if action == "SKIP":
                    tlog.log_skip(symbol, f"AI SKIP (conf={confidence:.0%}): {reasoning}", equity, balance)
                    continue

                # ── Compute SL/TP and lot size ────────────────────────────────
                last_atr = float(df["atr"].iloc[-1])
                entry_price = (
                    sym_info.get("ask") if action == "BUY" else sym_info.get("bid")
                )
                if not entry_price:
                    tlog.log_skip(symbol, "Could not get entry price from symbol info", equity, balance)
                    continue

                sl, tp = risk_mgr.compute_sl_tp(action, entry_price, last_atr)
                lot = risk_mgr.compute_lot_size(equity, last_atr, sym_info)

                # ── Place order ───────────────────────────────────────────────
                result = connector.send_market_order(
                    symbol=symbol,
                    action=action,
                    lot_size=lot,
                    sl=sl,
                    tp=tp,
                    comment=f"AI conf={confidence:.2f}",
                )

                if result:
                    risk_mgr.record_trade_opened()
                    open_count += 1
                    ticket = result.get("order", 0)
                    known_positions[ticket] = 0.0  # profit unknown until next cycle

                    tlog.log_trade(
                        symbol=symbol,
                        action=action,
                        lot_size=lot,
                        entry_price=result.get("price", entry_price),
                        sl=sl,
                        tp=tp,
                        confidence=confidence,
                        reasoning=reasoning,
                        equity=equity,
                        balance=balance,
                    )
                else:
                    tlog.log_skip(
                        symbol,
                        f"Order placement failed (AI: {action} conf={confidence:.0%})",
                        equity,
                        balance,
                    )

        except Exception as exc:
            tlog.log_error("main loop", exc)

        if not shutdown["requested"]:
            tlog.log_info(f"Cycle complete – sleeping {config.TRADE_INTERVAL_SECONDS}s")
            time.sleep(config.TRADE_INTERVAL_SECONDS)

    # ── Shutdown ──────────────────────────────────────────────────────────────
    connector.disconnect()
    tlog.log_info("=== AI Trading Bot stopped ===")


if __name__ == "__main__":
    main()
