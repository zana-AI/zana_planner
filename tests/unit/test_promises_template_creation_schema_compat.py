"""Tests that the promise visibility endpoint handles template creation
correctly on both legacy schema (has canonical_key) and simplified schema
(canonical_key dropped by migration 004).
"""
import pytest

import repositories.templates_repo as templates_repo_module
from repositories.templates_repo import TemplatesRepository


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


class _FakeSession:
    def __init__(self, *, has_canonical_key: bool, has_description: bool):
        self.calls: list = []
        self._has_canonical_key = has_canonical_key
        self._has_description = has_description

    def execute(self, statement, params=None):
        sql = statement.text if hasattr(statement, "text") else str(statement)
        self.calls.append((sql, params or {}))

        if "information_schema.columns" in sql:
            col = (params or {}).get("column_name", "")
            if not col:
                if "'description'" in sql or "= 'description'" in sql or "column_name = 'description'" in sql:
                    col = "description"
                elif "'canonical_key'" in sql or "column_name = 'canonical_key'" in sql:
                    col = "canonical_key"

            if col == "canonical_key" and self._has_canonical_key:
                return _FakeResult(row=(col,))
            if col == "description" and self._has_description:
                return _FakeResult(row=(col,))
            if col == "created_by_user_id":
                return _FakeResult(row=(col,))
            return _FakeResult(row=None)

        return _FakeResult()


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.mark.unit
def test_has_column_detects_canonical_key_presence():
    session = _FakeSession(has_canonical_key=True, has_description=True)
    repo = TemplatesRepository()
    assert repo._has_column(session, "promise_templates", "canonical_key") is True


@pytest.mark.unit
def test_has_column_detects_canonical_key_absence():
    session = _FakeSession(has_canonical_key=False, has_description=True)
    repo = TemplatesRepository()
    assert repo._has_column(session, "promise_templates", "canonical_key") is False


@pytest.mark.unit
def test_create_template_simplified_schema_uses_description_key(monkeypatch):
    """On simplified schema, create_template should write description, not why."""
    fake_session = _FakeSession(has_canonical_key=False, has_description=True)
    monkeypatch.setattr(
        templates_repo_module,
        "get_db_session",
        lambda: _FakeSessionContext(fake_session),
    )

    repo = TemplatesRepository()
    template_data = {
        "title": "Learn Chinese",
        "description": "Track progress on learning Chinese",
        "category": "language",
        "target_value": 3.0,
        "metric_type": "hours",
        "is_active": True,
        "created_by_user_id": "123",
    }
    repo.create_template(template_data)

    insert_calls = [
        (sql, p) for sql, p in fake_session.calls if "INSERT INTO promise_templates" in sql
    ]
    assert len(insert_calls) == 1
    sql, params = insert_calls[0]
    assert "description" in sql
    assert params["description"] == "Track progress on learning Chinese"
    assert "canonical_key" not in sql
    assert "level" not in sql


@pytest.mark.unit
def test_create_template_legacy_schema_maps_description_to_why(monkeypatch):
    """On legacy schema (no 'description' column), create_template should map
    the 'description' input to the 'why' column."""
    fake_session = _FakeSession(has_canonical_key=True, has_description=False)
    monkeypatch.setattr(
        templates_repo_module,
        "get_db_session",
        lambda: _FakeSessionContext(fake_session),
    )

    repo = TemplatesRepository()
    template_data = {
        "title": "Learn Chinese",
        "description": "Track progress on learning Chinese",
        "category": "language",
        "target_value": 3.0,
        "metric_type": "hours",
        "is_active": True,
    }
    repo.create_template(template_data)

    insert_calls = [
        (sql, p) for sql, p in fake_session.calls if "INSERT INTO promise_templates" in sql
    ]
    assert len(insert_calls) == 1
    sql, params = insert_calls[0]
    assert "why" in sql
    assert params.get("why") == "Track progress on learning Chinese"
