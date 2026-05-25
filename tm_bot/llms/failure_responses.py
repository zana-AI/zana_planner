from __future__ import annotations

import re
from typing import Optional


def classify_tool_error(result_text: str) -> Optional[str]:
    """Map known tool failure strings to semantic classes."""
    lower = (result_text or "").strip().lower()
    if not lower:
        return None
    if lower.startswith("could not parse datetime") or lower.startswith("could not parse"):
        return "time_parse_fail"
    if lower.startswith("missing required argument") or " is required" in lower:
        return "missing_arg"
    if "no promises found" in lower or ("promise" in lower and "not found" in lower):
        return "promise_not_found"
    if "must be an iso datetime" in lower:
        return "time_parse_fail"
    if lower.startswith(("error ", "error:", "failed to", "invalid ", "unsupported ")):
        return "internal_error"
    if "not found" in lower or "could not find" in lower:
        return "not_found"
    return None


def extract_quoted_value(result_text: str) -> str:
    """Best-effort extraction of the value quoted inside a tool error."""
    text = result_text or ""
    match = re.search(r"'([^']+)'", text)
    return match.group(1).strip() if match else ""


_TEMPLATES_EN = {
    "time_parse_fail": (
        "I couldn't read '{phrase}' as a time. Could you say it like "
        "'8:30 PM' or 'tomorrow at 7'?"
    ),
    "promise_not_found": (
        "I couldn't find a goal matching '{query}'. Send the goal name or ID, "
        "or tell me if you want to create a new one."
    ),
    "missing_arg": "I need one more detail: {arg_hint}.",
    "internal_error": "Something went wrong while doing that. Could you try again or rephrase?",
    "not_found": "I couldn't find what you're referring to. Could you send a name or ID?",
}

_TEMPLATES_FA = {
    "time_parse_fail": (
        "زمان «{phrase}» برام واضح نبود. می‌تونی مثلا بگی «۸:۳۰ شب» "
        "یا «فردا ساعت ۷»؟"
    ),
    "promise_not_found": (
        "هدفی با «{query}» پیدا نکردم. اسم یا آی‌دی هدف رو بفرست، "
        "یا بگو می‌خوای هدف جدید بسازم."
    ),
    "missing_arg": "یه جزئیات دیگه لازم دارم: {arg_hint}.",
    "internal_error": "موقع انجامش مشکلی پیش اومد. می‌تونی دوباره بگی یا جور دیگه‌ای توضیح بدی؟",
    "not_found": "نتونستم موردی که گفتی رو پیدا کنم. اسم یا آی‌دی رو می‌فرستی؟",
}


def render_failure_response(error_class: str, lang: str, **kwargs) -> str:
    """Render a short, user-facing failure response."""
    table = _TEMPLATES_FA if (lang or "").lower().startswith("fa") else _TEMPLATES_EN
    template = table.get(error_class) or table["internal_error"]
    fallback = table["internal_error"]
    values = {
        "phrase": kwargs.get("phrase") or kwargs.get("query") or "that",
        "query": kwargs.get("query") or kwargs.get("phrase") or "that",
        "arg_hint": kwargs.get("arg_hint") or "the missing value",
    }
    try:
        return template.format(**values)
    except Exception:
        return fallback
