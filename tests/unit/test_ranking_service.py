"""Tests for the RankingService scoring and selection logic."""
import random
import pytest
from datetime import datetime, date, timedelta

from models.models import Promise, Action
from services.ranking import RankingService


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakePromisesRepo:
    def __init__(self, promises):
        self._promises = list(promises)

    def list_promises(self, user_id):
        return list(self._promises)


class FakeActionsRepo:
    def __init__(self, actions):
        self._actions = list(actions)

    def list_actions(self, user_id, since=None):
        if since is None:
            return list(self._actions)
        return [a for a in self._actions if a.at >= since]


class FakeSettingsRepo:
    def get_settings(self, user_id):
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_promise(pid, hpw=5.0, start_days_ago=30):
    return Promise(
        user_id="1",
        id=pid,
        text=f"Promise {pid}",
        hours_per_week=hpw,
        start_date=date.today() - timedelta(days=start_days_ago),
    )


def _make_action(pid, hours, days_ago=0, hour_of_day=10):
    return Action(
        user_id="1",
        promise_id=pid,
        action="log_time",
        time_spent=hours,
        at=datetime.now().replace(hour=hour_of_day, minute=0, second=0, microsecond=0) - timedelta(days=days_ago),
    )


def _build_svc(promises, actions):
    return RankingService(
        promises_repo=FakePromisesRepo(promises),
        actions_repo=FakeActionsRepo(actions),
        settings_repo=FakeSettingsRepo(),
    )


# ---------------------------------------------------------------------------
# Tests: weekday affinity
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_weekday_affinity_zero_when_no_history():
    p = _make_promise("P01")
    svc = _build_svc([p], [])
    assert svc._get_weekday_affinity(p, [], datetime.now()) == 0.0


@pytest.mark.unit
def test_weekday_affinity_high_on_matching_day():
    """If the user always works on this promise on Fridays, affinity should be high on Friday."""
    p = _make_promise("P01")
    # Create 4 Fridays of activity, no other days
    friday = datetime(2026, 2, 27, 10, 0)  # a Friday
    actions = [
        Action(user_id="1", promise_id="P01", action="log_time", time_spent=1.0,
               at=friday - timedelta(weeks=i))
        for i in range(4)
    ]
    svc = _build_svc([p], actions)
    score = svc._get_weekday_affinity(p, actions, friday)
    assert score > 2.0, "Should have strong affinity on the only active day"


@pytest.mark.unit
def test_weekday_affinity_zero_on_non_matching_day():
    """If the user only works Monday, affinity on Friday should be 0."""
    p = _make_promise("P01")
    monday = datetime(2026, 2, 23, 10, 0)  # a Monday
    actions = [
        Action(user_id="1", promise_id="P01", action="log_time", time_spent=1.0,
               at=monday - timedelta(weeks=i))
        for i in range(4)
    ]
    svc = _build_svc([p], actions)
    friday = datetime(2026, 2, 27, 10, 0)
    score = svc._get_weekday_affinity(p, actions, friday)
    assert score == 0.0


# ---------------------------------------------------------------------------
# Tests: motivation-adjusted deficit
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_motivation_dampens_neglected_promise():
    """A promise with zero past-4-weeks activity should have dampened deficit."""
    p = _make_promise("P01", hpw=10.0)
    now = datetime(2026, 2, 27, 12, 0)  # Friday noon
    svc = _build_svc([p], [])

    deficit = svc._get_motivation_adjusted_deficit(p, [], now)
    # raw deficit would be ~10 * (progress ~5/7) = ~7.1
    # motivation = 0.15 (floor) -> ~1.07
    assert 0 < deficit < 2.0, f"Dampened deficit should be low, got {deficit}"


@pytest.mark.unit
def test_motivation_full_when_consistently_active():
    """A promise with full past-4-weeks activity should have undampened deficit."""
    p = _make_promise("P01", hpw=5.0)
    now = datetime(2026, 2, 27, 12, 0)  # Friday noon

    # 4 weeks of 5h/week = 20h total over past 4 weeks
    actions = []
    for week_offset in range(1, 5):
        for d in range(5):  # Mon-Fri
            day = now - timedelta(weeks=week_offset, days=-d)
            actions.append(Action(
                user_id="1", promise_id="P01", action="log_time",
                time_spent=1.0, at=day.replace(hour=10),
            ))

    svc = _build_svc([p], actions)
    deficit = svc._get_motivation_adjusted_deficit(p, actions, now)
    # motivation should be ~1.0, deficit reflects current week only (no this-week actions)
    assert deficit > 0.5, f"Full-motivation deficit should be meaningful, got {deficit}"


# ---------------------------------------------------------------------------
# Tests: top_n selection
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_top_n_returns_correct_count():
    promises = [_make_promise(f"P{i:02d}") for i in range(5)]
    actions = [_make_action(f"P{i:02d}", 1.0, days_ago=i) for i in range(5)]
    svc = _build_svc(promises, actions)
    result = svc.top_n(user_id=1, now=datetime.now(), n=3)
    assert len(result) == 3


@pytest.mark.unit
def test_top_n_with_fewer_promises_than_n():
    promises = [_make_promise("P01")]
    svc = _build_svc(promises, [])
    result = svc.top_n(user_id=1, now=datetime.now(), n=3)
    assert len(result) == 1


@pytest.mark.unit
def test_top2_are_deterministic():
    """First two slots should be the same across multiple calls."""
    promises = [_make_promise(f"P{i:02d}", hpw=float(i + 1)) for i in range(6)]
    actions = []
    svc = _build_svc(promises, actions)
    now = datetime.now()

    results = [svc.top_n(user_id=1, now=now, n=3) for _ in range(20)]
    first_slots = [(r[0].id, r[1].id) for r in results]
    assert len(set(first_slots)) == 1, "Top-2 should be deterministic"


@pytest.mark.unit
def test_slot3_has_variety():
    """Third slot should not always be the same (weighted random)."""
    promises = [_make_promise(f"P{i:02d}", hpw=float(i + 1)) for i in range(10)]
    actions = []
    svc = _build_svc(promises, actions)
    now = datetime.now()

    random.seed(None)  # ensure randomness
    third_ids = set()
    for _ in range(50):
        result = svc.top_n(user_id=1, now=now, n=3)
        if len(result) >= 3:
            third_ids.add(result[2].id)

    assert len(third_ids) > 1, "3rd slot should show variety across runs"


# ---------------------------------------------------------------------------
# Tests: future opportunity surplus
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_future_surplus_zero_when_no_history():
    """No action history → no surplus → signal is 0."""
    p = _make_promise("P01")
    svc = _build_svc([p], [])
    assert svc._get_future_opportunity_surplus(p, [], datetime.now()) == 0.0


@pytest.mark.unit
def test_future_surplus_high_when_all_history_on_upcoming_days():
    """Promise worked every day of the past → should score high surplus (future days have good affinity)."""
    p = _make_promise("P01")
    now = datetime.now()
    # Spread 18 actions across the last 3 weeks, hitting all 7 weekdays
    actions = [_make_action("P01", 1.0, days_ago=d) for d in range(1, 22)]
    svc = _build_svc([p], actions)
    surplus = svc._get_future_opportunity_surplus(p, actions, now)
    # Every upcoming day in the next 6 should have affinity → surplus near max
    assert surplus > 0.3, f"Expected high surplus for all-weekday history, got {surplus}"


@pytest.mark.unit
def test_future_surplus_low_when_history_only_on_today():
    """Promise whose entire history falls on today's weekday → no surge on upcoming days."""
    p = _make_promise("P01")
    now = datetime.now()
    today_name = now.strftime('%A')
    # Build actions only on the same weekday as today, going back 5 weeks
    actions = []
    for weeks_ago in range(1, 6):
        past_day = now - timedelta(weeks=weeks_ago)
        # Adjust to the same weekday as today (it already is, since we subtract full weeks)
        actions.append(_make_action("P01", 1.0, days_ago=weeks_ago * 7))
    svc = _build_svc([p], actions)
    surplus = svc._get_future_opportunity_surplus(p, actions, now)
    # Next 6 days do NOT contain today's weekday (today is today, not in range(1,7))
    assert surplus < 0.15, f"Expected near-zero surplus for today-only history, got {surplus}"
