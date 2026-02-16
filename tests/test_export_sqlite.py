import json
import sqlite3

import pytest

# tests/conftest.py adds zana_planner/tm_bot to sys.path, so import via that root.
from db.export import main as export_main


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            timezone TEXT NOT NULL,
            nightly_hh INTEGER NOT NULL,
            nightly_mm INTEGER NOT NULL,
            language TEXT NOT NULL,
            voice_mode TEXT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS promises (
            promise_uuid TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            current_id TEXT NOT NULL,
            text TEXT NOT NULL,
            hours_per_week REAL NOT NULL,
            recurring INTEGER NOT NULL,
            start_date TEXT NULL,
            end_date TEXT NULL,
            is_deleted INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS promise_aliases (
            user_id TEXT NOT NULL,
            alias_id TEXT NOT NULL,
            promise_uuid TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS promise_events (
            event_uuid TEXT PRIMARY KEY,
            promise_uuid TEXT NOT NULL,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            at_utc TEXT NOT NULL,
            snapshot_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS actions (
            action_uuid TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            promise_uuid TEXT NULL,
            promise_id_text TEXT NOT NULL,
            action_type TEXT NOT NULL,
            time_spent_hours REAL NOT NULL,
            at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            promise_uuid TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at_utc TEXT NOT NULL,
            ended_at_utc TEXT NULL,
            paused_seconds_total INTEGER NOT NULL,
            last_state_change_at_utc TEXT NULL,
            message_id INTEGER NULL,
            chat_id INTEGER NULL
        );
        """
    )


@pytest.mark.unit
def test_export_writes_manifest_and_user_json(tmp_path):
    data_dir = tmp_path
    out_dir = tmp_path / "export"
    db_path = tmp_path / "zana.db"

    conn = sqlite3.connect(str(db_path))
    try:
        _create_schema(conn)
        conn.execute(
            "INSERT INTO users VALUES (?,?,?,?,?,?,?,?);",
            ("123", "UTC", 22, 0, "en", None, "2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO promises VALUES (?,?,?,?,?,?,?,?,?,?,?);",
            ("pu1", "123", "P01", "Hello", 1.0, 1, None, None, 0, "2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO promise_events VALUES (?,?,?,?,?,?);",
            ("ev1", "pu1", "123", "create", "2025-01-01T00:00:00Z", "{\"id\":\"P01\"}"),
        )
        conn.execute(
            "INSERT INTO actions VALUES (?,?,?,?,?,?,?);",
            ("au1", "123", "pu1", "P01", "log_time", 1.0, "2025-01-02T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?);",
            ("s1", "123", "pu1", "running", "2025-01-03T00:00:00Z", None, 0, None, None, None),
        )
        conn.commit()
    finally:
        conn.close()

    rc = export_main(["--data-dir", str(data_dir), "--out", str(out_dir), "--user", "123"])
    assert rc == 0

    manifest_path = out_dir / "manifest.json"
    user_path = out_dir / "user_123.json"
    assert manifest_path.exists()
    assert user_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "users" in manifest
    assert manifest["users"] == ["123"]

    payload = json.loads(user_path.read_text(encoding="utf-8"))
    assert payload["user_id"] == "123"
    assert payload["settings"] is not None
    assert len(payload["promises"]) == 1
    assert len(payload["actions"]) == 1
    assert len(payload["sessions"]) == 1




