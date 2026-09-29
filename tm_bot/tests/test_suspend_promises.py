"""Suspension must be reversible without losing reminders or event history."""
import os
import random
from contextlib import contextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from db.postgres_db import get_engine
from models.models import Promise
from repositories import promises_repo, reminders_repo


pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


def test_suspend_resume_preserves_history_and_pauses_reminders(monkeypatch):
    if os.getenv("ENVIRONMENT", "").lower() not in ("staging", "stage"):
        pytest.skip("Runs only against the staging PostgreSQL schema")

    connection = get_engine().connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)

    @contextmanager
    def same_transaction():
        yield session

    monkeypatch.setattr(promises_repo, "get_db_session", same_transaction)
    monkeypatch.setattr(reminders_repo, "get_db_session", same_transaction)

    try:
        user_id = random.randint(10**13, 10**14 - 1)
        promise_id = f"P{random.randint(10000, 99999)}"
        repo = promises_repo.PromisesRepository()
        reminders = reminders_repo.RemindersRepository()
        repo.upsert_promise(user_id, Promise(str(user_id), promise_id, "Suspension test", 2.0))
        initial = repo.get_promise(user_id, promise_id)
        assert initial is not None
        p_uuid = session.execute(
            text("SELECT promise_uuid FROM promises WHERE user_id = :uid AND current_id = :pid"),
            {"uid": str(user_id), "pid": promise_id},
        ).scalar_one()
        reminder_id = reminders.create_reminder({
            "promise_uuid": p_uuid, "kind": "fixed_time", "weekday": 0,
            "time_local": "09:00:00", "tz": "UTC", "enabled": True,
            "next_run_at_utc": "2020-01-01T00:00:00Z",
        })
        assert reminder_id in {r["reminder_id"] for r in reminders.get_due_reminders()}

        first = repo.set_suspended(user_id, promise_id, True)
        assert first and first["changed"] and first["suspended_at_utc"]
        assert repo.set_suspended(user_id, promise_id, True)["changed"] is False
        assert promise_id not in {p.id for p in repo.list_promises(user_id)}
        assert promise_id in {p.id for p in repo.list_suspended_promises(user_id)}
        assert reminders.get_reminder(reminder_id)["next_run_at_utc"] is None

        # Even if an old due time is written during suspension, dispatch must skip it.
        reminders.update_reminder(reminder_id, {"next_run_at_utc": "2020-01-01T00:00:00Z"})
        assert reminder_id not in {r["reminder_id"] for r in reminders.get_due_reminders()}

        resumed = repo.set_suspended(user_id, promise_id, False)
        assert resumed and resumed["changed"] and resumed["suspended_at_utc"] is None
        assert repo.set_suspended(user_id, promise_id, False)["changed"] is False
        assert promise_id in {p.id for p in repo.list_promises(user_id)}
        assert repo.get_promise(user_id, promise_id).text == initial.text
        events = session.execute(
            text("SELECT event_type FROM promise_events WHERE promise_uuid = :uuid ORDER BY at_utc"),
            {"uuid": p_uuid},
        ).scalars().all()
        assert events.count("suspend") == 1
        assert events.count("resume") == 1
        assert events.count("create") == 1
    finally:
        session.close()
        transaction.rollback()
        connection.close()
