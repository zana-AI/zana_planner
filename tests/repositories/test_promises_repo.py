import json
import pytest
import sqlite3
from datetime import date

from models.models import Promise
from repositories.promises_repo import PromisesRepository


@pytest.mark.repo
def test_promises_repo_upsert_and_list_roundtrip(tmp_path):
    root = str(tmp_path)
    repo = PromisesRepository(root)
    user_id = 123

    p = Promise(
        user_id=str(user_id),
        id="P01",
        text="Deep_Work",
        hours_per_week=5.0,
        recurring=True,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        angle_deg=10,
        radius=2,
    )

    repo.upsert_promise(user_id, p)
    assert (tmp_path / "zana.db").exists()
    items = repo.list_promises(user_id)
    assert len(items) == 1
    assert items[0].id == "P01"
    assert items[0].text == "Deep_Work"
    assert items[0].hours_per_week == pytest.approx(5.0)


@pytest.mark.repo
def test_promises_repo_imports_legacy_json_when_csv_missing(tmp_path):
    root = str(tmp_path)
    repo = PromisesRepository(root)
    user_id = 555
    user_dir = tmp_path / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    # Create legacy JSON only; no CSV file.
    legacy = [
        {
            "id": "P01",
            "text": "Test_Promise",
            "hours_per_week": 3.5,
            "recurring": True,
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
            "angle_deg": 0,
            "radius": 0,
        }
    ]
    (user_dir / "promises.json").write_text(json.dumps(legacy), encoding="utf-8")

    items = repo.list_promises(user_id)
    assert (tmp_path / "zana.db").exists()
    assert len(items) == 1
    assert items[0].id == "P01"
    assert items[0].text == "Test_Promise"


@pytest.mark.repo
def test_promises_repo_rename_creates_alias_and_old_id_resolves(tmp_path):
    root = str(tmp_path)
    repo = PromisesRepository(root)
    user_id = 42

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

    # Check aliases table contains both P01 and P02
    db_path = tmp_path / "zana.db"
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT alias_id FROM promise_aliases WHERE user_id = ? ORDER BY alias_id ASC;",
            (str(user_id),),
        ).fetchall()
        aliases = [r[0] for r in rows]
        assert aliases == ["P01", "P02"]
    finally:
        conn.close()


@pytest.mark.repo
def test_promises_repo_writes_promise_events_for_create_rename_delete(tmp_path):
    root = str(tmp_path)
    repo = PromisesRepository(root)
    user_id = 77

    repo.upsert_promise(
        user_id,
        Promise(user_id=str(user_id), id="P01", text="X", hours_per_week=1.0, recurring=True),
    )
    p2 = Promise(user_id=str(user_id), id="P02", text="X", hours_per_week=1.0, recurring=True)
    setattr(p2, "old_id", "P01")
    repo.upsert_promise(user_id, p2)
    assert repo.delete_promise(user_id, "P02") is True

    db_path = tmp_path / "zana.db"
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT event_type, snapshot_json FROM promise_events WHERE user_id = ? ORDER BY at_utc ASC;",
            (str(user_id),),
        ).fetchall()
        types = [r[0] for r in rows]
        # At least one create, one rename, and one delete
        assert "create" in types
        assert "rename" in types
        assert "delete" in types

        # Delete snapshot should mark is_deleted true
        delete_row = next((r for r in rows if r[0] == "delete"), None)
        assert delete_row is not None
        snapshot = json.loads(delete_row[1])
        assert snapshot.get("is_deleted") is True
    finally:
        conn.close()
