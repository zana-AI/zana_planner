import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import os
import sys

# Ensure zana_planner/ is importable (bot_stats.py lives in tm_bot/services/).
ZANA_PLANNER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ZANA_PLANNER_DIR not in sys.path:
    sys.path.insert(0, ZANA_PLANNER_DIR)

from tm_bot.services.bot_stats import compute_stats_sql  # noqa: E402


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _create_schema(conn: sqlite3.Connection) -> None:
    # Minimal subset needed by compute_stats_sql
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
            angle_deg INTEGER NOT NULL,
            radius INTEGER NOT NULL,
            is_deleted INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
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
def test_compute_stats_sql_counts_users_and_activity(tmp_path):
    data_dir = tmp_path
    db_path = tmp_path / "zana.db"

    now = datetime.now(timezone.utc).replace(microsecond=0)
    recent = _utc_iso(now - timedelta(days=2))
    old = _utc_iso(now - timedelta(days=40))

    conn = sqlite3.connect(str(db_path))
    try:
        _create_schema(conn)
        # user 1 has promises + recent actions
        conn.execute(
            "INSERT INTO promises VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?);",
            ("pu1", "1", "P01", "t", 1.0, 1, None, None, 0, 0, 0, _utc_iso(now), _utc_iso(now)),
        )
        conn.execute(
            "INSERT INTO actions VALUES (?,?,?,?,?,?,?);",
            ("au1", "1", "pu1", "P01", "log_time", 1.0, recent),
        )

        # user 2 has only old action (inactive for 30d window)
        conn.execute(
            "INSERT INTO actions VALUES (?,?,?,?,?,?,?);",
            ("au2", "2", None, "P99", "log_time", 2.0, old),
        )
        conn.commit()
    finally:
        conn.close()

    report = compute_stats_sql(str(data_dir))
    assert report["total_users"] == 2
    assert report["users_with_promises"] == 1
    assert report["users_with_actions"] == 2
    assert report["active_users_by_actions_mtime"]["7d"] == 1
    assert report["active_users_by_actions_mtime"]["30d"] == 1




