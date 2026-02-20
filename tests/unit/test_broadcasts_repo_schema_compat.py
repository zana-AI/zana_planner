from datetime import datetime, timezone

import pytest

import repositories.broadcasts_repo as broadcasts_repo_module
from repositories.broadcasts_repo import BroadcastsRepository


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


class _FakeSession:
    def __init__(self, row=None):
        self.calls = []
        self._row = row

    def execute(self, statement, params=None):
        sql = statement.text if hasattr(statement, "text") else str(statement)
        self.calls.append((sql, params or {}))

        if "FROM broadcasts" in sql and "WHERE broadcast_id = :broadcast_id" in sql:
            return _FakeResult(self._row)

        return _FakeResult()


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.mark.unit
def test_create_broadcast_omits_bot_token_id_when_column_missing(monkeypatch):
    fake_session = _FakeSession()
    monkeypatch.setattr(
        broadcasts_repo_module,
        "get_db_session",
        lambda: _FakeSessionContext(fake_session),
    )
    monkeypatch.setattr(
        broadcasts_repo_module,
        "get_table_columns",
        lambda session, table_name: [
            "broadcast_id",
            "admin_id",
            "message",
            "target_user_ids",
            "scheduled_time_utc",
            "status",
            "created_at_utc",
            "updated_at_utc",
        ],
    )
    monkeypatch.setattr(broadcasts_repo_module.uuid, "uuid4", lambda: "fixed-broadcast-id")

    repo = BroadcastsRepository()
    broadcast_id = repo.create_broadcast(
        admin_id=123,
        message="hello",
        target_user_ids=[123],
        scheduled_time_utc=datetime(2026, 2, 19, 23, 0, tzinfo=timezone.utc),
        bot_token_id="token-id",
    )

    assert broadcast_id == "fixed-broadcast-id"
    assert len(fake_session.calls) == 1
    insert_sql, insert_params = fake_session.calls[0]
    assert "INSERT INTO broadcasts" in insert_sql
    assert "bot_token_id" not in insert_sql
    assert "bot_token_id" not in insert_params


@pytest.mark.unit
def test_get_broadcast_selects_null_bot_token_id_when_column_missing(monkeypatch):
    fake_row = {
        "broadcast_id": "b1",
        "admin_id": "123",
        "message": "hello",
        "target_user_ids": "[123]",
        "scheduled_time_utc": "2026-02-19T23:00:00Z",
        "status": "pending",
        "bot_token_id": None,
        "created_at_utc": "2026-02-19T23:00:00Z",
        "updated_at_utc": "2026-02-19T23:00:00Z",
    }
    fake_session = _FakeSession(row=fake_row)
    monkeypatch.setattr(
        broadcasts_repo_module,
        "get_db_session",
        lambda: _FakeSessionContext(fake_session),
    )
    monkeypatch.setattr(
        broadcasts_repo_module,
        "get_table_columns",
        lambda session, table_name: [
            "broadcast_id",
            "admin_id",
            "message",
            "target_user_ids",
            "scheduled_time_utc",
            "status",
            "created_at_utc",
            "updated_at_utc",
        ],
    )

    repo = BroadcastsRepository()
    broadcast = repo.get_broadcast("b1")

    assert broadcast is not None
    assert broadcast.bot_token_id is None
    assert len(fake_session.calls) == 1
    select_sql, _ = fake_session.calls[0]
    assert "NULL AS bot_token_id" in select_sql
