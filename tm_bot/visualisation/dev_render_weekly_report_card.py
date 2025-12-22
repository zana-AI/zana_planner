"""
Dev helper: render a sample weekly report card PNG.

Usage (inside the zana_planner container or venv with Playwright installed):
  python -m tm_bot.visualisation.dev_render_weekly_report_card

Optional:
  OUT=/tmp/weekly_card.png python -m tm_bot.visualisation.dev_render_weekly_report_card
"""

import os
import tempfile
from datetime import datetime, timedelta

from utils.time_utils import get_week_range
from visualisation.weekly_report_card import render_weekly_report_card_png


def main() -> None:
    now = datetime.now()
    week_start, week_end = get_week_range(now)
    d0 = week_start.date()

    summary = {
        "P01": {
            "text": "Learn Arabic - تعلم العربية (Level 1)",
            "hours_promised": 5.0,
            "hours_spent": 3.5,
            "sessions": [
                {"date": d0 + timedelta(days=0), "hours": 1.0},  # Mon
                {"date": d0 + timedelta(days=2), "hours": 2.0},  # Wed
                {"date": d0 + timedelta(days=4), "hours": 0.5},  # Fri
            ],
        },
        "P02": {
            "text": "فارسی — مطالعه و تمرین نوشتن (Mixed English 123)",
            "hours_promised": 2.0,
            "hours_spent": 2.0,
            "sessions": [
                {"date": d0 + timedelta(days=1), "hours": 1.0},  # Tue
                {"date": d0 + timedelta(days=5), "hours": 1.0},  # Sat
            ],
        },
        "P03": {
            "text": "עברית: לקרוא ולכתוב — very very long title that should clamp nicely in the card layout",
            "hours_promised": 1.0,
            "hours_spent": 0.25,
            "sessions": [
                {"date": d0 + timedelta(days=6), "hours": 0.25},  # Sun
            ],
        },
        "P04": {
            "text": "היום 12:30 — mixed numbers and punctuation (RTL + LTR)",
            "hours_promised": 3.0,
            "hours_spent": 1.5,
            "sessions": [
                {"date": d0 + timedelta(days=0), "hours": 0.5},
                {"date": d0 + timedelta(days=3), "hours": 1.0},
            ],
        },
    }

    out = os.environ.get("OUT")
    if not out:
        out = os.path.join(tempfile.gettempdir(), "weekly_report_card_sample.png")

    render_weekly_report_card_png(
        summary=summary,
        output_path=out,
        week_start=week_start,
        week_end=week_end,
        width=1200,
    )
    print(out)


if __name__ == "__main__":
    main()

