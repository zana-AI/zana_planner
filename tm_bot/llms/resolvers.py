"""LLM-based argument resolvers for planner tools.

Each resolver returns a JSON string with a ``confidence`` field that the
executor reads to decide whether to proceed or trigger a clarification turn:

  {"resolved": "<value>", "confidence": "high"}
  {"resolved": null, "confidence": "low", "candidates": [...], "clarification": "..."}
  {"resolved": null, "confidence": "none", "clarification": "..."}
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Datetime resolver
# ---------------------------------------------------------------------------

_DT_SYSTEM = "You are a datetime resolver. Return ONLY valid JSON. No explanation."

_DT_USER_TEMPLATE = """\
Now: {now_str} ({tz}).

Convert the date/time expression to ISO 8601. Return ONLY valid JSON.

Rules:
- Prefer the near future.
- "Weekend" / "آخر هفته" / "fin de semaine" = coming {saturday_label}.
- "Morning" = 09:00, "Evening" / "tonight" = 19:00, "Night" = 21:00.
- If only a date is given with no time, default to 09:00 for future dates.
- If confident → return resolved ISO string.
- If 2-3 equally plausible options → return candidates + a short clarification question.
- If genuinely ambiguous or meaningless → clarification question only.

Examples (today is {now_str}):

Input: "tomorrow"
Output: {{"resolved": "{tomorrow_9am}", "confidence": "high"}}

Input: "tomorrow at 7pm"
Output: {{"resolved": "{tomorrow_7pm}", "confidence": "high"}}

Input: "this weekend"
Output: {{"resolved": "{saturday_9am}", "confidence": "high"}}

Input: "آخر هفته"
Output: {{"resolved": "{saturday_9am}", "confidence": "high"}}

Input: "demain soir"
Output: {{"resolved": "{tomorrow_7pm}", "confidence": "high"}}

Input: "in 3 days"
Output: {{"resolved": "{in_3_days_9am}", "confidence": "high"}}

Input: "tonight"
Output: {{"resolved": "{today_7pm}", "confidence": "high"}}

Input: "morning"
Output: {{"resolved": null, "confidence": "low", "candidates": ["{tomorrow_9am}", "{day_after_9am}"], "clarification": "Which morning — tomorrow or the day after?"}}

Input: "sometime next week"
Output: {{"resolved": null, "confidence": "low", "candidates": ["{next_monday_9am}", "{next_wednesday_9am}", "{next_friday_9am}"], "clarification": "Which day next week works for you?"}}

Input: "asap"
Output: {{"resolved": null, "confidence": "none", "clarification": "When exactly? (e.g. 'in 1 hour', 'tonight at 8 pm', 'tomorrow morning')"}}

Input: "someday"
Output: {{"resolved": null, "confidence": "none", "clarification": "When would you like this? Please give a specific time or day."}}

Input: "{datetime_text}"
Output:"""


def _fmt(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _next_weekday(base: datetime, weekday: int) -> datetime:
    """Return the next occurrence of ``weekday`` (0=Mon … 6=Sun) after ``base``."""
    days_ahead = (weekday - base.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return (base + timedelta(days=days_ahead)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )


def _coming_saturday(base: datetime) -> datetime:
    """Return coming Saturday at 09:00 (or today if today IS Saturday)."""
    days_ahead = (5 - base.weekday()) % 7  # 5 = Saturday
    target = base + timedelta(days=days_ahead)
    return target.replace(hour=9, minute=0, second=0, microsecond=0)


def _build_datetime_prompt(datetime_text: str, now_local: datetime) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) with all example slots filled."""
    tz_name = str(now_local.tzinfo or "UTC")
    now_str = now_local.strftime("%A %Y-%m-%d %H:%M %Z")
    saturday_label = "Saturday " + _coming_saturday(now_local).strftime("%b %d")

    tomorrow = (now_local + timedelta(days=1)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    day_after = (now_local + timedelta(days=2)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )

    slots = {
        "now_str": now_str,
        "tz": tz_name,
        "saturday_label": saturday_label,
        "saturday_9am": _fmt(_coming_saturday(now_local)),
        "tomorrow_7pm": _fmt(
            (now_local + timedelta(days=1)).replace(hour=19, minute=0, second=0, microsecond=0)
        ),
        "tomorrow_9am": _fmt(tomorrow),
        "day_after_9am": _fmt(day_after),
        "today_7pm": _fmt(now_local.replace(hour=19, minute=0, second=0, microsecond=0)),
        "in_3_days_9am": _fmt(
            (now_local + timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0)
        ),
        "next_monday_9am": _fmt(_next_weekday(now_local, 0)),
        "next_wednesday_9am": _fmt(_next_weekday(now_local, 2)),
        "next_friday_9am": _fmt(_next_weekday(now_local, 4)),
        "datetime_text": datetime_text,
    }
    return _DT_SYSTEM, _DT_USER_TEMPLATE.format(**slots)


def resolve_datetime_with_llm(
    model: Any,
    datetime_text: str,
    user_tz: str = "UTC",
) -> str:
    """Resolve *datetime_text* via LLM. Returns a JSON string with ``confidence``.

    Falls back to a ``confidence=none`` clarification response on any error so
    the executor always gets valid JSON it can act on.
    """
    try:
        from zoneinfo import ZoneInfo  # noqa: F811

        try:
            now_local = datetime.now(ZoneInfo(user_tz))
        except Exception:
            now_local = datetime.now(ZoneInfo("UTC"))

        system_prompt, user_prompt = _build_datetime_prompt(datetime_text, now_local)

        # Build messages compatible with both LangChain and raw OpenAI-style models.
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        except ImportError:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

        raw = model.invoke(messages)
        text = (getattr(raw, "content", None) or str(raw) or "").strip()

        # Strip markdown fences if any.
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        parsed = json.loads(text)

        # Validate: must have confidence key and resolved must be ISO-parseable when high.
        confidence = parsed.get("confidence", "none")
        if confidence == "high":
            resolved = parsed.get("resolved", "")
            datetime.fromisoformat(str(resolved))  # raises if invalid
        return json.dumps(parsed)

    except Exception as exc:
        logger.warning("resolve_datetime_with_llm failed (%s); returning clarification", exc)
        return json.dumps({
            "resolved": None,
            "confidence": "none",
            "clarification": (
                f"I couldn't figure out the date/time from '{datetime_text}'. "
                "Could you say it more specifically? (e.g. 'tomorrow at 9am', 'Friday evening')"
            ),
        })
