import json

import pytest

import repositories.content_repo as content_repo_module
from repositories.content_repo import ContentRepository


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def fetchone(self):
        return self._row


class _FakeSession:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        sql = statement.text if hasattr(statement, "text") else str(statement)
        self.calls.append((sql, params or {}))
        if "SELECT id FROM content WHERE canonical_url = :canonical_url" in sql:
            return _FakeResult({"id": "resolved-content-id"})
        return _FakeResult()


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.mark.unit
def test_upsert_content_uses_cast_for_metadata_json(monkeypatch):
    fake_session = _FakeSession()
    monkeypatch.setattr(
        content_repo_module,
        "get_db_session",
        lambda: _FakeSessionContext(fake_session),
    )

    repo = ContentRepository()
    content_id = repo.upsert_content(
        canonical_url="https://www.youtube.com/watch?v=1ZhsdckCK2c",
        original_url="https://www.youtube.com/watch?v=1ZhsdckCK2c",
        provider="youtube",
        content_type="video",
        title="Title",
        metadata_json={"captions_available": True},
    )

    assert content_id == "resolved-content-id"
    assert len(fake_session.calls) >= 2

    insert_sql, insert_params = fake_session.calls[0]
    assert "CAST(:metadata_json AS jsonb)" in insert_sql
    assert ":metadata_json::jsonb" not in insert_sql
    assert "EXCLUDED.metadata_json::jsonb" not in insert_sql
    assert json.loads(insert_params["metadata_json"]) == {"captions_available": True}
