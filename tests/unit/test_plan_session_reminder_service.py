import pytest

from services import plan_session_reminder_service as service_module


class _FakePlanSessionsRepo:
    def __init__(self, due_sessions):
        self.due_sessions = due_sessions
        self.marked = []

    def list_sessions_needing_reminder(self, lookahead_minutes=1):
        return list(self.due_sessions)

    def mark_plan_session_notified(self, session_id):
        self.marked.append(session_id)


@pytest.mark.asyncio
async def test_plan_session_reminder_service_sends_and_marks_notified(monkeypatch):
    repo = _FakePlanSessionsRepo(
        [
            {
                "id": 42,
                "user_id": "123",
                "promise_id": "P1",
                "promise_text": "Write",
                "title": "Draft",
                "planned_start": "2026-05-30T12:00:00Z",
                "planned_duration_min": 25,
                "reminder_offset_min": 0,
            }
        ]
    )
    calls = []

    async def _fake_send(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(service_module, "send_plan_session_reminder", _fake_send)

    sent = await service_module.PlanSessionReminderService(repo).dispatch_due_reminders("token")

    assert sent == 1
    assert repo.marked == [42]
    assert calls[0]["reminder_offset_min"] == 0
    assert calls[0]["plan_session_id"] == 42


@pytest.mark.asyncio
async def test_plan_session_reminder_service_does_not_mark_failed_send(monkeypatch):
    repo = _FakePlanSessionsRepo(
        [
            {
                "id": 7,
                "user_id": "123",
                "promise_id": "P1",
                "promise_text": "Write",
                "planned_start": "2026-05-30T12:00:00Z",
            }
        ]
    )

    async def _fake_send(**kwargs):
        raise RuntimeError("network")

    monkeypatch.setattr(service_module, "send_plan_session_reminder", _fake_send)

    sent = await service_module.PlanSessionReminderService(repo).dispatch_due_reminders("token")

    assert sent == 0
    assert repo.marked == []
