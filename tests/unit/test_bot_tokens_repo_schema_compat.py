import pytest

import repositories.bot_tokens_repo as bot_tokens_repo_module
from repositories.bot_tokens_repo import BotTokensRepository


class _FakeSession:
    pass


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.mark.unit
def test_list_bot_tokens_returns_empty_when_table_missing(monkeypatch):
    fake_session = _FakeSession()
    monkeypatch.setattr(
        bot_tokens_repo_module,
        "get_db_session",
        lambda: _FakeSessionContext(fake_session),
    )
    monkeypatch.setattr(
        bot_tokens_repo_module,
        "check_table_exists",
        lambda session, table_name: False,
    )

    repo = BotTokensRepository()
    assert repo.list_bot_tokens(is_active=True) == []


@pytest.mark.unit
def test_get_bot_token_returns_none_when_table_missing(monkeypatch):
    fake_session = _FakeSession()
    monkeypatch.setattr(
        bot_tokens_repo_module,
        "get_db_session",
        lambda: _FakeSessionContext(fake_session),
    )
    monkeypatch.setattr(
        bot_tokens_repo_module,
        "check_table_exists",
        lambda session, table_name: False,
    )

    repo = BotTokensRepository()
    assert repo.get_bot_token("any-token-id") is None


@pytest.mark.unit
def test_create_bot_token_raises_clear_error_when_table_missing(monkeypatch):
    fake_session = _FakeSession()
    monkeypatch.setattr(
        bot_tokens_repo_module,
        "get_db_session",
        lambda: _FakeSessionContext(fake_session),
    )
    monkeypatch.setattr(
        bot_tokens_repo_module,
        "check_table_exists",
        lambda session, table_name: False,
    )

    repo = BotTokensRepository()
    with pytest.raises(RuntimeError, match="missing table 'bot_tokens'"):
        repo.create_bot_token("123:abc")
