import pytest
from datetime import datetime

from models.models import Session
from repositories.sessions_repo import SessionsRepository
from models.models import Promise
from repositories.promises_repo import PromisesRepository


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
    )
    repo.create_session(s1)

    sessions = repo.list_sessions(user_id)
    assert len(sessions) == 1
    assert sessions[0].session_id == "S01"
    assert sessions[0].status == "running"

    active = repo.list_active_sessions(user_id)
    assert len(active) == 1
    assert active[0].session_id == "S01"
