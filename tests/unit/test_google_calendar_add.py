"""The direct Calendar action preserves the planned instant and duration."""

from datetime import datetime, timezone

import pytest

from webapp.routers.google_calendar import _direct_add_enabled_for, _event_payload


@pytest.mark.unit
def test_direct_calendar_event_uses_exact_utc_interval_and_reminder():
    event = _event_payload({
        "id": 77,
        "promise_uuid": None,
        "title": "Exercise",
        "notes": "Core workout",
        "planned_start": "2026-09-28T13:00:00Z",
        "planned_duration_min": 30,
        "reminder_enabled": True,
        "reminder_offset_min": 10,
    }, 123)
    assert event["start"]["dateTime"] == "2026-09-28T13:00:00Z"
    assert event["end"]["dateTime"] == "2026-09-28T13:30:00Z"
    assert event["reminders"]["overrides"] == [{"method": "popup", "minutes": 10}]
    assert event["summary"] == "Exercise"
    assert event["source"]["url"] == "https://xaana.club/plan-sessions/77/complete"
    assert "Mark done in Xaana: https://xaana.club/plan-sessions/77/complete" in event["description"]


@pytest.mark.unit
def test_direct_calendar_event_keeps_elapsed_duration_across_dst():
    event = _event_payload({
        "id": 77,
        "promise_uuid": None,
        "title": "Exercise",
        "planned_start": "2026-10-25T00:45:00Z",
        "planned_duration_min": 30,
        "reminder_enabled": False,
    }, 123)
    start = datetime.fromisoformat(event["start"]["dateTime"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(event["end"]["dateTime"].replace("Z", "+00:00"))
    assert start.astimezone(timezone.utc).isoformat() == "2026-10-25T00:45:00+00:00"
    assert (end - start).total_seconds() == 1800
    assert event["reminders"] == {"useDefault": False, "overrides": []}


@pytest.mark.unit
def test_unverified_calendar_access_is_limited_to_test_users(monkeypatch):
    monkeypatch.delenv("GOOGLE_CALENDAR_PUBLIC_ENABLED", raising=False)
    monkeypatch.delenv("GOOGLE_CALENDAR_TEST_USER_IDS", raising=False)
    monkeypatch.setenv("ADMIN_IDS", "123, 456")
    assert _direct_add_enabled_for(123)
    assert _direct_add_enabled_for(456)
    assert not _direct_add_enabled_for(789)


@pytest.mark.unit
def test_verified_calendar_access_can_be_opened_to_all_users(monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_PUBLIC_ENABLED", "1")
    monkeypatch.delenv("GOOGLE_CALENDAR_TEST_USER_IDS", raising=False)
    monkeypatch.delenv("ADMIN_IDS", raising=False)
    assert _direct_add_enabled_for(789)
