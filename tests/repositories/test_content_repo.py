"""Content repository tests (PostgreSQL). Require DB at schema head (migration 011+): run scripts/run_migrations.py with DATABASE_URL or DATABASE_URL_STAGING."""
import uuid

import pytest
from sqlalchemy import text

from db.postgres_db import get_db_session
from repositories.content_repo import ContentRepository

pytestmark = [pytest.mark.repo, pytest.mark.requires_postgres]


def test_user_content_roundtrip():
    """user_content: add, get, update_user_content_meta (notes/rating), get again."""
    repo = ContentRepository()
    user_id = "test-uc-" + uuid.uuid4().hex[:8]
    suffix = uuid.uuid4().hex[:8]
    content_id = repo.upsert_content(
        canonical_url=f"https://example.com/content-repo/{suffix}",
        original_url=f"https://example.com/content-repo/{suffix}",
        provider="test",
        content_type="text",
        title="User content test",
        description="For test_user_content_roundtrip",
    )

    uc_id = repo.add_user_content(user_id, content_id)
    assert uc_id

    uc = repo.get_user_content(user_id, content_id)
    assert uc is not None
    assert uc.get("status") == "saved"
    assert uc.get("added_at") is not None
    assert uc.get("content_id") == content_id

    repo.update_user_content_meta(user_id, content_id, notes="My note", rating=5)
    uc2 = repo.get_user_content(user_id, content_id)
    assert uc2 is not None
    assert uc2.get("notes") == "My note"
    assert uc2.get("rating") == 5


def test_insert_consumption_event():
    """content_consumption_event: insert then assert row exists."""
    repo = ContentRepository()
    user_id = "test-evt-" + uuid.uuid4().hex[:8]
    suffix = uuid.uuid4().hex[:8]
    content_id = repo.upsert_content(
        canonical_url=f"https://example.com/consumption/{suffix}",
        original_url=f"https://example.com/consumption/{suffix}",
        provider="test",
        content_type="video",
        title="Consumption event test",
    )
    repo.add_user_content(user_id, content_id)

    event_id = repo.insert_consumption_event(
        user_id=user_id,
        content_id=content_id,
        start_pos=0.0,
        end_pos=0.5,
        unit="ratio",
        started_at="2026-01-10T10:00:00Z",
        ended_at="2026-01-10T10:05:00Z",
        client="test-client",
    )
    assert event_id

    with get_db_session() as session:
        row = session.execute(
            text(
                "SELECT id, user_id, content_id, event_type, start_position, end_position, position_unit, client "
                "FROM content_consumption_event WHERE id = :id"
            ),
            {"id": event_id},
        ).mappings().fetchone()
    assert row is not None
    assert str(row["user_id"]) == user_id
    assert str(row["content_id"]) == content_id
    assert row["event_type"] == "consume"
    assert float(row["start_position"]) == 0.0
    assert float(row["end_position"]) == 0.5
    assert row["position_unit"] == "ratio"
    assert row["client"] == "test-client"


def test_rollup_get_and_update_buckets():
    """user_content_rollup: get_or_create_rollup, update_rollup_buckets, get_heatmap."""
    repo = ContentRepository()
    user_id = "test-rollup-" + uuid.uuid4().hex[:8]
    suffix = uuid.uuid4().hex[:8]
    content_id = repo.upsert_content(
        canonical_url=f"https://example.com/rollup/{suffix}",
        original_url=f"https://example.com/rollup/{suffix}",
        provider="test",
        content_type="text",
        title="Rollup test",
    )
    repo.add_user_content(user_id, content_id)

    rollup = repo.get_or_create_rollup(user_id, content_id, bucket_count=10)
    assert rollup["bucket_count"] == 10
    assert len(rollup["buckets"]) == 10
    assert rollup["buckets"] == [0] * 10

    buckets = [1, 2, 3, 0, 0, 1, 0, 0, 0, 0]
    repo.update_rollup_buckets(user_id, content_id, buckets, "2026-01-10T12:00:00Z")

    heatmap = repo.get_heatmap(user_id, content_id)
    assert heatmap is not None
    assert heatmap["bucket_count"] == 10
    assert heatmap["buckets"] == buckets
