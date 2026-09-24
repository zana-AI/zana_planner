"""Offline tests; all persistence is isolated in a disposable SQLite database."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from repositories import browser_login_repo as links
from repositories import auth_session_repo as sessions
from webapp.routers import auth


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'login.db'}")
    with engine.begin() as db:
        db.execute(text('CREATE TABLE auth_sessions (session_token TEXT PRIMARY KEY, user_id TEXT, created_at TEXT, expires_at TEXT, telegram_auth_date INTEGER, auth_method TEXT)'))
        db.execute(text('CREATE TABLE users (user_id TEXT PRIMARY KEY, first_name TEXT, username TEXT)'))
        db.execute(text("INSERT INTO users VALUES ('42', 'Test account', 'test_account')"))

    @contextmanager
    def session():
        with Session(engine) as db, db.begin():
            yield db

    monkeypatch.setattr(links, 'get_db_session', session)
    monkeypatch.setattr(sessions, 'get_db_session', session)
    yield engine
    engine.dispose()


@pytest.fixture
def client(database):
    app = FastAPI()
    app.include_router(auth.router)
    with TestClient(app) as http:
        yield http


def test_link_is_hashed_short_lived_and_not_a_bearer_session(database):
    code = links.BrowserLoginRepository().issue(42)
    with database.connect() as db:
        row = db.execute(text('SELECT * FROM auth_sessions')).mappings().one()
    assert len(code) == 43 and row['session_token'] != code
    assert (sessions._iso_to_dt(row['expires_at']) - sessions._iso_to_dt(row['created_at'])).total_seconds() == 300
    repo = sessions.AuthSessionRepository()
    assert repo.get_session(code) is None
    assert repo.get_session(row['session_token']) is None
    assert repo.get_user_sessions(42) == []


def test_preview_is_non_consuming_and_redemption_is_one_use(client):
    code = links.BrowserLoginRepository().issue(42)
    for _ in range(2):
        response = client.post('/api/auth/browser-login/preview', json={'code': code})
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert response.json() == {'user_id': '42', 'first_name': 'Test account', 'username': 'test_account'}
    body = {'code': code, 'expected_user_id': 42}
    response = client.post('/api/auth/browser-login/redeem', json=body)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    token = response.json()['session_token']
    assert sessions.AuthSessionRepository().get_session(token).user_id == 42
    assert client.post('/api/auth/browser-login/redeem', json=body).status_code == 401
    assert client.post('/api/auth/browser-login/preview', json={'code': code}).status_code == 401


def test_wrong_account_does_not_consume_link(client):
    code = links.BrowserLoginRepository().issue(42)
    assert client.post('/api/auth/browser-login/redeem', json={'code': code, 'expected_user_id': 99}).status_code == 401
    assert client.post('/api/auth/browser-login/redeem', json={'code': code, 'expected_user_id': 42}).status_code == 200


def test_expired_invalid_and_normal_session_tokens_cannot_be_redeemed(client, database):
    code = links.BrowserLoginRepository().issue(42)
    with database.begin() as db:
        db.execute(text("UPDATE auth_sessions SET expires_at='2000-01-01T00:00:00.000000'"))
    assert client.post('/api/auth/browser-login/preview', json={'code': code}).status_code == 401
    assert client.post('/api/auth/browser-login/redeem', json={'code': code, 'expected_user_id': 42}).status_code == 401
    assert client.post('/api/auth/browser-login/preview', json={'code': '!' * 43}).status_code == 422
    token = sessions.AuthSessionRepository().create_session(42, 0).session_token
    assert links.BrowserLoginRepository().redeem(token, 42) is None
    assert sessions.AuthSessionRepository().get_session(token)


def test_new_link_invalidates_old_link_but_not_browser_sessions(database):
    repo = links.BrowserLoginRepository()
    session = sessions.AuthSessionRepository().create_session(42, 0)
    old = repo.issue(42)
    new = repo.issue(42)
    assert repo.preview(old) is None
    assert repo.preview(new)['user_id'] == '42'
    assert sessions.AuthSessionRepository().get_session(session.session_token)


def test_parallel_redemption_has_only_one_winner(database):
    repo = links.BrowserLoginRepository()
    code = repo.issue(42)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: repo.redeem(code, 42), range(2)))
    assert sum(result is not None for result in results) == 1


def test_failed_session_insert_rolls_back_code_consumption(database):
    repo = links.BrowserLoginRepository()
    code = repo.issue(42)
    with database.begin() as db:
        db.execute(text("CREATE TRIGGER fail_new_session BEFORE INSERT ON auth_sessions WHEN NEW.auth_method = 'bot_login' BEGIN SELECT RAISE(ABORT, 'test failure'); END"))
    with pytest.raises(Exception, match='test failure'):
        repo.redeem(code, 42)
    assert repo.preview(code) is not None


@pytest.mark.parametrize('chat_type', ['group', 'supergroup', 'channel'])
def test_bot_does_not_issue_links_in_groups(chat_type, monkeypatch):
    from handlers.browser_login import send_browser_login
    monkeypatch.setattr(links.BrowserLoginRepository, 'issue', lambda *args: pytest.fail('Must not issue a code'))
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(effective_chat=SimpleNamespace(type=chat_type), effective_message=message)
    asyncio.run(send_browser_login(update, 'https://xaana.club'))
    assert 'private chat' in message.reply_text.call_args.args[0]


def test_private_bot_link_uses_verified_sender_and_fragment(database):
    from handlers.browser_login import send_browser_login
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(effective_chat=SimpleNamespace(type='private'), effective_message=message,
                             effective_user=SimpleNamespace(id=42, first_name='Test', is_bot=False))
    asyncio.run(send_browser_login(update, 'https://xaana.club'))
    sent = message.reply_text.call_args.args[0]
    url = next(line for line in sent.splitlines() if line.startswith('https://'))
    parsed = urlparse(url)
    assert parsed.path == '/login' and not parsed.query
    code = parse_qs(parsed.fragment)['code'][0]
    assert links.BrowserLoginRepository().preview(code)['user_id'] == '42'
    assert message.reply_text.call_args.kwargs['disable_web_page_preview'] is True
