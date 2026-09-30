"""A completed plan session and its promise activity must stay in sync."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso
from repositories.plan_sessions_repo import PlanSessionsRepository


pytestmark = [pytest.mark.repo, pytest.mark.requires_postgres]


def test_status_completion_logs_once_and_undo_removes_only_automatic_log():
    user_id = str(uuid.uuid4().int % 10**14)
    promise_uuid = str(uuid.uuid4())
    repo = PlanSessionsRepository()
    planned_start = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with get_db_session() as db:
        db.execute(text("""
            INSERT INTO promises (
                promise_uuid, user_id, current_id, text, hours_per_week,
                recurring, is_deleted, created_at_utc, updated_at_utc
            ) VALUES (:p, :u, 'T01', 'Exercise', 2, 1, 0, :now, :now)
        """), {"p": promise_uuid, "u": user_id, "now": utc_now_iso()})

    try:
        planned = repo.create(promise_uuid, user_id, {
            "title": "Core exercise", "planned_start": planned_start,
            "planned_duration_min": 30, "notes": None,
        })
        session_id = planned["id"]

        def logs():
            with get_db_session() as db:
                return db.execute(text("""
                    SELECT action_uuid, time_spent_hours, at_utc, notes FROM actions
                    WHERE user_id = :u AND promise_uuid = :p AND action_type = 'log_time'
                """), {"u": user_id, "p": promise_uuid}).mappings().all()

        assert logs() == []
        assert repo.update_status(session_id, user_id, "done")["status"] == "done"
        assert len(logs()) == 1
        assert logs()[0]["time_spent_hours"] == 0.5
        assert logs()[0]["at_utc"] == planned_start
        assert logs()[0]["notes"] == "Core exercise"

        repo.update_status(session_id, user_id, "planned")
        assert repo.get(session_id, user_id)["completed_at_utc"] is None
        completed = repo.update_status(session_id, user_id, "done", actual_duration_min=45)
        assert completed["actual_duration_min"] == 45
        assert completed["completed_at_utc"] is not None
        assert len(logs()) == 1
        assert logs()[0]["time_spent_hours"] == 0.75

        repo.update_status(session_id, user_id, "done")
        assert len(logs()) == 1

        repo.update_status(session_id, user_id, "planned")
        assert logs() == []

        repo.update_status(session_id, user_id, "done", activity_already_logged=True)
        assert logs() == []

        repo.update_status(session_id, user_id, "planned")
        repo.update_status(session_id, user_id, "done")
        assert len(logs()) == 1
    finally:
        with get_db_session() as db:
            db.execute(text("DELETE FROM actions WHERE user_id = :u AND promise_uuid = :p"), {"u": user_id, "p": promise_uuid})
            db.execute(text("DELETE FROM plan_sessions WHERE user_id = :u AND promise_uuid = :p"), {"u": user_id, "p": promise_uuid})
            db.execute(text("DELETE FROM promises WHERE user_id = :u AND promise_uuid = :p"), {"u": user_id, "p": promise_uuid})
