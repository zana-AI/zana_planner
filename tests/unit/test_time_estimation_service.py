import pytest
from datetime import datetime

from models.models import Action
from services.time_estimation_service import TimeEstimationService


class FakeActionsRepo:
    def __init__(self, actions):
        self._actions = list(actions)

    def list_actions(self, user_id, since=None):
        # Mimic ActionsRepository API used by TimeEstimationService.
        if since is None:
            return list(self._actions)
        return [a for a in self._actions if a.at >= since]


@pytest.mark.unit
def test_round_to_5_minutes_behavior():
    svc = TimeEstimationService(actions_repo=FakeActionsRepo([]))
    assert svc._round_to_5_minutes(0.0) == 0.0
    assert svc._round_to_5_minutes(-1.0) == 0.0
    # 7 minutes -> 5 minutes
    assert svc._round_to_5_minutes(7 / 60.0) == pytest.approx(5 / 60.0)
    # 8 minutes -> 10 minutes
    assert svc._round_to_5_minutes(8 / 60.0) == pytest.approx(10 / 60.0)


@pytest.mark.unit
def test_estimate_content_duration_uses_given_duration_if_present():
    svc = TimeEstimationService(actions_repo=FakeActionsRepo([]))
    meta = {"type": "youtube", "duration": 1.03, "metadata": {}}
    # rounds to nearest 5 minutes: 1.03h ~ 61.8m -> 60m
    assert svc.estimate_content_duration(meta) == pytest.approx(1.0)


@pytest.mark.unit
def test_estimate_content_duration_uses_word_count_if_present():
    svc = TimeEstimationService(actions_repo=FakeActionsRepo([]))
    meta = {"type": "blog", "metadata": {"word_count": 2000}}
    # 2000 words / 200 wpm = 10 min = 1/6 h -> rounds to 10 minutes (already on 5m step)
    assert svc.estimate_content_duration(meta) == pytest.approx(10 / 60.0)


@pytest.mark.unit
def test_analyze_user_work_patterns_aggregates_by_day_and_hour():
    actions = [
        Action(user_id="1", promise_id="P01", action="log_time", time_spent=1.0, at=datetime(2025, 1, 6, 10, 0)),  # Mon
        Action(user_id="1", promise_id="P01", action="log_time", time_spent=2.0, at=datetime(2025, 1, 6, 11, 0)),  # Mon
        Action(user_id="1", promise_id="P01", action="log_time", time_spent=3.0, at=datetime(2025, 1, 7, 10, 0)),  # Tue
    ]
    svc = TimeEstimationService(actions_repo=FakeActionsRepo(actions))
    patterns = svc.analyze_user_work_patterns(user_id=1)

    assert patterns["total_actions"] == 3
    assert patterns["total_days"] == 2
    assert patterns["most_productive_day"] in ("Monday", "Tuesday")
    assert 10 in patterns["by_hour"]
    assert 11 in patterns["by_hour"]
    assert patterns["by_hour"][10] == pytest.approx(4.0)
    assert patterns["by_hour"][11] == pytest.approx(2.0)
