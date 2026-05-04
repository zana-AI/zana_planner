from datetime import datetime

from services.club_reminder_service import _display_name, build_club_reminder_message


def test_display_name_uses_one_script_for_group_language():
    member = {
        "non_latin_name": "\u062c\u0648\u0627\u062f",
        "latin_name": "Javad",
        "first_name": "Fallback",
    }

    assert _display_name(member, "fa") == "\u062c\u0648\u0627\u062f"
    assert _display_name(member, "en") == "Javad"


def test_reminder_title_includes_localized_weekday():
    message = build_club_reminder_message(
        "Club",
        [{"name": "\u062c\u0648\u0627\u062f", "status": None, "streak": 0}],
        promise_text="Daily practice",
        language="fa",
        now_utc=datetime(2026, 5, 4, 10, 0, 0),
        timezone="UTC",
    )

    assert message is not None
    assert message.splitlines()[0] == "\U0001f3af Club \u00b7 \u062f\u0648\u0634\u0646\u0628\u0647 \u00b7 check-in"


def test_done_streak_display_uses_final_streak_without_incrementing():
    message = build_club_reminder_message(
        "Club",
        [{"name": "Javad", "status": "done", "streak": 2}],
        promise_text="Daily practice",
        language="en",
        now_utc=datetime(2026, 5, 4, 10, 0, 0),
        timezone="UTC",
    )

    assert "\u2705 Javad \U0001f5252" in message
    assert "\U0001f5253" not in message
