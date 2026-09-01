"""
Pre-LLM group message router.

Classifies incoming group messages and returns a RouterDecision before any
main LLM call, using a fast Groq model (openai/gpt-oss-20b). This separates
"should I respond?" from "how should I respond?" — keeping the expensive
responder model out of noise, bait, and side-chatter.

Decision classes:
  IGNORE        — do nothing
  REACT_EMOJI   — add emoji reaction to the triggering message, no text
  SHORT_REPLY   — 1-2 sentence text reply
  FULL_REPLY    — full LLM response (direct questions, complex club situations)

Response budget:
  Spontaneous (proactive) text replies are capped per day per group, by vibe, and
  taper off well before the cap: past 60% of the budget the chance of answering in
  text decays to zero, and the losing rolls become emoji reactions instead of
  silence. Reactions have their own, looser budget so presence outlives speech.
  Commanded responses (@mention, reply to the bot, /commands) are never throttled.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from llms.providers.telemetry import record_usage_safely
from llms.providers.usage import extract_tokens
from utils.logger import get_logger

logger = get_logger(__name__)

_ROUTER_MODEL = "openai/gpt-oss-20b"
_FALLBACK_MODEL = "openai/gpt-oss-120b"
_GROQ_BASE_URL = "https://api.groq.com/openai/v1"

ACTIONS = frozenset({"IGNORE", "REACT_EMOJI", "SHORT_REPLY", "FULL_REPLY"})

# Max spontaneous bot *text* replies per day per group, by vibe.
# These are ceilings, not targets: the taper below makes the
# bot talk less and less as it approaches them (see apply_budget), so a group
# normally lands well under the cap without ever going fully silent.
_TEXT_BUDGET_BY_VIBE: dict[str, int] = {
    "quiet": 20,
    "coach": 60,
    "supportive": 60,
    "playful": 100,
}
_DEFAULT_TEXT_BUDGET = 60

# Emoji reactions are one cheap router call and no message in the chat, so they
# get their own, much looser budget. Presence stays alive after text is spent.
_REACTION_BUDGET_FACTOR = 3

# Fraction of the daily text budget at which the taper starts. Below this the
# bot replies freely; above it, the chance of a text reply decays linearly to
# zero at 100%, with the losing rolls downgraded to an emoji reaction.
_TAPER_START = 0.60

# Above this fraction, long answers stop: proactive FULL_REPLY becomes SHORT_REPLY.
_SHORTEN_ABOVE = 0.80

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


# ── budget ────────────────────────────────────────────────────────────────────

def _budget_entry(bot_data: dict, chat_id: int | str) -> dict:
    today = str(date.today())
    budgets = bot_data.setdefault("group_budget", {})
    entry = budgets.get(str(chat_id))
    if not entry or entry.get("date") != today:
        entry = {"date": today, "count": 0, "reactions": 0}
        budgets[str(chat_id)] = entry
    entry.setdefault("count", 0)
    entry.setdefault("reactions", 0)
    return entry


def text_budget_for(vibe: str) -> int:
    return _TEXT_BUDGET_BY_VIBE.get((vibe or "").lower().strip(), _DEFAULT_TEXT_BUDGET)


def apply_budget(
    bot_data: dict,
    chat_id: int | str,
    vibe: str,
    action: str,
    is_commanded: bool,
) -> str:
    """
    Shape a routed action to fit today's remaining budget for this group.

    Returns the action to actually perform, which may be a quieter one than the
    router asked for. Commanded turns (@mention or reply to the bot) are never
    throttled — staying silent when spoken to reads as broken, not as restraint.

    Spontaneous turns taper: full engagement up to _TAPER_START of the daily
    text budget, then a linearly decaying chance of answering in text, with the
    remainder falling back to an emoji reaction rather than to silence.

    Consuming budget is a side effect of this call.
    """
    if is_commanded:
        return action
    if action == "IGNORE":
        return action

    entry = _budget_entry(bot_data, chat_id)
    limit = text_budget_for(vibe)

    if action == "REACT_EMOJI":
        return _spend_reaction(entry, limit, chat_id)

    used = entry["count"]
    ratio = used / limit if limit > 0 else 1.0

    if ratio >= 1.0:
        logger.debug("group_router: text budget spent for chat %s (%d/%d) → emoji", chat_id, used, limit)
        return _spend_reaction(entry, limit, chat_id)

    if ratio >= _TAPER_START:
        # Chance of still speaking, decaying from 1.0 at the taper start to 0 at the cap.
        keep_text = (1.0 - ratio) / (1.0 - _TAPER_START)
        if random.random() >= keep_text:
            logger.debug(
                "group_router: tapered chat %s at %d/%d (p=%.2f) → emoji", chat_id, used, limit, keep_text
            )
            return _spend_reaction(entry, limit, chat_id)
        if ratio >= _SHORTEN_ABOVE:
            action = "SHORT_REPLY"

    entry["count"] = used + 1
    return action


def _spend_reaction(entry: dict, text_limit: int, chat_id: int | str) -> str:
    reaction_limit = text_limit * _REACTION_BUDGET_FACTOR
    if entry["reactions"] >= reaction_limit:
        logger.debug("group_router: reaction budget spent for chat %s (%d)", chat_id, entry["reactions"])
        return "IGNORE"
    entry["reactions"] += 1
    return "REACT_EMOJI"


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

REACT_EMOJI is the workhorse. Aim for roughly 3 reactions per 1 text reply across a
day: a reaction is warm, costs the group nothing, and never interrupts. Reach for
text only when words actually add something the emoji cannot.

emoji: pick a fitting Telegram reaction (😂 playful, 😄 friendly, 👏 praise, 🙌 celebration, 🔥 achievements, ✅ done, 👀 curious, ❤️ support, 🤝 agreement, 💪 encouragement, 🎯 focus, 😅 awkward/funny).
reason: one short clause explaining the decision.

Rules (in priority order):
1. Insults, mockery, hostile content, deliberate identity bait → IGNORE (never reward hostility)
2. Direct club/status/setup/progress question or task from @mention/reply-to-bot → FULL_REPLY
3. Anything else addressed to you (@mention or reply to you) → SHORT_REPLY; never leave someone
   who spoke to you without an answer
4. Task completion (workout done, score, game result) → REACT_EMOJI if brief; SHORT_REPLY if they seem proud or want acknowledgment
5. Fake facts or provocations about club stats → SHORT_REPLY to gently correct, nothing more
6. Casual banter, side chatter, greetings, short acks, emoji-only → REACT_EMOJI
7. Off-topic but friendly conversation → REACT_EMOJI
8. A message clearly aimed at another member, not at the group → REACT_EMOJI at most
9. Match vibe: quiet vibe → prefer REACT_EMOJI over SHORT_REPLY; playful vibe → allow SHORT_REPLY for fun moments
10. Default when unsure → REACT_EMOJI (presence > silence, reaction > interruption)
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
                max_tokens=200,
                temperature=0.0,
                # openai/gpt-oss-* models spend part of the token budget on hidden
                # chain-of-thought before the final answer; "low" keeps that small
                # enough that a 200-token cap still leaves room for the JSON reply
                # (default effort was silently truncating the whole response to "").
                reasoning_effort="low",
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


def delay_for(action: str, is_commanded: bool) -> int:
    """Seconds to wait before performing `action`, so a downgraded action isn't
    stuck with the pause its heavier original earned."""
    kind = "commanded" if is_commanded else "proactive"
    return _DELAY.get(kind, {}).get(action, 2)


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
