"""Tests for past-week filtering in weekly reports."""
from datetime import datetime, timedelta

import pytest

from services.planner_api_adapter import PlannerAPIAdapter
from services.reports import ReportsService
from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository


def _unique_user_id() -> int:
    import time
    return int(time.time() * 1000) % 900000000 + 100000000


@pytest.mark.integration
def test_past_week_includes_snoozed_promise_with_activity(tmp_path):
    """A snoozed promise (future start_date) still appears in past weeks when it has logs."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = _unique_user_id()

    msg = adapter.add_promise(user_id, promise_text="Reading", num_hours_promised_per_week=5.0)
    promise_id = msg.split()[0].lstrip("#")

    past_monday = datetime.now() - timedelta(days=14)
    past_monday = past_monday - timedelta(days=past_monday.weekday())
    past_monday = past_monday.replace(hour=12, minute=0, second=0, microsecond=0)

    adapter.add_action(user_id, promise_id, 2.0, action_datetime=past_monday + timedelta(days=1))

    # Snooze pushes start_date to a future Monday — would hide the promise under old logic.
    promise = adapter.promises_repo.get_promise(user_id, promise_id)
    next_monday = datetime.now().date() + timedelta(days=(7 - datetime.now().weekday()) % 7 or 7)
    promise.start_date = next_monday
    adapter.promises_repo.upsert_promise(user_id, promise)

    reports = ReportsService(PromisesRepository(), ActionsRepository())
    summary = reports.get_weekly_summary_with_sessions(user_id, past_monday)

    assert promise_id in summary
    assert summary[promise_id]["hours_spent"] == pytest.approx(2.0)


@pytest.mark.integration
def test_past_week_hides_inactive_promises(tmp_path):
    """Past weeks only show promises that had activity that week."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = _unique_user_id()

    msg_active = adapter.add_promise(user_id, promise_text="Active", num_hours_promised_per_week=3.0)
    active_id = msg_active.split()[0].lstrip("#")
    msg_idle = adapter.add_promise(user_id, promise_text="Idle", num_hours_promised_per_week=2.0)
    idle_id = msg_idle.split()[0].lstrip("#")

    past_monday = datetime.now() - timedelta(days=14)
    past_monday = past_monday - timedelta(days=past_monday.weekday())
    past_monday = past_monday.replace(hour=12, minute=0, second=0, microsecond=0)

    adapter.add_action(user_id, active_id, 1.5, action_datetime=past_monday + timedelta(days=2))

    reports = ReportsService(PromisesRepository(), ActionsRepository())
    summary = reports.get_weekly_summary_with_sessions(user_id, past_monday)

    assert active_id in summary
    assert idle_id not in summary


@pytest.mark.integration
def test_current_week_still_shows_inactive_promises(tmp_path):
    """The current week keeps showing active promises even without logs yet."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    user_id = _unique_user_id()

    msg = adapter.add_promise(user_id, promise_text="New habit", num_hours_promised_per_week=4.0)
    promise_id = msg.split()[0].lstrip("#")

    now = datetime.now().replace(microsecond=0)
    reports = ReportsService(PromisesRepository(), ActionsRepository())
    summary = reports.get_weekly_summary_with_sessions(user_id, now)

    assert promise_id in summary
    assert summary[promise_id]["hours_spent"] == 0.0
