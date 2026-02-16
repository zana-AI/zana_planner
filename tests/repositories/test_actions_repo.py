import pytest
from datetime import datetime
import sqlite3

from models.models import Action
from repositories.actions_repo import ActionsRepository


@pytest.mark.repo
def test_actions_repo_append_and_list_roundtrip(tmp_path):
    repo = ActionsRepository()
    user_id = 100

    a = Action(
        user_id=user_id,
        promise_id="P01",
        action="log_time",
        time_spent=0.5,
        at=datetime(2025, 1, 19, 21, 33),
    )
    repo.append_action(a)

    items = repo.list_actions(user_id)
    assert len(items) == 1
    assert items[0].promise_id == "P01"
    assert items[0].time_spent == pytest.approx(0.5)


@pytest.mark.repo
def test_actions_repo_is_legacy_no_header_csv(tmp_path):
    repo = ActionsRepository()
    user_id = 200

    a = Action(
        user_id=user_id,
        promise_id="P99",
        action="log_time",
        time_spent=1.0,
        at=datetime(2025, 1, 1, 9, 0),
    )
    repo.append_action(a)
    # No CSV files should be created; actions are stored in SQLite.
    db_path = tmp_path / "zana.db"
    assert db_path.exists()

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT COUNT(*) FROM actions WHERE user_id = ?;", (str(user_id),)).fetchone()
        assert int(row[0] or 0) == 1
    finally:
        conn.close()


@pytest.mark.repo
def test_actions_repo_imports_legacy_actions_csv(tmp_path):
    root = str(tmp_path)
    user_id = 300

    # Create legacy promises.csv so actions can resolve to a promise_uuid
    user_dir = tmp_path / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "promises.csv").write_text(
        "id,text,hours_per_week,recurring,start_date,end_date\n"
        "P01,Legacy,2.0,True,2025-01-01,2025-12-31\n",
        encoding="utf-8",
    )
    # Legacy actions.csv has no header: date,time,promise_id,time_spent
    (user_dir / "actions.csv").write_text(
        "2025-01-01,09:00,P01,1.5\n",
        encoding="utf-8",
    )

    repo = ActionsRepository()
    items = repo.list_actions(user_id)
    assert len(items) == 1
    assert items[0].promise_id == "P01"
    assert items[0].time_spent == pytest.approx(1.5)

    # It should have been imported into SQLite
    db_path = tmp_path / "zana.db"
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT COUNT(*) FROM actions WHERE user_id = ?;", (str(user_id),)).fetchone()
        assert int(row[0] or 0) == 1
    finally:
        conn.close()
