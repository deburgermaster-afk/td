"""
ai_brain.py - Integrates with Anthropic's Claude API to make trading decisions.

Flow:
1. Package market snapshot, indicators, account state, position status, and
   risk context into a structured prompt.
2. Send to Claude and request a JSON response.
3. Parse and validate the decision (BUY / SELL / SKIP).
"""

from __future__ import annotations

import json
import re
from typing import Optional

import anthropic

import config
import trade_logger as tlog

def _build_system_prompt() -> str:
    """Build the system prompt with the current config values."""
    return (
        "You are an expert algorithmic trading analyst for a MetaTrader 5 bot.\n\n"
        "Your job is to analyse the provided market data and return a precise JSON trading "
        "decision for the given symbol. You MUST respond with ONLY valid JSON matching this "
        "schema – no markdown, no prose, no code fences:\n\n"
        "{\n"
        '  "action": "BUY" | "SELL" | "SKIP",\n'
        '  "confidence": <float between 0.0 and 1.0>,\n'
        '  "sl_pips": <float, optional stop-loss distance hint in pips>,\n'
        '  "tp_pips": <float, optional take-profit distance hint in pips>,\n'
        '  "reasoning": "<max 200 character explanation>"\n'
        "}\n\n"
        "Rules:\n"
        f"- Only recommend BUY or SELL when confidence >= {config.AI_MIN_CONFIDENCE}.\n"
        "- Prefer SKIP when signals are mixed, data is thin, or risk is elevated.\n"
        "- Always consider the current risk context (consecutive losses, daily PnL, etc.).\n"
        "- The risk manager will enforce position sizing independently; your sl_pips/tp_pips\n"
        "  are advisory hints only.\n"
    )


class AIBrain:
    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # ── Prompt construction ───────────────────────────────────────────────────

    @staticmethod
    def _build_user_prompt(
        symbol: str,
        snapshot: list[dict],
        account_info: dict,
        positions: list[dict],
        risk_ctx: dict,
        sessions: list[str],
        crash_day: bool,
    ) -> str:
        """Assemble the full user-facing prompt from all context objects."""
        return json.dumps(
            {
                "symbol": symbol,
                "active_sessions": sessions,
                "crash_day_flag": crash_day,
                "account": account_info,
                "open_positions": positions,
                "risk_context": risk_ctx,
                "market_snapshot_last_20_candles": snapshot,
            },
            default=str,
            indent=2,
        )

    # ── Decision request ──────────────────────────────────────────────────────

    def get_decision(
        self,
        symbol: str,
        snapshot: list[dict],
        account_info: dict,
        positions: list[dict],
        risk_ctx: dict,
        sessions: list[str],
        crash_day: bool,
    ) -> dict:
        """
        Call Claude with market context and return a parsed decision dict.

        Returns a dict with keys: action, confidence, sl_pips, tp_pips, reasoning.
        Defaults to SKIP on any error.
        """
        user_prompt = self._build_user_prompt(
            symbol, snapshot, account_info, positions, risk_ctx, sessions, crash_day
        )

        try:
            message = self._client.messages.create(
                model=config.AI_MODEL,
                max_tokens=512,
                system=_build_system_prompt(),
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = message.content[0].text.strip()
            return self._parse_response(raw)

        except anthropic.APIError as exc:
            tlog.log_error("AIBrain.get_decision", exc)
            return _default_skip(f"Anthropic API error: {exc}")

        except Exception as exc:
            tlog.log_error("AIBrain.get_decision", exc)
            return _default_skip(f"Unexpected error: {exc}")

    # ── Response parsing ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_response(raw: str) -> dict:
        """
        Extract and validate the JSON decision from Claude's response text.
        Falls back to SKIP on any parse/validation failure.
        """
        # Strip markdown code fences if Claude added them despite instructions
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Attempt to locate a JSON object anywhere in the string
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    return _default_skip("JSON parse failed after extraction attempt")
            else:
                return _default_skip("No JSON object found in response")

        # Validate action
        action = str(data.get("action", "SKIP")).upper()
        if action not in {"BUY", "SELL", "SKIP"}:
            action = "SKIP"

        # Validate confidence
        try:
            confidence = float(data.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.0

        # Enforce minimum confidence threshold
        if action in {"BUY", "SELL"} and confidence < config.AI_MIN_CONFIDENCE:
            action = "SKIP"

        return {
            "action": action,
            "confidence": confidence,
            "sl_pips": _safe_float(data.get("sl_pips")),
            "tp_pips": _safe_float(data.get("tp_pips")),
            "reasoning": str(data.get("reasoning", ""))[:200],
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _default_skip(reason: str) -> dict:
    return {
        "action": "SKIP",
        "confidence": 0.0,
        "sl_pips": None,
        "tp_pips": None,
        "reasoning": reason[:200],
    }


def _safe_float(value) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
