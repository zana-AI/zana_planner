"""Session scheduling, Telegram text, and calendar options use the same instant."""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from services.planner_api_adapter import PlannerAPIAdapter
from webapp import notifications
from webapp.routers import plan_sessions
from webapp.schemas import PlanSessionIn


class _SettingsRepo:
    def get_settings(self, user_id):
        return SimpleNamespace(timezone="Europe/Paris")


class _PlanSessionsRepo:
    def __init__(self):
        self.created = []

    def create(self, promise_uuid, user_id, data):
        self.created.append(data)
        return {"id": 77}


@pytest.mark.unit
def test_web_scheduling_normalizes_local_time_and_requires_positive_duration(monkeypatch):
    monkeypatch.setattr(plan_sessions, "_user_timezone", lambda user_id: ZoneInfo("Europe/Paris"))
    assert plan_sessions._normalize_planned_start("2026-09-28T15:00:00", 123) == (
        "2026-09-28T13:00:00Z"
    )
    assert plan_sessions._normalize_planned_start("2026-09-28T13:00:00Z", 123) == (
        "2026-09-28T13:00:00Z"
    )
    with pytest.raises(ValidationError):
        PlanSessionIn(planned_duration_min=0)


@pytest.mark.unit
def test_bot_scheduling_interprets_naive_time_in_user_timezone():
    adapter = PlannerAPIAdapter.__new__(PlannerAPIAdapter)
    adapter.settings_repo = _SettingsRepo()
    adapter.plan_sessions_repo = _PlanSessionsRepo()

    result = adapter.schedule_session(
        user_id=123,
        title="Exercise",
        planned_start="2026-09-28T15:00:00",
        planned_duration_min=30,
    )

    assert result.startswith("✅ Session #77 scheduled")
    assert adapter.plan_sessions_repo.created[0]["planned_start"] == "2026-09-28T13:00:00Z"
    assert adapter.plan_sessions_repo.created[0]["planned_duration_min"] == 30


@pytest.mark.unit
def test_bot_scheduling_rejects_invalid_duration():
    adapter = PlannerAPIAdapter.__new__(PlannerAPIAdapter)
    adapter.settings_repo = _SettingsRepo()
    adapter.plan_sessions_repo = _PlanSessionsRepo()

    result = adapter.schedule_session(
        user_id=123, planned_start="2026-09-28T15:00:00+02:00", planned_duration_min=0,
    )

    assert "positive number of minutes" in result
    assert adapter.plan_sessions_repo.created == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_saved_session_calendar_link_and_reminder_use_paris_time(monkeypatch):
    sent = []

    class FakeBot:
        def __init__(self, token):
            assert token == "test-token"

        async def send_message(self, **kwargs):
            sent.append(kwargs)

    monkeypatch.setattr(notifications, "Bot", FakeBot)
    monkeypatch.setattr(notifications, "SettingsRepository", _SettingsRepo)

    await notifications.send_plan_session_saved_notification(
        bot_token="test-token", user_id=123, plan_session_id=77,
        promise_id="C02", promise_text="Crossfit and Gym", title="شکم و کمر",
        planned_start="2026-09-28T13:00:00Z", planned_duration_min=30,
    )
    assert "15:00  ·  30min" in sent[0]["text"]
    calendar_url = sent[0]["reply_markup"].inline_keyboard[1][0].url
    calendar_params = parse_qs(urlsplit(calendar_url).query)
    assert calendar_params["text"] == ["Crossfit and Gym — شکم و کمر"]
    assert calendar_params["dates"] == [
        "20260928T130000Z/20260928T133000Z"
    ]

    await notifications.send_plan_session_reminder(
        bot_token="test-token", user_id=123, plan_session_id=77,
        promise_id="C02", promise_text="Crossfit and Gym", title="شکم و کمر",
        planned_start="2026-09-28T13:00:00Z", planned_duration_min=30,
        reminder_offset_min=10,
    )
    assert "Start: 15:00  -  30min" in sent[1]["text"]
