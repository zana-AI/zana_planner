"""
Pre-LLM group message router.

Classifies incoming group messages and returns a RouterDecision before any
main LLM call, using a fast Groq model (llama-3.1-8b-instant). This separates
"should I respond?" from "how should I respond?" — keeping the expensive
responder model out of noise, bait, and side-chatter.

Decision classes:
  IGNORE        — do nothing
  REACT_EMOJI   — add emoji reaction to the triggering message, no text
  SHORT_REPLY   — 1-2 sentence text reply
  FULL_REPLY    — full LLM response (direct questions, complex club situations)

Response budget:
  Spontaneous (proactive) responses are capped per day per group, by vibe.
  Commanded responses (direct @mention, /commands) are always allowed.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

_ROUTER_MODEL = "llama-3.1-8b-instant"
_FALLBACK_MODEL = "llama-3.3-70b-versatile"
_GROQ_BASE_URL = "https://api.groq.com/openai/v1"

ACTIONS = frozenset({"IGNORE", "REACT_EMOJI", "SHORT_REPLY", "FULL_REPLY"})

# Max spontaneous bot replies per day per group, by vibe
_BUDGET_BY_VIBE: dict[str, int] = {
    "quiet": 2,
    "coach": 5,
    "supportive": 5,
    "playful": 10,
}
_DEFAULT_BUDGET = 5

# Delay in seconds before sending a response, by action and trigger type
_DELAY: dict[str, dict[str, int]] = {
    "commanded": {"REACT_EMOJI": 2, "SHORT_REPLY": 2, "FULL_REPLY": 2},
    "proactive":  {"REACT_EMOJI": 6, "SHORT_REPLY": 10, "FULL_REPLY": 14},
}


@dataclass
class RouterDecision:
    action: str = "FULL_REPLY"
    emoji: str = "👍"
    delay_seconds: int = 2
    reason: str = ""


# ── budget ─────────────────────────────────────────────────────────────────────

def budget_allows(
    bot_data: dict,
    chat_id: int | str,
    vibe: str,
    is_commanded: bool,
) -> bool:
    """
    Returns True if a spontaneous response is within today's budget.
    Commanded responses always pass. Consuming budget happens here (side-effect).
    """
    if is_commanded:
        return True

    today = str(date.today())
    budgets = bot_data.setdefault("group_budget", {})
    entry = budgets.get(str(chat_id), {})
    if entry.get("date") != today:
        entry = {"date": today, "count": 0}

    limit = _BUDGET_BY_VIBE.get((vibe or "").lower().strip(), _DEFAULT_BUDGET)
    if entry["count"] >= limit:
        logger.debug("group_router: budget exhausted for chat %s (count=%d limit=%d)", chat_id, entry["count"], limit)
        return False

    entry["count"] += 1
    budgets[str(chat_id)] = entry
    return True


# ── router prompt ──────────────────────────────────────────────────────────────

_SYSTEM = """You are the message router for Xaana, an AI accountability coach inside a Telegram group.

Your only job: decide how Xaana should respond to the current message.

Output EXACTLY one JSON object on one line, nothing else:
{"action": "...", "emoji": "...", "reason": "..."}

action must be one of:
- IGNORE: no response needed (side chatter, banter, off-topic, insults, mockery, repeated bait, stickers)
- REACT_EMOJI: add a single emoji reaction to the message, no text (light achievements, quick social moments)
- SHORT_REPLY: 1-2 sentence text reply (simple questions, mild engagement)
- FULL_REPLY: full thoughtful response (direct club questions, complex situations, check-in info needed)

emoji: pick an appropriate reaction for REACT_EMOJI (🔥 for achievements, 👍 for acks, ❤️ for support, 🎉 for milestones).
reason: one short clause explaining the decision.

Rules (in priority order):
1. If the bot was NOT @mentioned AND message is not a task completion result → IGNORE almost always
2. Emoji-only, sticker, short acks (ok, باشه, 😂, هاها, 👌) → IGNORE
3. Identity bait, insults, mockery, "are you a robot?" → IGNORE (or one REACT_EMOJI at most)
4. Fake facts or provocations about club stats → SHORT_REPLY to gently correct, nothing more
5. Task completion (score, game result, workout done) → REACT_EMOJI if brief; SHORT_REPLY if they seem proud
6. Direct club question from an @mention → FULL_REPLY
7. Match vibe: quiet vibe → prefer IGNORE; playful vibe → allow SHORT_REPLY for social moments
"""

_USER_TEMPLATE = """Club vibe: {vibe}
Bot was @mentioned: {mentioned}
Sender already checked in today: {sender_checked_in}

Recent conversation (last 10 messages):
{transcript}

Current message from {sender}:
{message}"""


# ── main entry point ───────────────────────────────────────────────────────────

def route_group_message(
    message: str,
    sender: str,
    vibe: str,
    is_mentioned: bool,
    sender_checked_in: bool,
    recent_messages: List[dict],
    groq_api_key: Optional[str] = None,
) -> RouterDecision:
    """
    Call the Groq router and return a RouterDecision.
    Falls back to simple heuristics if Groq is unavailable or fails.
    """
    api_key = groq_api_key or os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return _heuristic(message, is_mentioned)

    transcript = _fmt_transcript(recent_messages)
    user_content = _USER_TEMPLATE.format(
        vibe=vibe or "coach",
        mentioned="yes" if is_mentioned else "no",
        sender_checked_in="yes" if sender_checked_in else "no",
        transcript=transcript,
        sender=sender or "Member",
        message=(message or "").strip() or "(empty)",
    )

    for model in (_ROUTER_MODEL, _FALLBACK_MODEL):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=_GROQ_BASE_URL)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=100,
                temperature=0.0,
            )
            raw = (resp.choices[0].message.content or "").strip()
            return _parse(raw, is_mentioned)
        except Exception as exc:
            logger.warning("group_router: %s failed: %s", model, exc)

    return _heuristic(message, is_mentioned)


# ── helpers ────────────────────────────────────────────────────────────────────

def _parse(raw: str, is_mentioned: bool) -> RouterDecision:
    try:
        text = re.sub(r"```(?:json)?|```", "", raw).strip()
        # Take only the first JSON object if model outputs extra text
        m = re.search(r"\{.*?\}", text, re.DOTALL)
        if not m:
            raise ValueError("no JSON found")
        data = json.loads(m.group())
        action = str(data.get("action", "FULL_REPLY")).upper()
        if action not in ACTIONS:
            action = "FULL_REPLY"
        emoji = (str(data.get("emoji") or "👍"))[:2]
        reason = str(data.get("reason") or "")
        kind = "commanded" if is_mentioned else "proactive"
        delay = _DELAY.get(kind, {}).get(action, 2)
        return RouterDecision(action=action, emoji=emoji, delay_seconds=delay, reason=reason)
    except Exception as exc:
        logger.debug("group_router: parse failed on %r: %s", raw[:80], exc)
        return _heuristic("", is_mentioned)


def _heuristic(message: str, is_mentioned: bool) -> RouterDecision:
    """Minimal fallback when Groq is unavailable."""
    if not is_mentioned:
        return RouterDecision(action="IGNORE", delay_seconds=0, reason="no mention, no Groq")
    if not (message or "").strip():
        return RouterDecision(action="IGNORE", delay_seconds=0, reason="empty")
    return RouterDecision(action="FULL_REPLY", delay_seconds=2, reason="mentioned, heuristic")


def _fmt_transcript(recent_messages: List[dict]) -> str:
    lines = []
    for m in (recent_messages or [])[-10:]:
        sender = str(m.get("sender_name") or "?")[:30]
        text = str(m.get("text") or "")[:150]
        if text:
            lines.append(f"{sender}: {text}")
    return "\n".join(lines) or "(no recent messages)"
