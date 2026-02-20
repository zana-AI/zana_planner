from datetime import date, datetime

from visualisation.weekly_report_card import (
    build_weekly_report_card_html,
)


def _sample_summary():
    # Includes RTL (Arabic/Persian/Hebrew) + mixed RTL/LTR + long titles.
    return {
        "P01": {
            "text": "Learn Arabic - تعلم العربية (Level 1)",
            "hours_promised": 5.0,
            "hours_spent": 3.5,
            "sessions": [
                {"date": date(2025, 12, 22), "hours": 1.0},  # Mon
                {"date": date(2025, 12, 24), "hours": 2.0},  # Wed
                {"date": date(2025, 12, 26), "hours": 0.5},  # Fri
            ],
        },
        "P02": {
            "text": "فارسی — مطالعه و تمرین نوشتن (Mixed English 123)",
            "hours_promised": 2.0,
            "hours_spent": 2.0,
            "sessions": [
                {"date": date(2025, 12, 23), "hours": 1.0},  # Tue
                {"date": date(2025, 12, 27), "hours": 1.0},  # Sat
            ],
        },
        "P03": {
            "text": "עברית: לקרוא ולכתוב — very very long title that should clamp nicely in the card layout",
            "hours_promised": 1.0,
            "hours_spent": 0.25,
            "sessions": [
                {"date": date(2025, 12, 28), "hours": 0.25},  # Sun
            ],
        },
    }


def test_build_weekly_report_card_html_has_rtl_safety_features():
    week_start = datetime(2025, 12, 22, 0, 0, 0)  # Monday
    week_end = datetime(2025, 12, 29, 0, 0, 0)
    html_doc = build_weekly_report_card_html(
        _sample_summary(), week_start=week_start, week_end=week_end, width=1200
    )

    # Key CSS/HTML knobs that improve mixed RTL/LTR correctness.
    assert 'dir="auto"' in html_doc
    assert "unicode-bidi: plaintext" in html_doc
    assert 'dir="ltr"' in html_doc  # numeric spans + date range





