import pytest
from datetime import datetime, timezone, timedelta

from models.models import Session
from repositories.sessions_repo import SessionsRepository
from models.models import Promise
from repositories.promises_repo import PromisesRepository

pytestmark = [pytest.mark.repo, pytest.mark.requires_postgres]


@pytest.mark.repo
def test_sessions_repo_create_list_and_active_filter(tmp_path):
    # Sessions require a valid promise_uuid link, so seed a promise first.
    promises_repo = PromisesRepository()
    promises_repo.upsert_promise(
        user_id=7,
        promise=Promise(
            user_id="7",
            id="P01",
            text="Seed",
            hours_per_week=1.0,
            recurring=True,
        ),
    )

    repo = SessionsRepository()
    user_id = 7

    expected_end = datetime(2025, 1, 1, 9, 30, 0, tzinfo=timezone.utc)
    s1 = Session(
        session_id="S01",
        user_id=user_id,
        promise_id="P01",
        status="running",
        started_at=datetime(2025, 1, 1, 9, 0, 0),
        ended_at=None,
        paused_seconds_total=0,
        last_state_change_at=None,
        message_id=111,
        chat_id=222,
        expected_end_utc=expected_end,
        planned_duration_minutes=25,
        timer_kind="focus",
        notified_at_utc=None,
    )
    repo.create_session(s1)

    sessions = repo.list_sessions(user_id)
    assert len(sessions) == 1
    assert sessions[0].session_id == "S01"
    assert sessions[0].status == "running"
    assert sessions[0].expected_end_utc is not None
    assert sessions[0].planned_duration_minutes == 25
    assert sessions[0].timer_kind == "focus"
    assert sessions[0].notified_at_utc is None

    active = repo.list_active_sessions(user_id)
    assert len(active) == 1
    assert active[0].session_id == "S01"
    assert active[0].planned_duration_minutes == 25


@pytest.mark.repo
def test_sessions_repo_overdue_notification_roundtrip():
    """Focus timer: list_overdue_sessions_needing_notification returns session until mark_session_notified."""
    promises_repo = PromisesRepository()
    user_id = 8
    promises_repo.upsert_promise(
        user_id=user_id,
        promise=Promise(
            user_id=str(user_id),
            id="P08",
            text="Focus seed",
            hours_per_week=1.0,
            recurring=True,
        ),
    )

    repo = SessionsRepository()
    # expected_end_utc in the past so it is overdue
    past_end = (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(microsecond=0)
    session = Session(
        session_id="S-overdue-01",
        user_id=user_id,
        promise_id="P08",
        status="running",
        started_at=datetime(2025, 1, 1, 9, 0, 0),
        ended_at=None,
        paused_seconds_total=0,
        last_state_change_at=None,
        message_id=None,
        chat_id=None,
        expected_end_utc=past_end,
        planned_duration_minutes=25,
        timer_kind="focus",
        notified_at_utc=None,
    )
    repo.create_session(session)

    overdue = repo.list_overdue_sessions_needing_notification()
    overdue_ids = [s.session_id for s in overdue]
    assert "S-overdue-01" in overdue_ids

    repo.mark_session_notified("S-overdue-01")
    overdue_after = repo.list_overdue_sessions_needing_notification()
    overdue_ids_after = [s.session_id for s in overdue_after]
    assert "S-overdue-01" not in overdue_ids_after