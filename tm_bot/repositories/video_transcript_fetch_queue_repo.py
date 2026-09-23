"""Queue video caption cache misses; workers run from residential networks."""
from sqlalchemy import text

from db.postgres_db import get_db_session


class VideoTranscriptFetchQueueRepository:
    def enqueue(self, video_id: str) -> None:
        """Idempotently request a fetch, reopening a previously failed job."""
        from repositories.video_transcript_repo import VideoTranscriptRepository

        cached = VideoTranscriptRepository().get(video_id)
        if cached and cached.get("cues"):
            return
        with get_db_session() as session:
            session.execute(text("""
                INSERT INTO video_transcript_fetch_jobs (video_id, status, priority, available_at)
                VALUES (:video_id, 'queued', 0, now())
                ON CONFLICT (video_id) DO UPDATE SET
                    status = CASE WHEN video_transcript_fetch_jobs.status = 'failed'
                                  THEN 'queued' ELSE video_transcript_fetch_jobs.status END,
                    available_at = CASE WHEN video_transcript_fetch_jobs.status = 'failed'
                                        THEN now() ELSE video_transcript_fetch_jobs.available_at END;
            """), {"video_id": video_id})
