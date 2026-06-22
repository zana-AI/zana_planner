"""Normalize adapter return values into JSON-friendly structures for MCP.

Many ``PlannerAPIAdapter`` methods return human-readable strings (built for a chat
UI), some already return dicts/lists, and a few return dataclasses or dates. MCP
clients work best with structured content, so we coerce returns toward plain JSON
types here. This is the seam for the incremental string->JSON conversion: as
individual adapter methods are migrated to return structured data, this helper
keeps passing them through unchanged.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from typing import Any


def normalize_result(value: Any) -> Any:
    """Coerce an adapter return value into JSON-serializable form.

    Conservative by design: dataclasses become dicts, dates become ISO strings,
    containers are normalized recursively, and everything else (including
    human-readable strings) is passed through untouched. We deliberately do not
    try to parse free-form strings as JSON — that belongs in per-method
    conversion, not a blanket guess here.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return normalize_result(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(k): normalize_result(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [normalize_result(v) for v in value]
    # Fallback: stringify unknown objects rather than letting serialization fail.
    return str(value)
