"""Discovery privacy and cache tests. Disposable SQLite only; no real DB."""
import json
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from repositories import explore_repo
from services.explore_config import ExploreCatalog
from webapp.routers import explore


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'explore.db'}")

    @event.listens_for(engine, 'connect')
    def functions(connection, _):
        connection.create_function('jsonb_typeof', 1, lambda raw: 'array' if isinstance(json.loads(raw), list) else 'object')
        connection.create_function('jsonb_array_length', 1, lambda raw: len(json.loads(raw)))

    with engine.begin() as session:
        for sql in [
            'CREATE TABLE clubs (club_id TEXT, name TEXT, description TEXT, visibility TEXT, status TEXT)',
            'CREATE TABLE club_members (club_id TEXT, user_id TEXT, status TEXT)',
            'CREATE TABLE video_transcript (video_id TEXT, language TEXT, cues JSON, cue_count INT, duration_seconds REAL)',
            'CREATE TABLE content (metadata_json JSON, canonical_url TEXT, duration_seconds REAL, updated_at TEXT)',
            "INSERT INTO clubs VALUES ('public','Public','Open learning','public','active'),('mine','Mine','Private','private','active'),('other','Other','Secret','private','active'),('old','Old','Archived','public','archived')",
            "INSERT INTO club_members VALUES ('mine','42','active'),('other','42','left'),('old','42','active')",
            "INSERT INTO video_transcript VALUES ('abcdefghijk','fr','[{\"text\":\"Bonjour\"}]',1,80),('empty','en','[]',1,100),('invalid','en','{}',1,100)",
            "INSERT INTO content VALUES ('{\"video_id\":\"abcdefghijk\"}','https://www.youtube.com/watch?v=abcdefghijk',120,'2026-01-01')",
        ]:
            session.execute(text(sql))

    @contextmanager
    def get_session():
        with Session(engine) as session, session.begin():
            yield session

    monkeypatch.setattr(explore_repo, 'get_db_session', get_session)
    yield engine
    engine.dispose()


def test_club_discovery_has_only_public_or_active_memberships_and_no_people(db):
    cards = explore_repo.ExploreRepository().clubs(42)
    assert [card['club_id'] for card in cards] == ['mine', 'public']
    assert bool(cards[0]['joined'])
    assert set(cards[0]) == {'club_id', 'name', 'description', 'joined'}
    assert [card['club_id'] for card in explore_repo.ExploreRepository().clubs(99)] == ['public']


def test_metadata_uses_video_length_not_transcript_length_and_requires_cues(db):
    meta = explore_repo.ExploreRepository().video_metadata(['abcdefghijk', 'empty', 'invalid', 'missing'])
    assert meta['abcdefghijk'] == dict(subtitles_available=True, subtitle_language='fr', duration_seconds=120)
    for video in ('empty', 'invalid', 'missing'):
        assert meta[video]['subtitles_available'] is False
        assert 'duration_seconds' not in meta[video]
    assert explore_repo.ExploreRepository().video_metadata([]) == {}


@pytest.fixture
def client(db, monkeypatch):
    config = ExploreCatalog.model_validate({'categories': [{'id': 'french', 'title': 'French', 'language': 'fr', 'topics': [{'id': 'watch', 'title': 'Watch', 'items': [{'id': 'video', 'title': 'Lesson', 'starter': True, 'duration_seconds': 110, 'creator': 'Example creator', 'native_ref': '/youtube-watch?video_id=abcdefghijk'}]}]}]})
    monkeypatch.setattr(explore.explore_config_loader, 'load', lambda: config)
    app = FastAPI()
    app.include_router(explore.router)
    app.dependency_overrides[explore.get_current_user] = lambda: 42
    with TestClient(app) as http:
        yield http, app, config


def test_response_enrichment_does_not_mutate_shared_catalog(client):
    http, _, config = client
    response = http.get('/api/explore')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
    body = response.json()
    assert body['categories'][0]['topics'][0]['items'][0]['subtitles_available'] is True
    assert body['categories'][0]['topics'][0]['items'][0]['duration_seconds'] == 120
    assert config.categories[0].topics[0].items[0].duration_seconds == 110
    assert 'subtitles_available' not in config.model_dump()['categories'][0]['topics'][0]['items'][0]
    assert body['metadata_available'] and body['clubs_available']


def test_partial_outages_do_not_hide_catalog_or_fabricate_readiness(client, monkeypatch):
    http, _, _ = client
    def fail(*_):
        raise RuntimeError('offline fixture')
    monkeypatch.setattr(explore_repo.ExploreRepository, 'video_metadata', fail)
    monkeypatch.setattr(explore_repo.ExploreRepository, 'clubs', fail)
    body = http.get('/api/explore').json()
    assert body['metadata_available'] is False and body['clubs_available'] is False
    assert body['clubs'] == []
    assert 'subtitles_available' not in body['categories'][0]['topics'][0]['items'][0]


def test_verified_catalog_duration_does_not_imply_cached_captions(client, monkeypatch):
    http, _, _ = client
    monkeypatch.setattr(explore_repo.ExploreRepository, 'video_metadata', lambda *_: {})
    item = http.get('/api/explore').json()['categories'][0]['topics'][0]['items'][0]
    assert item['duration_seconds'] == 110
    assert item['creator'] == 'Example creator'
    assert item['subtitles_available'] is False


def test_discovery_requires_authentication(client):
    http, app, _ = client
    app.dependency_overrides.clear()
    assert http.get('/api/explore').status_code == 401
