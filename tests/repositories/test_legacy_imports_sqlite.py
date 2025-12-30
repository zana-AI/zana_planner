import sqlite3
import pytest

from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from repositories.sessions_repo import SessionsRepository
from repositories.settings_repo import SettingsRepository


@pytest.mark.repo
def test_legacy_import_is_idempotent_and_tracked(tmp_path):
    """
    Calling repo read methods multiple times should not duplicate imported rows.
    Also validates legacy_imports markers are present.
    """
    root = str(tmp_path)
    user_id = 501
    udir = tmp_path / str(user_id)
    udir.mkdir(parents=True, exist_ok=True)

    # Legacy promises.csv (with header)
    (udir / "promises.csv").write_text(
        "id,text,hours_per_week,recurring,start_date,end_date,angle_deg,radius\n"
        "P01,LegacyPromise,2.0,True,2025-01-01,2025-12-31,0,0\n",
        encoding="utf-8",
    )
    # Legacy actions.csv (no header)
    (udir / "actions.csv").write_text(
        "2025-01-02,10:00,P01,1.5\n",
        encoding="utf-8",
    )
    # Legacy settings.yaml
    (udir / "settings.yaml").write_text(
        "timezone: UTC\nnightly_hh: 22\nnightly_mm: 0\nlanguage: en\n",
        encoding="utf-8",
    )

    # First read/import
    promises_repo = PromisesRepository(root)
    actions_repo = ActionsRepository(root)
    settings_repo = SettingsRepository(root)

    assert len(promises_repo.list_promises(user_id)) == 1
    assert len(actions_repo.list_actions(user_id)) == 1
    s = settings_repo.get_settings(user_id)
    assert s.timezone == "UTC"

    # Second read (should not duplicate)
    assert len(promises_repo.list_promises(user_id)) == 1
    assert len(actions_repo.list_actions(user_id)) == 1
    s2 = settings_repo.get_settings(user_id)
    assert s2.timezone == "UTC"

    # Verify DB row counts stay 1 for imported entities
    db_path = tmp_path / "zana.db"
    conn = sqlite3.connect(str(db_path))
    try:
        p_cnt = conn.execute("SELECT COUNT(*) FROM promises WHERE user_id = ?;", (str(user_id),)).fetchone()[0]
        a_cnt = conn.execute("SELECT COUNT(*) FROM actions WHERE user_id = ?;", (str(user_id),)).fetchone()[0]
        st_cnt = conn.execute("SELECT COUNT(*) FROM users WHERE user_id = ?;", (str(user_id),)).fetchone()[0]
        assert int(p_cnt) == 1
        assert int(a_cnt) == 1
        assert int(st_cnt) == 1

        # legacy_imports should have markers for each source
        rows = conn.execute(
            "SELECT source FROM legacy_imports WHERE user_id = ? ORDER BY source ASC;",
            (str(user_id),),
        ).fetchall()
        sources = [r[0] for r in rows]
        # promises imported as a dependency of actions (and also directly)
        assert "promises" in sources
        assert "actions" in sources
        assert "settings" in sources
    finally:
        conn.close()


@pytest.mark.repo
def test_sessions_repo_imports_legacy_sessions_csv(tmp_path):
    root = str(tmp_path)
    user_id = 777
    udir = tmp_path / str(user_id)
    udir.mkdir(parents=True, exist_ok=True)

    # Need a promise so sessions can resolve promise_uuid
    (udir / "promises.csv").write_text(
        "id,text,hours_per_week,recurring,start_date,end_date,angle_deg,radius\n"
        "P01,Seed,1.0,True,2025-01-01,2025-12-31,0,0\n",
        encoding="utf-8",
    )

    # Legacy sessions.csv (with header)
    (udir / "sessions.csv").write_text(
        "session_id,user_id,promise_id,status,started_at,ended_at,paused_seconds_total,last_state_change_at,message_id,chat_id\n"
        "S01,777,P01,running,2025-01-01T09:00:00,,0,2025-01-01T09:00:00,111,222\n",
        encoding="utf-8",
    )

    repo = SessionsRepository(root)
    sessions = repo.list_sessions(user_id)
    assert len(sessions) == 1
    assert sessions[0].session_id == "S01"
    assert sessions[0].promise_id == "P01"
    assert sessions[0].status == "running"

    # Verify row exists in SQLite
    db_path = tmp_path / "zana.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cnt = conn.execute("SELECT COUNT(*) FROM sessions WHERE user_id = ?;", (str(user_id),)).fetchone()[0]
        assert int(cnt) == 1
    finally:
        conn.close()




