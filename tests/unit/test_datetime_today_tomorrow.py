"""Unit tests for the 'today vs tomorrow, same time' datetime disambiguation."""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tm_bot"))
from llms.resolvers import _maybe_collapse_today_tomorrow  # noqa: E402

pytestmark = pytest.mark.unit

TZ = ZoneInfo("Europe/Paris")  # +02:00 in summer, matches the candidates below
NOW = datetime(2026, 5, 31, 17, 26, tzinfo=TZ)


def _low(cands):
    return {"resolved": None, "confidence": "low", "candidates": cands, "clarification": "Which one?"}


def test_picks_today_when_still_upcoming():
    out = _maybe_collapse_today_tomorrow(
        _low(["2026-05-31T18:00:00+02:00", "2026-06-01T18:00:00+02:00"]), NOW
    )
    assert out["confidence"] == "high"
    assert out["resolved"].startswith("2026-05-31T18:00")


def test_picks_tomorrow_when_today_already_passed():
    now = datetime(2026, 5, 31, 19, 30, tzinfo=TZ)  # 7:30pm, the 6pm slot is gone
    out = _maybe_collapse_today_tomorrow(
        _low(["2026-05-31T18:00:00+02:00", "2026-06-01T18:00:00+02:00"]), now
    )
    assert out["confidence"] == "high"
    assert out["resolved"].startswith("2026-06-01T18:00")


def test_tomorrow_vs_day_after_left_as_clarification():
    # "morning" → tomorrow 9am vs day-after 9am: earlier isn't today, so still ask.
    out = _maybe_collapse_today_tomorrow(
        _low(["2026-06-01T09:00:00+02:00", "2026-06-02T09:00:00+02:00"]), NOW
    )
    assert out["confidence"] == "low"
    assert out.get("clarification")


def test_different_times_left_as_clarification():
    out = _maybe_collapse_today_tomorrow(
        _low(["2026-05-31T18:00:00+02:00", "2026-06-01T19:00:00+02:00"]), NOW
    )
    assert out["confidence"] == "low"


def test_three_candidates_left_as_clarification():
    out = _maybe_collapse_today_tomorrow(
        _low([
            "2026-05-31T18:00:00+02:00",
            "2026-06-01T18:00:00+02:00",
            "2026-06-02T18:00:00+02:00",
        ]),
        NOW,
    )
    assert out["confidence"] == "low"


def test_high_confidence_untouched():
    parsed = {"resolved": "2026-05-31T18:00:00+02:00", "confidence": "high"}
    assert _maybe_collapse_today_tomorrow(parsed, NOW) == parsed
