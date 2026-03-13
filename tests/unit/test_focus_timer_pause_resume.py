from datetime import datetime

import pytest

import services.sessions as sessions_module
from models.models import Session
from services.sessions import SessionsService


class _FakeSessionsRepo:
    def __init__(self, session: Session):
        self.session = session
        self.updated_sessions: list[Session] = []

    def get_session(self, user_id: int, session_id: str):
        if str(self.session.user_id) == str(user_id) and self.session.session_id == session_id:
            return self.session
        return None

    def update_session(self, session: Session) -> None:
        self.session = session
        self.updated_sessions.append(session)


class _FakeActionsRepo:
    def append_action(self, action) -> None:
        self.last_action = action


@pytest.mark.unit
def test_resume_adds_paused_time_and_extends_expected_end(monkeypatch):
    fixed_now = datetime(2025, 1, 1, 10, 20, 0)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is None else fixed_now.replace(tzinfo=tz)

    monkeypatch.setattr(sessions_module, "datetime", FixedDateTime)

    session = Session(
        session_id="session-1",
        user_id="7",
        promise_id="P01",
        status="paused",
        started_at=datetime(2025, 1, 1, 10, 0, 0),
        last_state_change_at=datetime(2025, 1, 1, 10, 5, 0),
        paused_seconds_total=0,
        expected_end_utc=datetime(2025, 1, 1, 10, 25, 0),
        planned_duration_minutes=25,
        timer_kind="focus",
    )
    repo = _FakeSessionsRepo(session)
    service = SessionsService(repo, _FakeActionsRepo())

    resumed = service.resume(7, "session-1")

    assert resumed is not None
    assert resumed.status == "running"
    assert resumed.paused_seconds_total == 15 * 60
    assert resumed.expected_end_utc == datetime(2025, 1, 1, 10, 40, 0)
    assert resumed.last_state_change_at == fixed_now
    assert repo.updated_sessions[-1] is resumed


@pytest.mark.unit
def test_get_session_elapsed_time_freezes_while_paused(monkeypatch):
    fixed_now = datetime(2025, 1, 1, 10, 20, 0)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is None else fixed_now.replace(tzinfo=tz)

    monkeypatch.setattr(sessions_module, "datetime", FixedDateTime)

    session = Session(
        session_id="session-2",
        user_id="7",
        promise_id="P01",
        status="paused",
        started_at=datetime(2025, 1, 1, 10, 0, 0),
        last_state_change_at=datetime(2025, 1, 1, 10, 5, 0),
        paused_seconds_total=0,
    )
    service = SessionsService(_FakeSessionsRepo(session), _FakeActionsRepo())

    elapsed_hours = service.get_session_elapsed_time(session)

    assert elapsed_hours == pytest.approx(5 / 60)


@pytest.mark.unit
def test_finish_from_paused_excludes_current_pause_interval(monkeypatch):
    fixed_now = datetime(2025, 1, 1, 10, 20, 0)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now if tz is None else fixed_now.replace(tzinfo=tz)

    monkeypatch.setattr(sessions_module, "datetime", FixedDateTime)

    session = Session(
        session_id="session-3",
        user_id="7",
        promise_id="P01",
        status="paused",
        started_at=datetime(2025, 1, 1, 10, 0, 0),
        last_state_change_at=datetime(2025, 1, 1, 10, 5, 0),
        paused_seconds_total=0,
    )
    repo = _FakeSessionsRepo(session)
    actions_repo = _FakeActionsRepo()
    service = SessionsService(repo, actions_repo)

    action = service.finish(7, "session-3")

    assert action is not None
    assert action.time_spent == pytest.approx(5 / 60)
    assert repo.session.status == "finished"
    assert repo.session.paused_seconds_total == 15 * 60
