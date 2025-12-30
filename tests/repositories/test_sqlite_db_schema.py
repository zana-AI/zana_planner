import sqlite3

import pytest

from db.sqlite_db import connection_for_root


@pytest.mark.repo
def test_sqlite_db_creates_schema_and_tables(tmp_path):
    root = str(tmp_path)
    with connection_for_root(root) as conn:
        # Basic sanity: schema_version exists and is set.
        row = conn.execute("SELECT MAX(version) AS v FROM schema_version;").fetchone()
        assert int(row["v"] or 0) >= 1

        # A few critical tables exist
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
        }
        for expected in (
            "users",
            "promises",
            "promise_aliases",
            "promise_events",
            "actions",
            "sessions",
            "legacy_imports",
            # Social tables (v3)
            "user_follows",
            "user_blocks",
            "user_mutes",
            "clubs",
            "club_members",
            "promise_club_shares",
            "feed_items",
            "milestones",
            "feed_reactions",
            "social_events",
        ):
            assert expected in tables


@pytest.mark.repo
def test_sqlite_db_file_is_created_in_root(tmp_path):
    # Creating a connection should create <root>/zana.db
    root = str(tmp_path)
    with connection_for_root(root):
        pass
    assert (tmp_path / "zana.db").exists()



