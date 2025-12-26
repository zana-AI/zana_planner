import pytest
from datetime import datetime, timedelta

from utils.time_utils import beautify_time, round_time, get_week_range


@pytest.mark.unit
def test_beautify_time_formats_hours_and_minutes():
    assert beautify_time(0.0) == "0 min"
    assert beautify_time(0.5) == "30 min"
    assert beautify_time(1.25) == "1:15 hrs"
    assert beautify_time(2.0) == "2:00 hrs"


@pytest.mark.unit
def test_round_time_rounds_to_step_minutes():
    assert round_time(0.0) == 0.0
    assert round_time(-0.1) == 0.0
    # 1h07m -> 1h05m
    assert round_time(1 + 7 / 60) == pytest.approx(1 + 5 / 60)
    # 1h08m -> 1h10m
    assert round_time(1 + 8 / 60) == pytest.approx(1 + 10 / 60)


@pytest.mark.unit
def test_get_week_range_returns_monday_start_and_next_monday_end():
    ref = datetime(2025, 9, 17, 10, 30)  # Wednesday
    week_start, week_end = get_week_range(ref, week_start_hour=3)
    assert week_start.weekday() == 0  # Monday
    assert week_start.hour == 3
    assert week_end == week_start + timedelta(days=7)
