"""
Repository for cached YouTube transcripts (see migration 036_video_transcript).

Read-only in production: the server cannot fetch transcripts itself because
YouTube blocks its IP, so rows arrive from scripts/fetch_transcripts.py run on a
residential connection.
"""
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from db.postgres_db import get_db_session


class VideoTranscriptRepository:
    """PostgreSQL-backed cache of timestamped captions, keyed by YouTube id."""

    def __init__(self) -> None:
        pass

    def get(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Return the cached transcript for a video, or None if we have none."""
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT video_id, language, is_generated, cues, cue_count,
                           duration_seconds, title, source, fetched_at
                    FROM video_transcript WHERE video_id = :video_id;
                """),
                {"video_id": video_id},
            ).mappings().first()

        if not row:
            return None
        cues = row["cues"]
        # psycopg returns JSONB already decoded; tolerate a text column too.
        if isinstance(cues, str):
            cues = json.loads(cues)
        return {
            "available": True,
            "video_id": row["video_id"],
            "language": row["language"],
            "source": "automatic" if row["is_generated"] else "manual",
            "title": row["title"],
            "duration_seconds": row["duration_seconds"],
            "fetched_at": row["fetched_at"].isoformat() if row["fetched_at"] else None,
            "cues": cues or [],
        }

    def upsert(
        self,
        video_id: str,
        cues: List[Dict[str, Any]],
        language: Optional[str] = None,
        is_generated: bool = True,
        title: Optional[str] = None,
        source: str = "youtube_transcript_api",
    ) -> int:
        """Store (or replace) a transcript. Returns the number of cues stored."""
        duration = None
        if cues:
            last = cues[-1]
            duration = float(last.get("end") or last.get("start") or 0) or None

        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO video_transcript (
                        video_id, language, is_generated, cues, cue_count,
                        duration_seconds, title, source, fetched_at
                    ) VALUES (
                        :video_id, :language, :is_generated, CAST(:cues AS JSONB), :cue_count,
                        :duration_seconds, :title, :source, now()
                    )
                    ON CONFLICT (video_id) DO UPDATE SET
                        language = EXCLUDED.language,
                        is_generated = EXCLUDED.is_generated,
                        cues = EXCLUDED.cues,
                        cue_count = EXCLUDED.cue_count,
                        duration_seconds = EXCLUDED.duration_seconds,
                        title = COALESCE(EXCLUDED.title, video_transcript.title),
                        source = EXCLUDED.source,
                        fetched_at = now();
                """),
                {
                    "video_id": video_id,
                    "language": language,
                    "is_generated": is_generated,
                    "cues": json.dumps(cues, ensure_ascii=False),
                    "cue_count": len(cues),
                    "duration_seconds": duration,
                    "title": title,
                    "source": source,
                },
            )
        return len(cues)

    def list_video_ids(self) -> List[str]:
        """Every video we already hold, so ingest can skip them."""
        with get_db_session() as session:
            rows = session.execute(text("SELECT video_id FROM video_transcript;")).fetchall()
        return [r[0] for r in rows]
