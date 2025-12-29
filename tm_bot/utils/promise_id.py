"""
Helpers for working with promise IDs.

Promise IDs are user-facing strings like "P11". Historically the codebase has
treated them inconsistently (sometimes case-sensitive, sometimes not). These
helpers provide a single place for normalization/comparison.
"""

from __future__ import annotations
import re


def normalize_promise_id(promise_id: str | None) -> str:
    """
    Normalize a promise id for comparisons.
    Handles: P01, p01, P-01, p-1, #P01, etc.

    - Strips surrounding whitespace
    - Removes common prefixes (#) and separators (-, _)
    - Pads single digits: P1 -> P01
    - Uppercases for case-insensitive matching
    """
    if not promise_id:
        return ""
    # Remove common prefixes and special chars
    cleaned = re.sub(r'[#\-_\s]', '', promise_id.strip())
    # Pad single digits: P1 -> P01
    match = re.match(r'^([PTpt])(\d+)$', cleaned)
    if match:
        prefix, num = match.groups()
        return f"{prefix.upper()}{int(num):02d}"
    return cleaned.upper()


def promise_ids_equal(a: str | None, b: str | None) -> bool:
    """Case-insensitive equality for promise IDs."""
    return normalize_promise_id(a) == normalize_promise_id(b)


