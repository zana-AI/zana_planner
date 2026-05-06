"""Per-user call rate gate.

Two independent counters, both keyed by (user_id, date):
  - live_data: expensive xAI/Grok calls with live search (default 10/day).
  - general:   all LLM calls (default unlimited; set DAILY_CALL_LIMIT to cap).

Both limits read from env at import time, but callers can pass an explicit
`limit` override for tests.
"""
from __future__ import annotations

import os
import threading
from collections import defaultdict
from datetime import date
from typing import Tuple

_lock = threading.Lock()
_live_counters: dict[str, dict[date, int]] = defaultdict(dict)
_general_counters: dict[str, dict[date, int]] = defaultdict(dict)

LIVE_DATA_DAILY_LIMIT: int = int(os.getenv("LIVE_DATA_DAILY_LIMIT", "10"))
# 0 means unlimited
GENERAL_DAILY_LIMIT: int = int(os.getenv("DAILY_CALL_LIMIT", "0"))


def _check_and_record(store: dict, user_id: str, limit: int) -> Tuple[bool, int]:
    today = date.today()
    with _lock:
        bucket = store[user_id]
        for d in list(bucket):
            if d < today:
                del bucket[d]
        count = bucket.get(today, 0)
        if limit > 0 and count >= limit:
            return False, count
        bucket[today] = count + 1
        return True, count + 1


def check_live_data(user_id: str, *, limit: int = LIVE_DATA_DAILY_LIMIT) -> Tuple[bool, int]:
    """Check and record one live-data (xAI) call. Returns (allowed, calls_used_today)."""
    return _check_and_record(_live_counters, user_id, limit)


def check_general(user_id: str, *, limit: int = GENERAL_DAILY_LIMIT) -> Tuple[bool, int]:
    """Check and record one general LLM call. Returns (allowed, calls_used_today).

    When limit == 0 (default) the call is always allowed.
    """
    return _check_and_record(_general_counters, user_id, limit)


def live_data_usage(user_id: str) -> int:
    today = date.today()
    with _lock:
        return _live_counters.get(user_id, {}).get(today, 0)


def general_usage(user_id: str) -> int:
    today = date.today()
    with _lock:
        return _general_counters.get(user_id, {}).get(today, 0)
