"""Unit tests for ReportsService smart effective-start-date and past-week sorting.

These tests use fake in-memory repos (no DB required) to verify:
1. Promises with an earliest action before their declared start_date are included
   in past-week reports (effective_start = min(start_date, earliest_action_date)).
2. Promises whose start_date is in the future but have prior actions appear in
   historical reports.
3. Current-week behaviour is unchanged (original start_date check).
4. Past-week report data is ordered by achieved_value descending.
"""
import pytest
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from unittest.mock import patch, MagicMock

from models.models import Promise, Action
from services.reports import ReportsService


# ---------------------------------------------------------------------------
# Fake repositories
# ---------------------------------------------------------------------------

class FakePromisesRepo:
    def __init__(self, promises):
        self._promises = list(promises)

    def list_promises(self, user_id):
        return list(self._promises)

    def get_promise(self, user_id, promise_id):
        for p in self._promises:
            if p.id == promise_id:
                return p
        return None


class FakeActionsRepo:
    def __init__(self, actions):
        self._actions = list(actions)

    def list_actions(self, user_id, since=None):
        if since is None:
            return list(self._actions)
        return [a for a in self._actions if a.at >= since]

    def get_earliest_action_dates(self, user_id) -> Dict[str, date]:
        earliest: Dict[str, date] = {}
        for a in self._actions:
            pid = a.promise_id
            d = a.at.date()
            if pid not in earliest or d < earliest[pid]:
                earliest[pid] = d
        return earliest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _promise(pid, start_date=None, hours=4.0):
    return Promise(
        user_id="1",
        id=pid,
        text=f"Promise {pid}",
        hours_per_week=hours,
        recurring=True,
        start_date=start_date,
    )


def _action(pid, at: datetime, hours=1.0):
    return Action(
        user_id="1",
        promise_id=pid,
        action="log_time",
        time_spent=hours,
        at=at,
    )


def _build_svc(promises, actions):
    return ReportsService(
        promises_repo=FakePromisesRepo(promises),
        actions_repo=FakeActionsRepo(actions),
    )


# Context manager that patches the DB-dependent parts of get_weekly_summary_with_sessions
# so unit tests can run without a live PostgreSQL connection.
from contextlib import contextmanager

@contextmanager
def _no_db():
    """Patch away all direct DB calls inside ReportsService so tests remain unit-level."""
    # resolve_promise_uuid always returns None → no instances looked up
    # get_db_session returns a context manager that yields a MagicMock session
    fake_session = MagicMock()
    fake_cm = MagicMock()
    fake_cm.__enter__ = MagicMock(return_value=fake_session)
    fake_cm.__exit__ = MagicMock(return_value=False)

    with patch("services.reports.resolve_promise_uuid", return_value=None), \
         patch("services.reports.get_db_session", return_value=fake_cm), \
         patch("services.reports.InstancesRepository") as mock_ir:
        mock_ir.return_value.get_instance_by_promise_uuid.return_value = None
        yield


# ---------------------------------------------------------------------------
# Reference timestamps (use a fixed "today" to make tests deterministic)
# ---------------------------------------------------------------------------

# A known past Monday so tests are time-independent
PAST_WEEK_MON = datetime(2026, 1, 5, 12, 0)   # Monday 2026-01-05

# The current-week tests use a ref_time far in the future so
# the is_past_week flag stays False.
FUTURE_WEEK_MON = datetime(2099, 3, 2, 12, 0)  # Some distant Monday


# ---------------------------------------------------------------------------
# Past-week tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_promise_with_actions_before_start_date_appears_in_past_week():
    """
    P1 has start_date = 2026-02-01 (future relative to the past week).
    But it had an action on 2026-01-07 (inside the past week).
    => P1 should appear in the report for the week of 2026-01-05.
    """
    future_start = date(2026, 2, 1)
    p1 = _promise("P1", start_date=future_start)
    action_in_week = _action("P1", datetime(2026, 1, 7, 10, 0), hours=2.0)

    svc = _build_svc([p1], [action_in_week])
    with _no_db():
        report = svc.get_weekly_summary_with_sessions(1, PAST_WEEK_MON)

    assert "P1" in report, (
        "Promise with actions inside the week must appear even if start_date is later"
    )
    assert report["P1"]["hours_spent"] == pytest.approx(2.0)


@pytest.mark.unit
def test_promise_with_actions_before_past_week_appears_due_to_prior_activity():
    """
    P1 has start_date = 2026-06-01 (months after the viewed week).
    It has an action from 2025-11-10 (well before the viewed week).
    => effective_start = 2025-11-10 <= week_end of 2026-01-11
    => P1 should appear in the past-week report even with 0 hours this week.
    """
    far_future_start = date(2026, 6, 1)
    p1 = _promise("P1", start_date=far_future_start)
    old_action = _action("P1", datetime(2025, 11, 10, 9, 0), hours=3.0)

    svc = _build_svc([p1], [old_action])
    with _no_db():
        report = svc.get_weekly_summary_with_sessions(1, PAST_WEEK_MON)

    assert "P1" in report, (
        "Promise with prior activity must be included in past-week report"
    )
    # No actions during the past week itself => 0 hours_spent
    assert report["P1"]["hours_spent"] == pytest.approx(0.0)


@pytest.mark.unit
def test_promise_without_any_actions_and_future_start_excluded_from_past_week():
    """
    P1 has start_date = 2026-06-01 and NO actions at all.
    => effective_start = 2026-06-01 > week_end 2026-01-11
    => P1 must NOT appear in the past-week report.
    """
    p1 = _promise("P1", start_date=date(2026, 6, 1))
    svc = _build_svc([p1], [])
    with _no_db():
        report = svc.get_weekly_summary_with_sessions(1, PAST_WEEK_MON)
    assert "P1" not in report


@pytest.mark.unit
def test_promise_with_no_start_date_always_included():
    """A promise with no start_date is always active."""
    p1 = _promise("P1", start_date=None)
    svc = _build_svc([p1], [])
    with _no_db():
        report = svc.get_weekly_summary_with_sessions(1, PAST_WEEK_MON)
    assert "P1" in report


@pytest.mark.unit
def test_effective_start_uses_min_of_start_date_and_earliest_action():
    """
    P1 start_date = 2026-01-08 (mid-week).
    Earliest action = 2026-01-06 (earlier in the same week).
    => effective_start = 2026-01-06 <= week_end => P1 included.
    """
    p1 = _promise("P1", start_date=date(2026, 1, 8))
    early_action = _action("P1", datetime(2026, 1, 6, 10, 0), hours=1.5)
    svc = _build_svc([p1], [early_action])
    with _no_db():
        report = svc.get_weekly_summary_with_sessions(1, PAST_WEEK_MON)
    assert "P1" in report
    assert report["P1"]["hours_spent"] == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# Current-week behaviour unchanged
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_current_week_excludes_promise_with_future_start_and_no_actions():
    """
    For the current week, original logic must be preserved:
    a promise with start_date after ref_time and no past actions should NOT appear.
    """
    p1 = _promise("P1", start_date=date(2099, 3, 10))  # starts after the viewed week's Monday
    svc = _build_svc([p1], [])
    # ref_time = 2099-03-02 (Monday); week_end = 2099-03-08 (Sunday)
    with _no_db():
        report = svc.get_weekly_summary_with_sessions(1, FUTURE_WEEK_MON)
    # start_date 2099-03-10 > ref_time 2099-03-02 => excluded for current week
    assert "P1" not in report


@pytest.mark.unit
def test_current_week_includes_promise_that_started_today():
    """For current week, a promise with start_date <= today is included."""
    today_like = FUTURE_WEEK_MON.date()
    p1 = _promise("P1", start_date=today_like)
    svc = _build_svc([p1], [])
    with _no_db():
        report = svc.get_weekly_summary_with_sessions(1, FUTURE_WEEK_MON)
    assert "P1" in report


# ---------------------------------------------------------------------------
# get_weekly_summary (simpler Telegram bot method)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_simple_summary_includes_promise_with_prior_action_in_past_week():
    far_future_start = date(2026, 6, 1)
    p1 = _promise("P1", start_date=far_future_start)
    old_action = _action("P1", datetime(2025, 12, 1, 10, 0), hours=2.0)

    svc = _build_svc([p1], [old_action])
    report = svc.get_weekly_summary(1, PAST_WEEK_MON)

    assert "P1" in report, (
        "get_weekly_summary must also apply effective_start logic for past weeks"
    )


# ---------------------------------------------------------------------------
# Past-week ordering: most activity first
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_past_week_report_data_ordering_via_achieved_value():
    """
    For past weeks get_weekly_summary_with_sessions returns promises;
    verify that the promise with more hours has a higher achieved_value.
    (The actual visual sort happens in the frontend; this test ensures the
    values that drive sorting are correctly computed.)
    """
    p_high = _promise("HIGH", start_date=date(2025, 12, 1))
    p_low  = _promise("LOW",  start_date=date(2025, 12, 1))

    # HIGH gets 5h during the past week, LOW gets 1h
    actions = [
        _action("HIGH", datetime(2026, 1, 6, 10, 0), hours=5.0),
        _action("LOW",  datetime(2026, 1, 7, 10, 0), hours=1.0),
    ]
    svc = _build_svc([p_high, p_low], actions)
    with _no_db():
        report = svc.get_weekly_summary_with_sessions(1, PAST_WEEK_MON)

    assert report["HIGH"]["achieved_value"] == pytest.approx(5.0)
    assert report["LOW"]["achieved_value"]  == pytest.approx(1.0)
    assert report["HIGH"]["achieved_value"] > report["LOW"]["achieved_value"]
