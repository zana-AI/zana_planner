# utils_time.py
from datetime import datetime, timedelta


def beautify_time(hours: float) -> str:
    """Convert float hours to human-friendly text."""
    h = int(hours)
    m = int(round((hours - h) * 60))
    if h == 0 and m == 0:
        return "0 min"
    if h == 0:
        return f"{m} min"
    return f"{h}:{m:02d} hrs"


def round_time(hours: float, step_min: int = 5) -> float:
    """Round float hours to the nearest step (default 5 minutes)."""
    if hours <= 0:
        return 0.0
    h = int(hours)
    m = int(round((hours - h) * 60))
    m = round(m / step_min) * step_min
    return h + m / 60.0


def get_week_range(reference: datetime, week_start_hour: int = 0):
    """Return (week_start, week_end) given a reference datetime.
    Week starts from Monday at the specified hour (default 0 = midnight)."""
    monday = reference - timedelta(days=reference.weekday())
    week_start = monday.replace(hour=week_start_hour, minute=0, second=0, microsecond=0)
    if reference < week_start:
        week_start -= timedelta(days=7)
    end_of_week = week_start + timedelta(days=7)
    return week_start, end_of_week
