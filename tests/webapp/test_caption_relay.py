"""Security and durable-state tests, optionally against an isolated PostgreSQL DB."""
import importlib.util
import os
from contextlib import contextmanager
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from services.caption_models import Completion
from repositories import caption_relay_repo as devices
from repositories import video_transcript_fetch_queue_repo as jobs
from webapp.routers import caption_relay as api

VIDEO = "dQw4w9WgXcQ"
CAPTIONS = {"language": "fr", "is_generated": True, "cues": [{"start": 0, "end": 2, "text": "Bonjour"}]}


@pytest.fixture
def db(monkeypatch):
    url = os.getenv("CAPTION_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set CAPTION_TEST_DATABASE_URL to an isolated caption_relay_test_* database")
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    assert make_url(url).database.startswith("caption_relay_test_"), "Refusing non-test database"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS video_transcript_fetch_jobs,caption_relay_devices,video_transcript CASCADE"))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            for file in ("036_video_transcript.py", "041_video_transcript_fetch_queue.py", "042_caption_relay.py"):
                path = Path(__file__).parents[2] / "tm_bot/db/alembic/versions" / file
                spec = importlib.util.spec_from_file_location("test_migration", path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.upgrade()
    @contextmanager
    def session():
        with Session(engine) as s:
            with s.begin():
                yield s
    monkeypatch.setattr(devices, "get_db_session", session)
    monkeypatch.setattr(jobs, "get_db_session", session)
    yield engine
    engine.dispose()


def paired():
    repo = devices.CaptionRelayRepository()
    code = repo.create("test device", 1)["pairing_code"]
    return repo.pair(code)


def sql(db, statement):
    with db.begin() as c:
        return c.execute(text(statement))


def test_server_first_then_relay_then_atomic_cache(db):
    queue, device = jobs.VideoTranscriptFetchQueueRepository(), paired()
    queue.enqueue(VIDEO)
    queue.enqueue(VIDEO)
    assert queue.claim(device["device_id"]) is None
    server_job = queue.claim()
    assert server_job["video_id"] == VIDEO
    assert queue.claim() is None
    queue.finish(VIDEO, server_job["lease_token"], error="blocked")
    sql(db, "UPDATE caption_relay_devices SET last_claim_at=NULL")
    relay_job = queue.claim(device["device_id"])
    assert relay_job["video_id"] == VIDEO
    queue.finish(VIDEO, relay_job["lease_token"], device["device_id"], CAPTIONS)
    assert queue.status(VIDEO) == "completed"
    queue.enqueue(VIDEO)
    assert queue.claim() is None
    assert sql(db, "SELECT cue_count FROM video_transcript").scalar() == 1
    with pytest.raises(jobs.LeaseLost):
        queue.finish(VIDEO, relay_job["lease_token"], device["device_id"], CAPTIONS)


def test_pairing_is_single_use_expires_and_revokes(db):
    repo = devices.CaptionRelayRepository()
    created = repo.create("Pi", 1)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(repo.pair, [created["pairing_code"]]*2))
    assert sum(r is not None for r in results) == 1
    device = next(r for r in results if r)
    assert repo.authenticate(device["token"]) == device["device_id"]
    assert sql(db, "SELECT token_hash FROM caption_relay_devices").scalar() != device["token"]
    repo.revoke(device["device_id"])
    assert repo.authenticate(device["token"]) is None
    created = repo.create("expired", 1)
    sql(db, "UPDATE caption_relay_devices SET pairing_expires_at=now()-interval '1 second'")
    assert repo.pair(created["pairing_code"]) is None


def test_wrong_device_stale_lease_and_revoked_device_cannot_write(db):
    queue, a, b = jobs.VideoTranscriptFetchQueueRepository(), paired(), paired()
    queue.enqueue(VIDEO)
    cloud = queue.claim()
    queue.finish(VIDEO, cloud["lease_token"], error="blocked")
    job = queue.claim(a["device_id"])
    with pytest.raises(jobs.LeaseLost):
        queue.finish(VIDEO, job["lease_token"], b["device_id"], CAPTIONS)
    sql(db, "UPDATE video_transcript_fetch_jobs SET leased_until=now()-interval '1 second'")
    with pytest.raises(jobs.LeaseLost):
        queue.finish(VIDEO, job["lease_token"], a["device_id"], CAPTIONS)
    new_job = queue.claim(b["device_id"])
    assert new_job["lease_token"] != job["lease_token"]
    devices.CaptionRelayRepository().revoke(b["device_id"])
    with pytest.raises(jobs.LeaseLost):
        queue.finish(VIDEO, new_job["lease_token"], b["device_id"], CAPTIONS)
    assert sql(db, "SELECT count(*) FROM video_transcript").scalar() == 0


def test_crashed_cloud_and_exhausted_relay_do_not_loop(db):
    queue = jobs.VideoTranscriptFetchQueueRepository()
    queue.enqueue(VIDEO)
    queue.claim()
    sql(db, "UPDATE video_transcript_fetch_jobs SET leased_until=now()-interval '1 second'")
    assert queue.claim() is None
    sql(db, "UPDATE video_transcript_fetch_jobs SET attempt_count=3")
    assert queue.claim(paired()["device_id"]) is None
    assert queue.status(VIDEO) == "failed"
    queue.enqueue(VIDEO)
    assert queue.status(VIDEO) == "failed"


def test_two_relays_cannot_claim_same_job(db):
    queue = jobs.VideoTranscriptFetchQueueRepository()
    queue.enqueue(VIDEO)
    cloud = queue.claim()
    queue.finish(VIDEO, cloud["lease_token"], error="blocked")
    identities = [paired()["device_id"], paired()["device_id"]]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(queue.claim, identities))
    assert sum(r is not None for r in results) == 1


def test_cache_wins_and_claim_rate_limited(db):
    queue, device = jobs.VideoTranscriptFetchQueueRepository(), paired()
    assert queue.claim(device["device_id"]) is None
    queue.enqueue(VIDEO)
    cloud = queue.claim()
    queue.finish(VIDEO, cloud["lease_token"], transcript=CAPTIONS)
    assert queue.claim(device["device_id"]) is None
    assert sql(db, "SELECT count(*) FROM video_transcript_fetch_jobs").scalar() == 1


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api.router)
    def admin(authorization=Header(None)):
        if authorization != "Bearer test-admin":
            raise HTTPException(403)
        return 1
    app.dependency_overrides[api.get_admin_user] = admin
    api._attempts.clear()
    return TestClient(app)


def test_api_auth_and_payload_boundaries(db, client):
    assert client.post("/api/caption-relay/claim").status_code == 401
    assert client.post("/api/caption-relay/claim", headers={"Authorization": "Bearer test-admin"}).status_code == 401
    a = paired()
    headers = {"Authorization": "Bearer " + a["token"]}
    assert client.get("/api/caption-relay/devices", headers=headers).status_code == 403
    assert client.post("/api/caption-relay/devices", headers=headers, json={"name": "bad"}).status_code == 403
    assert client.post("/api/caption-relay/claim", headers=headers).status_code == 200
    assert client.post("/api/caption-relay/complete", headers=headers, content=b"x"*2_000_001).status_code == 413
    assert client.post("/api/caption-relay/complete", headers=headers, json={}).status_code == 422
    assert client.post("/api/caption-relay/complete", headers=headers, json={
        "video_id": VIDEO, "lease_token": "x"*43, "transcript": CAPTIONS}).status_code == 409


@pytest.mark.parametrize("cue", [
    {"start": -1, "end": 2, "text": "bad"},
    {"start": 3, "end": 2, "text": "bad"},
    {"start": float("nan"), "end": 2, "text": "bad"},
    {"start": 0, "end": 2, "text": "x"*2001},
    {"start": 0, "end": 2, "text": "\x00"},
])
def test_caption_validation(cue):
    with pytest.raises(ValueError):
        Completion.model_validate({"video_id": VIDEO, "lease_token": "x"*43,
                                   "transcript": {"cues": [cue]}})
