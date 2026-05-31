import pytest
from datetime import datetime, timezone, timedelta

from utils.calendar_utils import generate_google_calendar_link, generate_ics, suggest_time_slot


@pytest.mark.unit
def test_generate_google_calendar_link_naive_datetime_uses_zulu_suffix():
    start = datetime(2025, 1, 2, 3, 4, 5)  # naive
    url = generate_google_calendar_link(
        title="Test",
        start_time=start,
        duration_hours=1.0,
        description="Hello",
        timezone="UTC",
    )
    assert "calendar.google.com/calendar/render" in url
    assert "text=Test" in url
    assert "dates=20250102T030405Z/20250102T040405Z" in url


@pytest.mark.unit
def test_generate_google_calendar_link_tz_aware_includes_offset():
    tz = timezone(timedelta(hours=1))
    start = datetime(2025, 1, 2, 3, 4, 5, tzinfo=tz)
    url = generate_google_calendar_link(
        title="Meet",
        start_time=start,
        duration_hours=2.0,
        description="Desc",
        timezone="Europe/Paris",
    )
    assert "dates=20250102T030405+0100/20250102T050405+0100" in url


@pytest.mark.unit
def test_generate_ics_naive_datetime_emits_utc_event():
    start = datetime(2025, 1, 2, 3, 4, 5)  # naive → treated as UTC
    ics = generate_ics(
        title="Focus session",
        start_time=start,
        duration_hours=0.5,
        description="Deep work",
    )
    assert ics.startswith("BEGIN:VCALENDAR")
    assert ics.strip().endswith("END:VCALENDAR")
    assert "\r\n" in ics  # CRLF line endings
    assert "SUMMARY:Focus session" in ics
    assert "DTSTART:20250102T030405Z" in ics
    assert "DTEND:20250102T033405Z" in ics  # +30 min
    assert "VALARM" not in ics  # no reminder requested


@pytest.mark.unit
def test_generate_ics_tz_aware_converts_to_utc():
    tz = timezone(timedelta(hours=1))
    start = datetime(2025, 1, 2, 3, 4, 5, tzinfo=tz)  # 02:04:05 UTC
    ics = generate_ics(title="Meet", start_time=start, duration_hours=1.0)
    assert "DTSTART:20250102T020405Z" in ics
    assert "DTEND:20250102T030405Z" in ics


@pytest.mark.unit
def test_generate_ics_includes_valarm_and_escapes_text():
    start = datetime(2025, 1, 2, 3, 4, 5)
    ics = generate_ics(
        title="A; tricky, title\nwith newline",
        start_time=start,
        duration_hours=1.0,
        reminder_minutes_before=10,
    )
    assert "BEGIN:VALARM" in ics
    assert "TRIGGER:-PT10M" in ics
    # special chars escaped per RFC 5545
    assert "SUMMARY:A\\; tricky\\, title\\nwith newline" in ics


@pytest.mark.unit
def test_suggest_time_slot_uses_base_date_and_preferred_time_without_flakiness(monkeypatch):
    # calendar_utils uses `datetime.now()` inside; patch it to be deterministic.
    import utils.calendar_utils as cal

    fixed_now = datetime(2030, 1, 1, 12, 0, 0)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(cal, "datetime", FixedDateTime)

    base_date = datetime(2030, 1, 1, 0, 0, 0)
    suggested = suggest_time_slot(duration_hours=1.0, preferred_hour=9, preferred_minute=0, base_date=base_date)
    # Since 09:00 is before the patched now(12:00), it should roll over to next day.
    assert suggested.date().isoformat() == "2030-01-02"
    assert suggested.hour == 9
    assert suggested.minute == 0
