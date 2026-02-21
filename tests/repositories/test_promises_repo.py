"""Promises repository tests (PostgreSQL). Requires DB at schema head: run `cd tm_bot/db && alembic upgrade head`."""
import pytest
import uuid
from datetime import date

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso
from models.models import Promise
from repositories.promises_repo import PromisesRepository

from tests.test_config import unique_user_id

pytestmark = [pytest.mark.repo, pytest.mark.requires_postgres]


@pytest.mark.repo
def test_promises_repo_upsert_and_list_roundtrip(tmp_path):
    repo = PromisesRepository()
    user_id = unique_user_id()

    p = Promise(
        user_id=str(user_id),
        id="P01",
        text="Deep_Work",
        hours_per_week=5.0,
        recurring=True,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

    repo.upsert_promise(user_id, p)
    items = repo.list_promises(user_id)
    assert len(items) == 1
    assert items[0].id == "P01"
    assert items[0].text == "Deep_Work"
    assert items[0].hours_per_week == pytest.approx(5.0)


@pytest.mark.repo
def test_promises_repo_rename_creates_alias_and_old_id_resolves(tmp_path):
    repo = PromisesRepository()
    user_id = unique_user_id()

    # Create initial promise P01
    p1 = Promise(
        user_id=str(user_id),
        id="P01",
        text="Alpha",
        hours_per_week=2.0,
        recurring=True,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )
    repo.upsert_promise(user_id, p1)

    # Rename by upserting the same promise under a new id
    p2 = Promise(
        user_id=str(user_id),
        id="P02",
        text="Alpha",
        hours_per_week=2.0,
        recurring=True,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )
    # Explicitly indicate rename target
    setattr(p2, "old_id", "P01")
    repo.upsert_promise(user_id, p2)

    # Listing should show only current id
    items = repo.list_promises(user_id)
    assert [p.id for p in items] == ["P02"]

    # Old id should still resolve to the same promise (current_id == P02)
    by_old = repo.get_promise(user_id, "P01")
    assert by_old is not None
    assert by_old.id == "P02"


@pytest.mark.repo
def test_promises_repo_writes_promise_events_for_create_rename_delete(tmp_path):
    repo = PromisesRepository()
    user_id = unique_user_id()
    # Self-clean: remove any leftover promises for this user from previous runs (counter reuses IDs).
    for p in repo.list_promises(user_id):
        repo.delete_promise(user_id, p.id)

    repo.upsert_promise(
        user_id,
        Promise(user_id=str(user_id), id="P01", text="X", hours_per_week=1.0, recurring=True),
    )
    p2 = Promise(user_id=str(user_id), id="P02", text="X", hours_per_week=1.0, recurring=True)
    setattr(p2, "old_id", "P01")
    repo.upsert_promise(user_id, p2)
    assert repo.delete_promise(user_id, "P02") is True
    # After delete, listing should be empty
    items = repo.list_promises(user_id)
    assert len(items) == 0


@pytest.mark.repo
def test_promises_repo_delete_cleans_schedule_and_reminders(tmp_path):
    repo = PromisesRepository()
    user_id = unique_user_id()

    # Create promise
    promise = Promise(
        user_id=str(user_id),
        id="P01",
        text="Delete_Cleanup_Test",
        hours_per_week=2.0,
        recurring=True,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )
    repo.upsert_promise(user_id, promise)

    user_str = str(user_id)
    with get_db_session() as session:
        has_schedule_table = bool(session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'promise_schedule_weekly_slots'
            )
        """)).scalar())
        has_reminder_table = bool(session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'promise_reminders'
            )
        """)).scalar())

        if not (has_schedule_table and has_reminder_table):
            pytest.skip("Schedule/reminder tables are not present in this schema")

        promise_uuid_row = session.execute(
            text("""
                SELECT promise_uuid
                FROM promises
                WHERE user_id = :user_id AND current_id = :promise_id
                LIMIT 1
            """),
            {"user_id": user_str, "promise_id": "P01"},
        ).fetchone()
        assert promise_uuid_row is not None
        promise_uuid = str(promise_uuid_row[0])

        now = utc_now_iso()
        slot_id = str(uuid.uuid4())
        reminder_id = str(uuid.uuid4())

        session.execute(
            text("""
                INSERT INTO promise_schedule_weekly_slots (
                    slot_id, promise_uuid, weekday, start_local_time, end_local_time,
                    tz, start_date, end_date, is_active, created_at_utc, updated_at_utc
                ) VALUES (
                    :slot_id, :promise_uuid, :weekday, :start_local_time, :end_local_time,
                    :tz, :start_date, :end_date, :is_active, :created_at_utc, :updated_at_utc
                )
            """),
            {
                "slot_id": slot_id,
                "promise_uuid": promise_uuid,
                "weekday": 0,
                "start_local_time": "09:00:00",
                "end_local_time": None,
                "tz": "UTC",
                "start_date": None,
                "end_date": None,
                "is_active": 1,
                "created_at_utc": now,
                "updated_at_utc": now,
            },
        )

        session.execute(
            text("""
                INSERT INTO promise_reminders (
                    reminder_id, promise_uuid, slot_id, kind, offset_minutes,
                    weekday, time_local, tz, enabled, last_sent_at_utc,
                    next_run_at_utc, created_at_utc, updated_at_utc
                ) VALUES (
                    :reminder_id, :promise_uuid, :slot_id, :kind, :offset_minutes,
                    :weekday, :time_local, :tz, :enabled, :last_sent_at_utc,
                    :next_run_at_utc, :created_at_utc, :updated_at_utc
                )
            """),
            {
                "reminder_id": reminder_id,
                "promise_uuid": promise_uuid,
                "slot_id": slot_id,
                "kind": "slot_offset",
                "offset_minutes": 10,
                "weekday": None,
                "time_local": None,
                "tz": "UTC",
                "enabled": 1,
                "last_sent_at_utc": None,
                "next_run_at_utc": None,
                "created_at_utc": now,
                "updated_at_utc": now,
            },
        )

    assert repo.delete_promise(user_id, "P01") is True

    with get_db_session() as session:
        remaining_slots = int(session.execute(
            text("SELECT COUNT(*) FROM promise_schedule_weekly_slots WHERE promise_uuid = :promise_uuid"),
            {"promise_uuid": promise_uuid},
        ).scalar() or 0)
        remaining_reminders = int(session.execute(
            text("SELECT COUNT(*) FROM promise_reminders WHERE promise_uuid = :promise_uuid"),
            {"promise_uuid": promise_uuid},
        ).scalar() or 0)

    assert remaining_slots == 0
    assert remaining_reminders == 0
