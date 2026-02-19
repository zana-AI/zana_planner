"""
Repository for content catalog, user_content, consumption events, and rollup heatmaps.
"""
import json
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso


def _now() -> str:
    return utc_now_iso()


class ContentRepository:
    """PostgreSQL-backed content and user_content repository."""

    def __init__(self) -> None:
        pass

    def upsert_content(
        self,
        canonical_url: str,
        original_url: str,
        provider: str,
        content_type: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        author_channel: Optional[str] = None,
        language: Optional[str] = None,
        published_at: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        estimated_read_seconds: Optional[int] = None,
        thumbnail_url: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Insert or update content by canonical_url; returns content id."""
        now = _now()
        meta = json.dumps(metadata_json or {})
        content_id = str(uuid.uuid4())
        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO content (
                        id, canonical_url, original_url, provider, content_type,
                        title, description, author_channel, language, published_at,
                        duration_seconds, estimated_read_seconds, thumbnail_url,
                        metadata_json, created_at, updated_at
                    ) VALUES (
                        :id, :canonical_url, :original_url, :provider, :content_type,
                        :title, :description, :author_channel, :language, :published_at,
                        :duration_seconds, :estimated_read_seconds, :thumbnail_url,
                        CAST(:metadata_json AS jsonb), :created_at, :updated_at
                    )
                    ON CONFLICT (canonical_url) DO UPDATE SET
                        original_url = EXCLUDED.original_url,
                        provider = EXCLUDED.provider,
                        content_type = EXCLUDED.content_type,
                        title = COALESCE(EXCLUDED.title, content.title),
                        description = COALESCE(EXCLUDED.description, content.description),
                        author_channel = COALESCE(EXCLUDED.author_channel, content.author_channel),
                        language = COALESCE(EXCLUDED.language, content.language),
                        published_at = COALESCE(EXCLUDED.published_at, content.published_at),
                        duration_seconds = COALESCE(EXCLUDED.duration_seconds, content.duration_seconds),
                        estimated_read_seconds = COALESCE(EXCLUDED.estimated_read_seconds, content.estimated_read_seconds),
                        thumbnail_url = COALESCE(EXCLUDED.thumbnail_url, content.thumbnail_url),
                        metadata_json = COALESCE(EXCLUDED.metadata_json, content.metadata_json),
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "id": content_id,
                    "canonical_url": canonical_url,
                    "original_url": original_url,
                    "provider": provider,
                    "content_type": content_type,
                    "title": title,
                    "description": description,
                    "author_channel": author_channel,
                    "language": language,
                    "published_at": published_at,
                    "duration_seconds": duration_seconds,
                    "estimated_read_seconds": estimated_read_seconds,
                    "thumbnail_url": thumbnail_url,
                    "metadata_json": meta,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            row = session.execute(
                text("SELECT id FROM content WHERE canonical_url = :canonical_url"),
                {"canonical_url": canonical_url},
            ).mappings().fetchone()
            if row:
                content_id = str(row["id"])
        return content_id

    def get_content_by_id(self, content_id: str) -> Optional[Dict[str, Any]]:
        """Return content row as dict or None."""
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT id, canonical_url, original_url, provider, content_type,
                           title, description, author_channel, language, published_at,
                           duration_seconds, estimated_read_seconds, thumbnail_url,
                           metadata_json, created_at, updated_at
                    FROM content WHERE id = :content_id
                """),
                {"content_id": content_id},
            ).mappings().fetchone()
        if not row:
            return None
        return dict(row)

    def get_content_by_canonical_url(self, canonical_url: str) -> Optional[Dict[str, Any]]:
        """Return content row as dict or None."""
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT id, canonical_url, original_url, provider, content_type,
                           title, description, author_channel, language, published_at,
                           duration_seconds, estimated_read_seconds, thumbnail_url,
                           metadata_json, created_at, updated_at
                    FROM content WHERE canonical_url = :canonical_url
                """),
                {"canonical_url": canonical_url},
            ).mappings().fetchone()
        if not row:
            return None
        return dict(row)

    def add_user_content(self, user_id: str, content_id: str) -> str:
        """Add user_content; returns user_content id (existing or new)."""
        uc_id = str(uuid.uuid4())
        now = _now()
        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO user_content (id, user_id, content_id, status, added_at)
                    VALUES (:id, :user_id, :content_id, 'saved', :added_at)
                    ON CONFLICT (user_id, content_id) DO NOTHING
                """),
                {"id": uc_id, "user_id": user_id, "content_id": content_id, "added_at": now},
            )
            row = session.execute(
                text("SELECT id FROM user_content WHERE user_id = :user_id AND content_id = :content_id"),
                {"user_id": user_id, "content_id": content_id},
            ).mappings().fetchone()
            return str(row["id"]) if row else uc_id

    def get_user_content(self, user_id: str, content_id: str) -> Optional[Dict[str, Any]]:
        """Return single user_content row (with content) or None."""
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT uc.id, uc.user_id, uc.content_id, uc.status, uc.added_at, uc.last_interaction_at,
                           uc.completed_at, uc.last_position, uc.position_unit, uc.progress_ratio,
                           uc.total_consumed_seconds, uc.notes, uc.rating
                    FROM user_content uc
                    WHERE uc.user_id = :user_id AND uc.content_id = :content_id
                """),
                {"user_id": user_id, "content_id": content_id},
            ).mappings().fetchone()
        return dict(row) if row else None

    def get_user_contents(
        self,
        user_id: str,
        status: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Return list of joined content + user_content + rollup (cursor = added_at or last_interaction_at)."""
        with get_db_session() as session:
            if status:
                if cursor:
                    rows = session.execute(
                        text("""
                            SELECT c.id AS content_id, c.canonical_url, c.original_url, c.provider, c.content_type,
                                   c.title, c.description, c.author_channel, c.language, c.published_at,
                                   c.duration_seconds, c.estimated_read_seconds, c.thumbnail_url, c.metadata_json,
                                   uc.id AS user_content_id, uc.status, uc.added_at, uc.last_interaction_at,
                                   uc.completed_at, uc.last_position, uc.position_unit, uc.progress_ratio,
                                   uc.total_consumed_seconds, uc.notes, uc.rating,
                                   r.bucket_count, r.buckets
                            FROM user_content uc
                            JOIN content c ON c.id = uc.content_id
                            LEFT JOIN user_content_rollup r ON r.user_id = uc.user_id AND r.content_id = uc.content_id
                            WHERE uc.user_id = :user_id AND uc.status = :status
                              AND (uc.last_interaction_at IS NOT NULL AND uc.last_interaction_at < :cursor
                                   OR uc.last_interaction_at IS NULL AND uc.added_at < :cursor)
                            ORDER BY uc.last_interaction_at DESC NULLS LAST, uc.added_at DESC
                            LIMIT :limit
                        """),
                        {"user_id": user_id, "status": status, "cursor": cursor, "limit": limit},
                    ).mappings().fetchall()
                else:
                    rows = session.execute(
                        text("""
                            SELECT c.id AS content_id, c.canonical_url, c.original_url, c.provider, c.content_type,
                                   c.title, c.description, c.author_channel, c.language, c.published_at,
                                   c.duration_seconds, c.estimated_read_seconds, c.thumbnail_url, c.metadata_json,
                                   uc.id AS user_content_id, uc.status, uc.added_at, uc.last_interaction_at,
                                   uc.completed_at, uc.last_position, uc.position_unit, uc.progress_ratio,
                                   uc.total_consumed_seconds, uc.notes, uc.rating,
                                   r.bucket_count, r.buckets
                            FROM user_content uc
                            JOIN content c ON c.id = uc.content_id
                            LEFT JOIN user_content_rollup r ON r.user_id = uc.user_id AND r.content_id = uc.content_id
                            WHERE uc.user_id = :user_id AND uc.status = :status
                            ORDER BY uc.last_interaction_at DESC NULLS LAST, uc.added_at DESC
                            LIMIT :limit
                        """),
                        {"user_id": user_id, "status": status, "limit": limit},
                    ).mappings().fetchall()
            else:
                if cursor:
                    rows = session.execute(
                        text("""
                            SELECT c.id AS content_id, c.canonical_url, c.original_url, c.provider, c.content_type,
                                   c.title, c.description, c.author_channel, c.language, c.published_at,
                                   c.duration_seconds, c.estimated_read_seconds, c.thumbnail_url, c.metadata_json,
                                   uc.id AS user_content_id, uc.status, uc.added_at, uc.last_interaction_at,
                                   uc.completed_at, uc.last_position, uc.position_unit, uc.progress_ratio,
                                   uc.total_consumed_seconds, uc.notes, uc.rating,
                                   r.bucket_count, r.buckets
                            FROM user_content uc
                            JOIN content c ON c.id = uc.content_id
                            LEFT JOIN user_content_rollup r ON r.user_id = uc.user_id AND r.content_id = uc.content_id
                            WHERE uc.user_id = :user_id
                              AND (uc.last_interaction_at IS NOT NULL AND uc.last_interaction_at < :cursor
                                   OR uc.last_interaction_at IS NULL AND uc.added_at < :cursor)
                            ORDER BY uc.last_interaction_at DESC NULLS LAST, uc.added_at DESC
                            LIMIT :limit
                        """),
                        {"user_id": user_id, "cursor": cursor, "limit": limit},
                    ).mappings().fetchall()
                else:
                    rows = session.execute(
                        text("""
                            SELECT c.id AS content_id, c.canonical_url, c.original_url, c.provider, c.content_type,
                                   c.title, c.description, c.author_channel, c.language, c.published_at,
                                   c.duration_seconds, c.estimated_read_seconds, c.thumbnail_url, c.metadata_json,
                                   uc.id AS user_content_id, uc.status, uc.added_at, uc.last_interaction_at,
                                   uc.completed_at, uc.last_position, uc.position_unit, uc.progress_ratio,
                                   uc.total_consumed_seconds, uc.notes, uc.rating,
                                   r.bucket_count, r.buckets
                            FROM user_content uc
                            JOIN content c ON c.id = uc.content_id
                            LEFT JOIN user_content_rollup r ON r.user_id = uc.user_id AND r.content_id = uc.content_id
                            WHERE uc.user_id = :user_id
                            ORDER BY uc.last_interaction_at DESC NULLS LAST, uc.added_at DESC
                            LIMIT :limit
                        """),
                        {"user_id": user_id, "limit": limit},
                    ).mappings().fetchall()
        return [dict(r) for r in rows]

    def update_user_content_progress(
        self,
        user_id: str,
        content_id: str,
        last_position: Optional[float] = None,
        position_unit: Optional[str] = None,
        progress_ratio: Optional[float] = None,
        status: Optional[str] = None,
        total_consumed_seconds: Optional[float] = None,
        completed_at: Optional[str] = None,
    ) -> None:
        """Update user_content progress fields."""
        now = _now()
        with get_db_session() as session:
            session.execute(
                text("""
                    UPDATE user_content
                    SET last_interaction_at = :now,
                        last_position = COALESCE(:last_position, last_position),
                        position_unit = COALESCE(:position_unit, position_unit),
                        progress_ratio = COALESCE(:progress_ratio, progress_ratio),
                        status = COALESCE(:status, status),
                        total_consumed_seconds = COALESCE(:total_consumed_seconds, total_consumed_seconds),
                        completed_at = COALESCE(:completed_at, completed_at)
                    WHERE user_id = :user_id AND content_id = :content_id
                """),
                {
                    "user_id": user_id,
                    "content_id": content_id,
                    "now": now,
                    "last_position": last_position,
                    "position_unit": position_unit,
                    "progress_ratio": progress_ratio,
                    "status": status,
                    "total_consumed_seconds": total_consumed_seconds,
                    "completed_at": completed_at,
                },
            )

    def update_user_content_meta(
        self,
        user_id: str,
        content_id: str,
        status: Optional[str] = None,
        notes: Optional[str] = None,
        rating: Optional[int] = None,
    ) -> None:
        """Update user_content status, notes, rating."""
        with get_db_session() as session:
            session.execute(
                text("""
                    UPDATE user_content
                    SET status = COALESCE(:status, status),
                        notes = COALESCE(:notes, notes),
                        rating = COALESCE(:rating, rating)
                    WHERE user_id = :user_id AND content_id = :content_id
                """),
                {"user_id": user_id, "content_id": content_id, "status": status, "notes": notes, "rating": rating},
            )

    def insert_consumption_event(
        self,
        user_id: str,
        content_id: str,
        start_pos: float,
        end_pos: float,
        unit: str,
        started_at: Optional[str] = None,
        ended_at: Optional[str] = None,
        client: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> str:
        """Insert content_consumption_event; returns event id."""
        event_id = str(uuid.uuid4())
        now = _now()
        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO content_consumption_event (
                        id, user_id, content_id, event_type, start_position, end_position,
                        position_unit, started_at, ended_at, client, device_id, created_at
                    ) VALUES (
                        :id, :user_id, :content_id, 'consume', :start_position, :end_position,
                        :position_unit, :started_at, :ended_at, :client, :device_id, :created_at
                    )
                """),
                {
                    "id": event_id,
                    "user_id": user_id,
                    "content_id": content_id,
                    "start_position": start_pos,
                    "end_position": end_pos,
                    "position_unit": unit,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "client": client,
                    "device_id": device_id,
                    "created_at": now,
                },
            )
        return event_id

    def get_or_create_rollup(self, user_id: str, content_id: str, bucket_count: int = 120) -> Dict[str, Any]:
        """Get or create user_content_rollup; buckets is list of ints."""
        now = _now()
        empty_buckets = json.dumps([0] * bucket_count)
        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO user_content_rollup (user_id, content_id, bucket_count, buckets, updated_at)
                    VALUES (:user_id, :content_id, :bucket_count, :buckets::jsonb, :updated_at)
                    ON CONFLICT (user_id, content_id) DO NOTHING
                """),
                {"user_id": user_id, "content_id": content_id, "bucket_count": bucket_count, "buckets": empty_buckets, "updated_at": now},
            )
            row = session.execute(
                text("SELECT user_id, content_id, bucket_count, buckets, updated_at FROM user_content_rollup WHERE user_id = :user_id AND content_id = :content_id"),
                {"user_id": user_id, "content_id": content_id},
            ).mappings().fetchone()
        if not row:
            return {"user_id": user_id, "content_id": content_id, "bucket_count": bucket_count, "buckets": [0] * bucket_count, "updated_at": now}
        buckets = row["buckets"] if isinstance(row["buckets"], list) else json.loads(row["buckets"]) if isinstance(row["buckets"], str) else []
        return {"user_id": str(row["user_id"]), "content_id": str(row["content_id"]), "bucket_count": int(row["bucket_count"]), "buckets": buckets, "updated_at": str(row["updated_at"])}

    def update_rollup_buckets(self, user_id: str, content_id: str, buckets: List[int], updated_at: str) -> None:
        """Update rollup buckets (list of ints)."""
        buckets_json = json.dumps(buckets)
        with get_db_session() as session:
            session.execute(
                text("""
                    UPDATE user_content_rollup SET buckets = :buckets::jsonb, updated_at = :updated_at
                    WHERE user_id = :user_id AND content_id = :content_id
                """),
                {"user_id": user_id, "content_id": content_id, "buckets": buckets_json, "updated_at": updated_at},
            )

    def get_heatmap(self, user_id: str, content_id: str) -> Optional[Dict[str, Any]]:
        """Return bucket_count and buckets for content heatmap."""
        with get_db_session() as session:
            row = session.execute(
                text("SELECT bucket_count, buckets FROM user_content_rollup WHERE user_id = :user_id AND content_id = :content_id"),
                {"user_id": user_id, "content_id": content_id},
            ).mappings().fetchone()
        if not row:
            return None
        buckets = row["buckets"] if isinstance(row["buckets"], list) else json.loads(row["buckets"]) if isinstance(row["buckets"], str) else []
        return {"bucket_count": int(row["bucket_count"]), "buckets": buckets}
