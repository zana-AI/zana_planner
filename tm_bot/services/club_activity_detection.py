"""Generic activity-evidence detection for club group check-ins."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ActivityEvidence:
    matched: bool
    confidence: float = 0.0
    reason: str = ""


_GRID_LINE_RE = re.compile(
    r"(?:[\U0001F7E9\U0001F7E8\U0001F7E5\U0001F7E6\U0001F7E7\u2b1b\u2b1c]\s*){3,}",
    re.UNICODE,
)
_SCORE_RE = re.compile(r"(?<!\d)(?:0|[1-9]\d?)\s*/\s*(?:[1-9]\d?)(?!\d)")
_TIME_RE = re.compile(r"(?:\b\d{1,2}:\d{2}(?::\d{2})?\b|[\u23f1\u23f2\u23f0]\ufe0f?\s*\d{1,2}:\d{2})")
_EN_COMPLETION_RE = re.compile(
    r"\b(?:i|i've|i have|we|we've|we have)\s+(?:just\s+)?"
    r"(?:did|finished|completed|played|ran|walked|worked out|trained|studied|"
    r"practiced|practised|read|meditated|checked in)\b"
    r"|\b(?:done|finished|completed)\s+(?:for\s+)?today\b"
    r"|\btoday'?s\s+(?:done|complete)\b",
    re.IGNORECASE,
)
_RESULT_WORD_RE = re.compile(r"\b(?:result|score|solved|attempt|attempts|today)\b", re.IGNORECASE)
_TODAY_RE = re.compile(
    r"\b(?:today|tonight|this\s+morning|this\s+evening|just)\b"
    r"|(?:\u0627\u0645\u0631\u0648\u0632|\u0627\u0645\u0634\u0628)",
    re.IGNORECASE,
)
_NEGATION_RE = re.compile(
    r"\b(?:did\s+not|didn't|havent|haven't|not\s+done|not\s+today|skip|skipped|"
    r"couldn't|could\s+not|can't|cannot)\b"
    r"|(?:\u0646\u06a9\u0631\u062f\u0645|\u0646\u062f\u0627\u062f\u0645|\u0646\u0634\u062f|"
    r"\u0646\u0632\u062f\u0645|\u0646\u0631\u0641\u062a\u0645)",
    re.IGNORECASE,
)
_QUESTION_RE = re.compile(r"\?\s*$|\u061f\s*$|^\s*(?:who|how|did|should|can|could|what|why|when)\b", re.IGNORECASE)

_FA_COMPLETION_PHRASES = (
    "\u0627\u0646\u062c\u0627\u0645 \u062f\u0627\u062f\u0645",
    "\u0628\u0627\u0632\u06cc \u06a9\u0631\u062f\u0645",
    "\u062a\u0645\u0648\u0645 \u06a9\u0631\u062f\u0645",
    "\u062a\u0645\u0627\u0645 \u06a9\u0631\u062f\u0645",
    "\u0648\u0631\u0632\u0634 \u06a9\u0631\u062f\u0645",
    "\u062a\u0645\u0631\u06cc\u0646 \u06a9\u0631\u062f\u0645",
    "\u0686\u06a9\u200c\u0627\u06cc\u0646 \u06a9\u0631\u062f\u0645",
    "\u0686\u06a9\u0627\u06cc\u0646 \u06a9\u0631\u062f\u0645",
    "\u062e\u0648\u0646\u062f\u0645",
    "\u062f\u0648\u06cc\u062f\u0645",
)


def _context_keyword_hit(text: str, *contexts: str | None) -> bool:
    words: set[str] = set()
    for context in contexts:
        for word in re.findall(r"[\w\u0600-\u06ff]{4,}", str(context or "").lower(), flags=re.UNICODE):
            words.add(word)
    if not words:
        return False
    lowered = text.lower()
    return any(word in lowered for word in list(words)[:24])


def detect_activity_evidence(
    text: str,
    *,
    what_counts: str | None = None,
    promise_text: str | None = None,
) -> ActivityEvidence:
    """Return whether a group message is strong evidence of today's activity."""
    raw = str(text or "").strip()
    if len(raw) < 4:
        return ActivityEvidence(False, 0.0, "empty")

    lowered = raw.lower()
    grid_lines = _GRID_LINE_RE.findall(raw)
    has_grid = len(grid_lines) >= 2
    has_score = bool(_SCORE_RE.search(raw))
    has_time = bool(_TIME_RE.search(raw))
    has_completion_phrase = bool(_EN_COMPLETION_RE.search(raw)) or any(
        phrase in raw for phrase in _FA_COMPLETION_PHRASES
    )
    has_result_word = bool(_RESULT_WORD_RE.search(raw))
    has_today_marker = bool(_TODAY_RE.search(raw))
    has_context_hit = _context_keyword_hit(lowered, what_counts, promise_text)

    if _NEGATION_RE.search(lowered) and not has_grid:
        return ActivityEvidence(False, 0.0, "negated")
    if _QUESTION_RE.search(raw) and not (has_grid or (has_score and has_completion_phrase)):
        return ActivityEvidence(False, 0.0, "question")

    confidence = 0.0
    reasons: list[str] = []
    if has_grid:
        confidence += 0.75
        reasons.append("grid_result")
    if has_completion_phrase and (has_today_marker or has_score or has_grid or has_time or has_context_hit):
        confidence += 0.7
        reasons.append("completion_phrase")
    if has_score and (has_grid or has_time or has_completion_phrase or has_result_word):
        confidence += 0.35
        reasons.append("score")
    if has_time and (has_grid or has_score or has_completion_phrase):
        confidence += 0.2
        reasons.append("timer")
    if has_context_hit and (has_completion_phrase or has_score or has_grid):
        confidence += 0.1
        reasons.append("club_context")

    confidence = min(confidence, 1.0)
    if confidence >= 0.7:
        return ActivityEvidence(True, confidence, "+".join(reasons))
    return ActivityEvidence(False, confidence, "+".join(reasons) or "weak")
