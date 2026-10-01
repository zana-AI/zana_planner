"""Run only against an explicit disposable DB; every test uses rolled-back temp tables."""
from contextlib import contextmanager
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from repositories import youtube_progress_repo as module


@pytest.fixture
def db(monkeypatch):
    url = os.environ.get('WATCH_PROGRESS_TEST_URL')
    if not url:
        pytest.skip('Explicit disposable PostgreSQL database required')
    # App imports may load the local preview's read-only PGOPTIONS. This URL
    # explicitly names a disposable test database with rolled-back temp tables.
    engine = create_engine(url, connect_args={'options': '-c default_transaction_read_only=off'})
    with engine.connect() as conn:
        transaction = conn.begin()
        definitions = {
            'content': 'id text PRIMARY KEY, canonical_url text UNIQUE, original_url text, provider text, content_type text, created_at text, updated_at text, duration_seconds float, title text, description text, author_channel text, language text, published_at text, estimated_read_seconds int, thumbnail_url text, metadata_json jsonb, owner_user_id text, visibility text, club_id text',
            'user_content': 'id text PRIMARY KEY, user_id text, content_id text, status text, added_at text, last_interaction_at text, last_position float, position_unit text, progress_ratio float, total_consumed_seconds float, completed_at text, assigned_promise_id text, assigned_at text, UNIQUE(user_id,content_id)',
            'content_consumption_event': 'id text PRIMARY KEY, user_id text, content_id text, event_type text, start_position float, end_position float, position_unit text, client text, created_at text',
            'user_content_rollup': 'user_id text, content_id text, bucket_count int, buckets jsonb, updated_at text, PRIMARY KEY(user_id,content_id)',
            'actions': 'action_uuid text PRIMARY KEY, user_id text, promise_uuid text, promise_id_text text, action_type text, time_spent_hours float, at_utc text, notes text',
            'users': 'user_id text PRIMARY KEY, first_name text, username text, avatar_visibility text, avatar_path text',
            'clubs': 'club_id text PRIMARY KEY, status text, name text, telegram_chat_id text, telegram_status text, language text',
            'club_members': 'club_id text, user_id text, status text',
            'content_club_shares': "content_id text, club_id text, status text DEFAULT 'pending', created_at timestamptz DEFAULT now(), shared_by text, telegram_message_id bigint, PRIMARY KEY(content_id,club_id)",
        }
        for name, columns in definitions.items():
            conn.execute(text(f'CREATE TEMP TABLE {name} ({columns}) ON COMMIT DROP'))
        session = Session(bind=conn, join_transaction_mode='create_savepoint')
        @contextmanager
        def use_session():
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
        monkeypatch.setattr(module, 'get_db_session', use_session)
        monkeypatch.setattr(module, 'resolve_promise_uuid', lambda *args: 'test-promise')
        conn.execute(text("""INSERT INTO content (id,canonical_url,original_url,provider,content_type,created_at,updated_at)
                             VALUES ('item','https://youtu.be/du-G1B785Fs','url','youtube','video','now','now')"""))
        yield conn, module.YoutubeProgressRepository()
        session.close()
        transaction.rollback()
    engine.dispose()


def report(repo, segments, duration=100, report_id=None, promise=''):
    return repo.record('42', 'item', 'du-G1B785Fs', report_id or str(uuid.uuid4()), segments, duration, promise)


def test_retry_is_atomic_and_logs_task_time_once(db):
    conn, repo = db
    rid = str(uuid.uuid4())
    assert report(repo, [[0, 30]], report_id=rid, promise='T01')['progress_ratio'] == .3
    assert report(repo, [[0, 30]], report_id=rid, promise='T01')['duplicate']
    assert conn.execute(text('SELECT count(*) FROM content_consumption_event')).scalar() == 1
    assert conn.execute(text('SELECT count(*) FROM actions')).scalar() == 1
    assert conn.execute(text('SELECT duration_seconds FROM content')).scalar() == 100
    assert conn.execute(text('SELECT total_consumed_seconds FROM user_content')).scalar() == 30


def test_overlap_gap_completion_and_legacy_progress(db):
    conn, repo = db
    report(repo, [[0, 30]])
    assert report(repo, [[20, 40], [80, 100]])['progress_ratio'] == .6
    assert report(repo, [[40, 80]])['status'] == 'completed'
    assert report(repo, [[0, 1]])['progress_ratio'] == 1


def test_missing_duration_does_not_mark_first_segment_complete(db):
    conn, repo = db
    assert report(repo, [[0, 20]], duration=None)['progress_ratio'] == 0
    assert report(repo, [[20, 30]], duration=100)['progress_ratio'] == .3


def test_saved_coverage_is_user_scoped_and_replays_remain_in_events(db):
    conn, repo = db
    report(repo, [[0, 30], [10, 20], [80, 100]])
    assert repo.get_progress('42', 'item', 100) == {
        'duration_seconds': 100, 'segments': [[0, 30], [80, 100]]}
    assert repo.get_progress('other-user', 'item', 100)['segments'] == []
    assert conn.execute(text('SELECT count(*) FROM content_consumption_event')).scalar() == 3
    assert conn.execute(text('SELECT total_consumed_seconds FROM user_content')).scalar() == 60


def test_failure_rolls_back_events_and_receipt_for_retry(db, monkeypatch):
    conn, repo = db
    rid = str(uuid.uuid4())
    def fail(*args): raise RuntimeError('task lookup unavailable')
    monkeypatch.setattr(module, 'resolve_promise_uuid', fail)
    with pytest.raises(RuntimeError):
        report(repo, [[0, 30]], report_id=rid, promise='T01')
    assert conn.execute(text('SELECT count(*) FROM content_consumption_event')).scalar() == 0
    assert report(repo, [[0, 30]], report_id=rid)['progress_ratio'] == .3


def test_club_watch_without_a_save_gate_is_visible_to_other_members(db, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from repositories import content_repo, content_share_repo
    from webapp.routers import youtube_watch, content as content_routes

    conn, repo = db
    monkeypatch.setattr(content_repo, 'get_db_session', module.get_db_session)
    monkeypatch.setattr(content_share_repo, 'get_db_session', module.get_db_session)
    conn.execute(text("UPDATE content SET visibility='private', owner_user_id='7' WHERE id='item'"))
    conn.execute(text("INSERT INTO users(user_id,first_name) VALUES ('42','AA'),('7','Javad'),('8','Inactive')"))
    conn.execute(text("INSERT INTO clubs(club_id,status) VALUES ('club','active'),('other-club','active')"))
    conn.execute(text("INSERT INTO club_members VALUES ('club','42','active'),('club','7','active'),('club','8','left')"))
    conn.execute(text("INSERT INTO content_club_shares(content_id,club_id,status) VALUES ('item','club','sent')"))
    # AA has membership access, but has never pressed Save or opened club-open.
    assert conn.execute(text("SELECT count(*) FROM user_content WHERE user_id='42'")).scalar() == 0
    app = FastAPI()
    app.state.bot_token = 'test-token'
    app.state.root_dir = str(tmp_path)
    app.state.auth_session_repo = SimpleNamespace(get_session=lambda token:
        SimpleNamespace(user_id=int(token)) if token in {'42','7','8'} else None)
    app.include_router(youtube_watch.router)
    app.include_router(content_routes.router)
    with TestClient(app) as http:
        body = {'stats': {'report_id': str(uuid.uuid4()), 'video_id': 'du-G1B785Fs',
                'content_id': 'item', 'duration_seconds': 100, 'segments': [[0, 12], [40, 45]]}}
        headers = {'Authorization': 'Bearer 42'}
        assert http.post('/api/youtube/report_stats', json=body, headers=headers).status_code == 200
        assert http.post('/api/youtube/report_stats', json=body, headers=headers).json()['duplicate'] is True
        url = '/api/content/item/club-video-progress?club_id=club'
        result = http.get(url, headers={'Authorization': 'Bearer 7'})
        assert result.status_code == 200
        assert result.json()['items'] == [{'user_id':'42', 'name':'AA', 'avatar_path':None, 'segments':[[0,12],[40,45]]}]
        assert http.get(url, headers=headers).json()['items'] == []  # Own bar is already above.
        assert http.get(url).status_code == 401
        assert http.get(url, headers={'Authorization': 'Bearer 8'}).status_code == 403
        assert http.get(url.replace('=club', '=other-club'), headers=headers).status_code == 403
    assert conn.execute(text("SELECT count(*) FROM user_content WHERE user_id='42'")).scalar() == 1
    assert conn.execute(text("SELECT count(*) FROM content_consumption_event WHERE user_id='42'")).scalar() == 2
    assert repo.get_progress('42', 'item', 100)['segments'] == [[0,12],[40,45]]


def test_group_import_resolves_aliases_and_posts_one_club_card(db, monkeypatch):
    import asyncio
    import httpx
    from repositories import content_repo, content_share_repo, clubs_repo
    from services import club_content_ingest_service, content_share_service
    from services.content_service import ContentService

    conn, _ = db
    for repository in [content_repo, content_share_repo, clubs_repo]:
        monkeypatch.setattr(repository, 'get_db_session', module.get_db_session)
    captions = []
    monkeypatch.setattr(content_repo.ContentRepository, 'request_youtube_transcript', lambda _, cid: captions.append(cid))
    monkeypatch.setattr(ContentService, 'process_link', lambda _, url: {
        'title':'French news', 'type':'youtube', 'duration':.2,
        'metadata':{'video_id':'YSHZ9TMvNHc', 'language':'fr'}})
    conn.execute(text("INSERT INTO clubs VALUES ('club','active','French Club','-100123','connected','fa')"))
    conn.execute(text("INSERT INTO club_members VALUES ('club','42','active')"))
    posts = []
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        async def post(self, url, **kwargs):
            posts.append(kwargs['json'])
            return httpx.Response(200, json={'ok':True, 'result':{'message_id':55}})
    monkeypatch.setenv('BOT_TOKEN', 'local-test-token')
    monkeypatch.setattr(content_share_service.httpx, 'AsyncClient', lambda **kwargs: Client())
    results = asyncio.run(club_content_ingest_service.ingest_club_links([
        'https://youtu.be/YSHZ9TMvNHc?si=tracking',
        'https://www.youtube.com/watch?v=YSHZ9TMvNHc&t=30'], 'club', 42))
    assert [item['already_shared'] for item in results] == [False, True]
    assert len(posts) == 1
    assert posts[0]['chat_id'] == '-100123'
    assert posts[0]['photo'].endswith('/YSHZ9TMvNHc/mqdefault.jpg')
    assert 'club_id=club' in posts[0]['reply_markup']['inline_keyboard'][0][0]['url']
    assert posts[0]['reply_markup']['inline_keyboard'][0][0]['text'] == 'باز کردن در زانا'
    assert conn.execute(text("SELECT count(*) FROM user_content WHERE user_id='42'")).scalar() == 1
    share = conn.execute(text('SELECT status,shared_by,telegram_message_id FROM content_club_shares')).one()
    assert tuple(share) == ('sent','42',55)
    assert captions and len(set(captions)) == 1
