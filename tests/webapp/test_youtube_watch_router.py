from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from webapp.routers import youtube_watch as route
from webapp.youtube_watch_stats import create_user_token
from repositories.content_repo import ContentRepository
from repositories.youtube_progress_repo import YoutubeProgressRepository, coverage


def test_transcript_follow_scrolls_only_its_panel():
    html = (Path(__file__).parents[2] / 'tm_bot/webapp/static/youtube_watch.html').read_text(encoding='utf-8')
    assert 'list.scrollTo({top: targetTop' in html
    assert 'button.scrollIntoView' not in html
    assert "localStorage.setItem('telegram_auth_token', sessionToken)" in html
    assert "appDestination + '#session_token=' + encodeURIComponent(sessionToken)" in html


@pytest.fixture
def client(monkeypatch, tmp_path):
    app = FastAPI()
    app.state.bot_token = 'test-token'
    app.state.root_dir = str(tmp_path)
    app.state.auth_session_repo = SimpleNamespace(get_session=lambda token: SimpleNamespace(user_id=42) if token == 'browser-session' else None)
    app.include_router(route.router)
    calls = []
    item = {'id': 'library-alias', 'canonical_url': 'https://youtu.be/du-G1B785Fs?si=abc', 'duration_seconds': 383}
    monkeypatch.setattr(ContentRepository, 'get_content_by_id', lambda self, cid: item)
    monkeypatch.setattr(ContentRepository, 'get_content_by_canonical_url', lambda self, url: item)
    monkeypatch.setattr(ContentRepository, 'can_access_content', lambda self, uid, cid: uid == '42')
    monkeypatch.setattr(YoutubeProgressRepository, 'record', lambda self, *args: calls.append(args) or {'ok': True, 'duplicate': False})
    return TestClient(app), calls


def payload():
    return {'stats': {'report_id': str(uuid.uuid4()), 'video_id': 'du-G1B785Fs',
                     'content_id': 'library-alias', 'duration_seconds': 383,
                     'segments': [[0, 30]], 'promise_id': 'T01'}}


def test_browser_session_saves_actual_library_item_and_duration(client):
    http, calls = client
    result = http.post('/api/youtube/report_stats', json=payload(), headers={'Authorization': 'Bearer browser-session'})
    assert result.status_code == 200
    assert calls[0][0:3] == (42, 'library-alias', 'du-G1B785Fs')
    assert calls[0][4:] == ([[0, 30]], 383, 'T01')


def test_legacy_signed_token_still_works(client):
    http, calls = client
    body = payload()
    body['user_token'] = create_user_token(42, 'test-token')
    assert http.post('/api/youtube/report_stats', json=body).status_code == 200
    assert calls[0][0] == 42


def test_legacy_init_data_still_works(client, monkeypatch):
    monkeypatch.setattr(route, 'validate_init_data', lambda *args: (True, 42))
    http, calls = client
    assert http.post('/api/youtube/report_stats', json=payload()).status_code == 200
    assert calls[0][0] == 42


def test_missing_invalid_auth_and_claimed_user_id_are_rejected(client):
    http, calls = client
    body = payload()
    body['user_id'] = 42
    for headers in ({}, {'Authorization': 'Bearer invalid'}):
        assert http.post('/api/youtube/report_stats', json=body, headers=headers).status_code == 401
    assert calls == []


def test_save_failure_is_not_acknowledged(client, monkeypatch):
    def fail(*args): raise RuntimeError('database down')
    monkeypatch.setattr(YoutubeProgressRepository, 'record', fail)
    assert client[0].post('/api/youtube/report_stats', json=payload(), headers={'Authorization': 'Bearer browser-session'}).status_code == 503


def test_audit_file_failure_does_not_undo_db_save(client, monkeypatch):
    def fail(**kwargs): raise OSError('disk full')
    monkeypatch.setattr(route, 'append_stats', fail)
    assert client[0].post('/api/youtube/report_stats', json=payload(), headers={'Authorization': 'Bearer browser-session'}).status_code == 200


@pytest.mark.parametrize('bad', [{'segments': [[0, -1]]}, {'duration_seconds': 'NaN'}, {'segments': [[0, 'Infinity']]},
                                 {'report_id': 'not-a-uuid'}, {'video_id': 'bad'}, {'segments': 'bad'}])
def test_invalid_reports_rejected(client, bad):
    body = payload()
    body['stats'].update(bad)
    assert client[0].post('/api/youtube/report_stats', json=body, headers={'Authorization': 'Bearer browser-session'}).status_code == 400
    assert client[1] == []


def test_content_video_mismatch_rejected(client):
    body = payload()
    body['stats']['video_id'] = 'q_r7L1wsY2U'
    assert client[0].post('/api/youtube/report_stats', json=body, headers={'Authorization': 'Bearer browser-session'}).status_code == 400


def test_replays_and_seeks_do_not_inflate_unique_coverage():
    assert coverage([[0, 30], [20, 40], [80, 120]], 100) == ([[0, 40], [80, 100]], 60)


def test_load_saved_progress_before_playback(client, monkeypatch):
    reads = []
    monkeypatch.setattr(YoutubeProgressRepository, 'get_progress', lambda _, *args:
                        reads.append(args) or {'duration_seconds': 383, 'segments': [[0, 30]]})
    response = client[0].get('/api/youtube/du-G1B785Fs/progress?content_id=library-alias',
                             headers={'Authorization': 'Bearer browser-session'})
    assert response.status_code == 200
    assert response.json() == {'duration_seconds': 383, 'segments': [[0, 30]]}
    assert response.headers['cache-control'] == 'no-store'
    assert reads == [(42, 'library-alias', 383)]
    assert client[1] == []  # Reading must not create watch events.


def test_progress_read_requires_auth_and_content_access(client, monkeypatch):
    url = '/api/youtube/du-G1B785Fs/progress?content_id=library-alias'
    assert client[0].get(url).status_code == 401
    monkeypatch.setattr(ContentRepository, 'can_access_content', lambda *_: False)
    assert client[0].get(url, headers={'Authorization': 'Bearer browser-session'}).status_code == 403


def test_progress_read_rejects_mismatched_video(client):
    assert client[0].get('/api/youtube/q_r7L1wsY2U/progress?content_id=library-alias',
                         headers={'Authorization': 'Bearer browser-session'}).status_code == 400


def test_progress_missing_content_is_read_only_and_supports_legacy_token(client, monkeypatch):
    monkeypatch.setattr(ContentRepository, 'get_content_by_canonical_url', lambda *_: None)
    response = client[0].get('/api/youtube/du-G1B785Fs/progress',
                             headers={'X-YouTube-User-Token': create_user_token(42, 'test-token')})
    assert response.status_code == 200
    assert response.json() == {'duration_seconds': None, 'segments': []}
    assert client[1] == []
