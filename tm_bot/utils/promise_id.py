"""
Helpers for working with promise IDs.

Promise IDs are user-facing strings like "P11". Historically the codebase has
treated them inconsistently (sometimes case-sensitive, sometimes not). These
helpers provide a single place for normalization/comparison.
"""

from __future__ import annotations


def normalize_promise_id(promise_id: str | None) -> str:
    """
    Normalize a promise id for comparisons.

    - Strips surrounding whitespace
    - Uppercases for case-insensitive matching
    """
    return (promise_id or "").strip().upper()


def promise_ids_equal(a: str | None, b: str | None) -> bool:
    """Case-insensitive equality for promise IDs."""
    return normalize_promise_id(a) == normalize_promise_id(b)

