"""Tests that InstancesRepository adapts to both legacy and simplified template schemas.

Migration 004 dropped template_kind and target_direction from promise_templates.
The _template_join_fields() helper must return literal defaults when those columns
are absent so that SQL queries and downstream consumers continue to work.
"""
import pytest

import repositories.instances_repo as instances_repo_module
from repositories.instances_repo import InstancesRepository


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


class _FakeSession:
    """Records SQL calls and stubs information_schema lookups."""

    def __init__(self, *, has_template_kind: bool):
        self.calls: list = []
        self._has_template_kind = has_template_kind

    def execute(self, statement, params=None):
        sql = statement.text if hasattr(statement, "text") else str(statement)
        self.calls.append((sql, params or {}))

        if "information_schema.columns" in sql:
            if self._has_template_kind and "template_kind" in sql:
                return _FakeResult(row=("template_kind",))
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
def test_template_join_fields_returns_real_columns_on_legacy_schema():
    session = _FakeSession(has_template_kind=True)
    fields = InstancesRepository._template_join_fields(session)
    assert "t.template_kind" in fields
    assert "t.target_direction" in fields
    assert "'commitment'" not in fields


@pytest.mark.unit
def test_template_join_fields_returns_defaults_on_simplified_schema():
    session = _FakeSession(has_template_kind=False)
    fields = InstancesRepository._template_join_fields(session)
    assert "'commitment' as template_kind" in fields
    assert "'at_least' as target_direction" in fields
    assert "t.template_kind" not in fields


@pytest.mark.unit
def test_list_active_instances_uses_defaults_on_simplified_schema(monkeypatch):
    """Verifies the generated SQL uses literal defaults, not dropped column names."""
    fake_session = _FakeSession(has_template_kind=False)
    monkeypatch.setattr(
        instances_repo_module,
        "get_db_session",
        lambda: _FakeSessionContext(fake_session),
    )

    repo = InstancesRepository()
    repo.list_active_instances(user_id=999)

    sql_calls = [sql for sql, _ in fake_session.calls if "promise_instances" in sql]
    assert len(sql_calls) == 1
    assert "'commitment' as template_kind" in sql_calls[0]
    assert "'at_least' as target_direction" in sql_calls[0]
