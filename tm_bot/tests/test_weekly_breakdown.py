"""Unit tests for ReportsService.get_weekly_breakdown (the structured weekly view).

Validates the behaviour that the prose get_weekly_report could not express:
count-based habits get check-ins counted, time goals get hours summed, expired
promises are omitted, and nothing is scored against a weekly-hours target.
"""

from datetime import datetime, timedelta, date

import pytest

from models.models import Promise, Action
from services.reports import ReportsService

pytestmark = pytest.mark.unit


class _Repo:
    def __init__(self, items):
        self._items = items

    def list_promises(self, user_id):
        return self._items

    def list_actions(self, user_id, since=None):
        return self._items


def _svc(promises, actions):
    return ReportsService(_Repo(promises), _Repo(actions))


def test_weekly_breakdown_counts_checkins_and_hours_and_drops_expired():
    now = datetime(2026, 6, 24, 12, 0)  # a Wednesday
    future = date(2026, 12, 31)
    past = date(2026, 1, 15)

    promises = [
        Promise(user_id="1", id="P01", text="Deep_work_(Stage11)", hours_per_week=20.0, end_date=future),
        Promise(user_id="1", id="C01", text="Play Cheenva", hours_per_week=0.0, end_date=None),
        Promise(user_id="1", id="P09", text="Play_piano", hours_per_week=0.67, end_date=past),  # expired
    ]
    actions = [
        Action(user_id="1", promise_id="P01", action="log_time", time_spent=4.0, at=now),
        Action(user_id="1", promise_id="P01", action="log_time", time_spent=2.0, at=now),
        Action(user_id="1", promise_id="C01", action="checkin", time_spent=0.0, at=now),
        Action(user_id="1", promise_id="C01", action="checkin", time_spent=0.0, at=now),
        Action(user_id="1", promise_id="C01", action="checkin", time_spent=0.0, at=now),
        Action(user_id="1", promise_id="C01", action="skip", time_spent=0.0, at=now),  # not counted
        Action(user_id="1", promise_id="P09", action="log_time", time_spent=1.0, at=now),  # expired -> excluded
    ]

    out = _svc(promises, actions).get_weekly_breakdown(1, now)
    by_id = {p["id"]: p for p in out["promises"]}

    assert set(by_id) == {"P01", "C01"}  # expired P09 dropped
    assert by_id["P01"] == {"id": "P01", "name": "Deep work (Stage11)", "tracking": "time", "checkins": 2, "hours": 6.0}
    assert by_id["C01"] == {"id": "C01", "name": "Play Cheenva", "tracking": "count", "checkins": 3, "hours": 0.0}
    assert out["totals"] == {"active_promises": 2, "total_checkins": 5, "total_hours": 6.0}


def test_weekly_breakdown_empty_when_no_activity():
    now = datetime(2026, 6, 24, 12, 0)
    promises = [Promise(user_id="1", id="C01", text="Meditate", hours_per_week=0.0, end_date=None)]
    out = _svc(promises, []).get_weekly_breakdown(1, now)
    assert out["promises"] == [{"id": "C01", "name": "Meditate", "tracking": "count", "checkins": 0, "hours": 0.0}]
    assert out["totals"] == {"active_promises": 1, "total_checkins": 0, "total_hours": 0.0}
