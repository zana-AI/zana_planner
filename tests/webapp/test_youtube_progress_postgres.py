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
    engine = create_engine(url)
    with engine.connect() as conn:
        transaction = conn.begin()
        definitions = {
            'content': 'id text PRIMARY KEY, canonical_url text, original_url text, provider text, content_type text, created_at text, updated_at text, duration_seconds float',
            'user_content': 'id text PRIMARY KEY, user_id text, content_id text, status text, added_at text, last_interaction_at text, last_position float, position_unit text, progress_ratio float, total_consumed_seconds float, completed_at text, assigned_promise_id text, assigned_at text, UNIQUE(user_id,content_id)',
            'content_consumption_event': 'id text PRIMARY KEY, user_id text, content_id text, event_type text, start_position float, end_position float, position_unit text, client text, created_at text',
            'user_content_rollup': 'user_id text, content_id text, bucket_count int, buckets jsonb, updated_at text, PRIMARY KEY(user_id,content_id)',
            'actions': 'action_uuid text PRIMARY KEY, user_id text, promise_uuid text, promise_id_text text, action_type text, time_spent_hours float, at_utc text, notes text',
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


def test_failure_rolls_back_events_and_receipt_for_retry(db, monkeypatch):
    conn, repo = db
    rid = str(uuid.uuid4())
    def fail(*args): raise RuntimeError('task lookup unavailable')
    monkeypatch.setattr(module, 'resolve_promise_uuid', fail)
    with pytest.raises(RuntimeError):
        report(repo, [[0, 30]], report_id=rid, promise='T01')
    assert conn.execute(text('SELECT count(*) FROM content_consumption_event')).scalar() == 0
    assert report(repo, [[0, 30]], report_id=rid)['progress_ratio'] == .3
