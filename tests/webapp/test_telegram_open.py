import hashlib
import hmac
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from webapp.routers.auth import router

TOKEN = 'offline-test-bot-token'
DESTINATION = '/youtube-watch?video_id=YSHZ9TMvNHc&content_id=content&club_id=club&lang=fa'

@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.state.bot_token = TOKEN
    app.state.auth_session_repo = Mock()
    app.state.auth_session_repo.create_session.return_value = SimpleNamespace(session_token='test-session')
    with TestClient(app, follow_redirects=False) as http:
        yield http, app.state.auth_session_repo

def signed(user_id=42, auth_date=None):
    data = {'id': str(user_id), 'first_name': 'Test', 'auth_date': str(auth_date if auth_date is not None else int(time.time()))}
    body = '\n'.join(f'{key}={value}' for key, value in sorted(data.items()))
    data['hash'] = hmac.new(hashlib.sha256(TOKEN.encode()).digest(), body.encode(), hashlib.sha256).hexdigest()
    return {'next': DESTINATION, **data}

def test_signed_click_logs_in_clicker_and_keeps_reader_destination(client):
    http, repo = client
    for uid in (42, 99):
        data = signed(uid)
        response = http.get('/api/auth/telegram-open', params=data)
        assert response.status_code == 303
        assert response.headers['location'] == DESTINATION + '#session_token=test-session'
        assert response.headers['cache-control'] == 'no-store'
        assert response.headers['referrer-policy'] == 'no-referrer'
        assert repo.create_session.call_args.kwargs['user_id'] == uid
    assert repo.create_session.call_count == 2

@pytest.mark.parametrize('change', [
    {'id': '99'}, {'hash': '0' * 64}, {'auth_date': 'bad'}, {'id': '-1'},
])
def test_tampering_never_creates_a_session(client, change):
    http, repo = client
    data = signed()
    data.update(change)
    assert http.get('/api/auth/telegram-open', params=data).status_code == 401
    repo.create_session.assert_not_called()

@pytest.mark.parametrize('offset', [-301, 120])
def test_old_or_future_signed_data_is_rejected(client, offset):
    http, repo = client
    assert http.get('/api/auth/telegram-open', params=signed(auth_date=int(time.time()) + offset)).status_code == 401
    repo.create_session.assert_not_called()

@pytest.mark.parametrize('target', ['https://evil.test/youtube-watch', '//evil.test/youtube-watch', '/youtube-watch#session_token=evil', '/youtube-watch?return_to=https://evil.test', '/\\evil.test/youtube-watch', '/youtube-watch\r\nLocation: evil', '/dashboard'])
def test_redirect_cannot_escape_readers_or_inject_credentials(client, target):
    http, repo = client
    data = signed()
    data['next'] = target
    assert http.get('/api/auth/telegram-open', params=data).status_code == 400
    repo.create_session.assert_not_called()

def test_duplicates_are_rejected(client):
    http, repo = client
    data = list(signed().items()) + [('id', '99')]
    assert http.get('/api/auth/telegram-open', params=data).status_code == 400
    repo.create_session.assert_not_called()

def test_declined_authorization_opens_guest_reader_without_session(client):
    http, repo = client
    response = http.get('/api/auth/telegram-open', params={'next': DESTINATION})
    assert response.status_code == 303
    assert response.headers['location'] == DESTINATION
    repo.create_session.assert_not_called()

def test_pdf_reader_uses_the_same_handoff(client):
    http, repo = client
    data = signed()
    data['next'] = '/pdf-reader?content_id=pdf&club_id=club'
    response = http.get('/api/auth/telegram-open', params=data)
    assert response.status_code == 303
    assert response.headers['location'] == data['next'] + '#session_token=test-session'
