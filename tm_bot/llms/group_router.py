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
import time
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from llms.providers.telemetry import record_usage_safely
from llms.providers.usage import extract_tokens
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
- IGNORE: truly ignore — no reaction, no text (hostile content, insults, mockery, deliberate bait, repeated provocations)
- REACT_EMOJI: add a single emoji reaction, no text (casual banter, side chatter, social moments, greetings, short acks — show presence without intruding)
- SHORT_REPLY: 1-2 sentence text reply (simple questions, mild engagement, task completions worth a comment)
- FULL_REPLY: full thoughtful response (club/status/setup/progress questions, complex situations, check-in info needed)

emoji: pick a fitting Telegram reaction (😂 playful, 😄 friendly, 👏 praise, 🙌 celebration, 🔥 achievements, ✅ done, 👀 curious, ❤️ support, 🤝 agreement, 💪 encouragement, 🎯 focus, 😅 awkward/funny).
reason: one short clause explaining the decision.

Rules (in priority order):
1. Insults, mockery, hostile content, deliberate identity bait → IGNORE (never reward hostility)
2. Direct club/status/setup/progress question or task from @mention/reply-to-bot → FULL_REPLY
3. Task completion (workout done, score, game result) → REACT_EMOJI if brief; SHORT_REPLY if they seem proud or want acknowledgment
4. Fake facts or provocations about club stats → SHORT_REPLY to gently correct, nothing more
5. Casual banter, side chatter, greetings, short acks, emoji-only → REACT_EMOJI or SHORT_REPLY (show presence without interrupting)
6. Off-topic but friendly conversation → REACT_EMOJI
7. Match vibe: quiet vibe → prefer REACT_EMOJI over SHORT_REPLY; playful vibe → allow SHORT_REPLY for fun moments
8. Default when unsure → REACT_EMOJI (presence > silence)
"""

_USER_TEMPLATE = """Club vibe: {vibe}
Bot was @mentioned: {mentioned}
Message replied to Xaana: {reply_to_bot}
Conversation state: {conversation_state}

Recent conversation (last 4 compact messages):
{transcript}

Current message from {sender}:
{message}"""

_ACK_RE = re.compile(
    r"^(ok|okay|k|yes|no|yep|nope|thanks|thank you|agreed|agree|cool|nice|"
    r"\u0628\u0627\u0634\u0647|\u0627\u0648\u06a9\u06cc|\u0645\u0631\u0633\u06cc|"
    r"\u0645\u0645\u0646\u0648\u0646|\u0622\u0631\u0647|\u0627\u0631\u0647|"
    r"\u0646\u0647|\u062e\u0648\u0628\u0647|\u0639\u0627\u0644\u06cc\u0647|"
    r"\u0645\u0648\u0627\u0641\u0642\u0645|\u0627\u06cc\u0648\u0644)$",
    re.IGNORECASE,
)

_STATUS_RE = re.compile(
    r"\b(who checked|who check(?:ed)? in|how many checked|check-?in status|status)\b",
    re.IGNORECASE,
)


# ── main entry point ───────────────────────────────────────────────────────────

def route_group_message(
    message: str,
    sender: str,
    vibe: str,
    is_mentioned: bool,
    sender_checked_in: bool,
    recent_messages: List[dict],
    conversation_state: Optional[str] = None,
    reply_to_bot: bool = False,
    groq_api_key: Optional[str] = None,
) -> RouterDecision:
    """
    Call the Groq router and return a RouterDecision.
    Falls back to simple heuristics if Groq is unavailable or fails.
    """
    pre_decision = _pre_route(message, is_mentioned=is_mentioned, reply_to_bot=reply_to_bot)
    if pre_decision is not None:
        return pre_decision

    api_key = groq_api_key or os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return _heuristic(message, is_mentioned)

    transcript = _fmt_transcript(recent_messages)
    user_content = _USER_TEMPLATE.format(
        vibe=vibe or "coach",
        mentioned="yes" if is_mentioned else "no",
        reply_to_bot="yes" if reply_to_bot else "no",
        conversation_state=(conversation_state or "unknown"),
        transcript=transcript,
        sender=sender or "Member",
        message=(message or "").strip() or "(empty)",
    )

    for model in (_ROUTER_MODEL, _FALLBACK_MODEL):
        start = time.perf_counter()
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
            latency_ms = int((time.perf_counter() - start) * 1000)
            input_tokens, output_tokens = extract_tokens(resp)
            record_usage_safely(
                provider="groq",
                model_name=model,
                role="group_router",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                success=True,
                error_type=None,
            )
            return _parse(raw, is_mentioned)
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            record_usage_safely(
                provider="groq",
                model_name=model,
                role="group_router",
                input_tokens=0,
                output_tokens=0,
                latency_ms=latency_ms,
                success=False,
                error_type=type(exc).__name__,
            )
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


def _decision(action: str, reason: str, is_mentioned: bool, emoji: str = "👍") -> RouterDecision:
    kind = "commanded" if is_mentioned else "proactive"
    delay = _DELAY.get(kind, {}).get(action, 2)
    return RouterDecision(action=action, emoji=emoji, delay_seconds=delay, reason=reason)


def _message_without_mentions(message: str) -> str:
    return re.sub(r"@\w+", "", message or "").strip()


def _is_emoji_only(message: str) -> bool:
    cleaned = _message_without_mentions(message)
    if not cleaned:
        return False
    without_letters = re.sub(r"[\w\u0600-\u06ff]+", "", cleaned, flags=re.UNICODE).strip()
    without_punctuation = re.sub(r"[\s.,!?؟،؛:;_\-~]+", "", without_letters)
    return bool(without_punctuation) and len(cleaned) <= 24


def _is_short_ack(message: str) -> bool:
    cleaned = _message_without_mentions(message).strip(" \t\r\n.,!?؟،؛:;-_")
    return bool(cleaned) and len(cleaned) <= 24 and bool(_ACK_RE.match(cleaned))


def _is_direct_status_question(message: str) -> bool:
    cleaned = _message_without_mentions(message)
    return bool(cleaned) and bool(_STATUS_RE.search(cleaned))


def _pre_route(message: str, is_mentioned: bool, reply_to_bot: bool = False) -> Optional[RouterDecision]:
    cleaned = _message_without_mentions(message)
    if not cleaned:
        if is_mentioned or reply_to_bot:
            return _decision("REACT_EMOJI", "address-only", is_mentioned, "👀")
        return _decision("IGNORE", "empty", is_mentioned, "👍")
    tiny_cleaned = cleaned.strip(" \t\r\n.,!?:;-_")
    if len(tiny_cleaned) <= 1:
        if is_mentioned or reply_to_bot:
            return _decision("REACT_EMOJI", "tiny ping", is_mentioned, "👀")
        return _decision("IGNORE", "one-character noise", is_mentioned, "👍")
    if (is_mentioned or reply_to_bot) and _is_direct_status_question(cleaned):
        return _decision("FULL_REPLY", "direct club/status question", is_mentioned, "🎯")
    if _is_emoji_only(cleaned):
        return _decision("REACT_EMOJI", "emoji-only", is_mentioned, "😂")
    if _is_short_ack(cleaned):
        return _decision("REACT_EMOJI", "short acknowledgement", is_mentioned, "👍")
    return None


def _heuristic(message: str, is_mentioned: bool) -> RouterDecision:
    """Minimal fallback when Groq is unavailable."""
    if not is_mentioned:
        return RouterDecision(action="IGNORE", delay_seconds=0, reason="no mention, no Groq")
    if not (message or "").strip():
        return RouterDecision(action="IGNORE", delay_seconds=0, reason="empty")
    return RouterDecision(action="FULL_REPLY", delay_seconds=2, reason="mentioned, heuristic")


def _fmt_transcript(recent_messages: List[dict]) -> str:
    lines = []
    for m in (recent_messages or [])[-4:]:
        sender = str(m.get("sender_name") or "?")[:30]
        text = str(m.get("text") or "")[:120]
        if text:
            reply_to = str(m.get("reply_to_sender_name") or "").strip()
            prefix = f"{sender} reply to {reply_to}: " if reply_to else f"{sender}: "
            lines.append(f"{prefix}{text}")
    return "\n".join(lines) or "(no recent messages)"
