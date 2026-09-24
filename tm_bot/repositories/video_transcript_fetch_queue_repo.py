"""Durable caption queue. Network fetches never hold a database session."""
import json
import re
import secrets

from sqlalchemy import text
from db.postgres_db import get_db_session

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class LeaseLost(Exception):
    pass


class VideoTranscriptFetchQueueRepository:
    def enqueue(self, video_id: str) -> None:
        if not VIDEO_ID.fullmatch(video_id):
            raise ValueError("Invalid YouTube video ID")
        with get_db_session() as session:
            session.execute(text("""
                INSERT INTO video_transcript_fetch_jobs (video_id)
                SELECT :video_id WHERE NOT EXISTS (
                    SELECT 1 FROM video_transcript WHERE video_id=:video_id AND cue_count>0
                ) ON CONFLICT (video_id) DO NOTHING
            """), {"video_id": video_id})

    def status(self, video_id):
        return self.fetch_state(video_id)["status"]

    def fetch_state(self, video_id):
        with get_db_session() as session:
            row = session.execute(text("SELECT status,last_error FROM video_transcript_fetch_jobs WHERE video_id=:id"),
                                  {"id": video_id}).mappings().first()
            return dict(row) if row else {"status": "queued", "last_error": None}

    def claim(self, worker_id=None):
        stage = "relay" if worker_id else "server"
        with get_db_session() as session:
            if worker_id:
                # Serialize claims, completion and revocation for each device.
                device = session.execute(text("""
                    SELECT id FROM caption_relay_devices WHERE id=:id AND token_hash IS NOT NULL
                    AND revoked_at IS NULL FOR UPDATE
                """), {"id": worker_id}).first()
                if not device:
                    raise LeaseLost("Device revoked")
                allowed = session.execute(text("""
                    UPDATE caption_relay_devices SET last_claim_at=now(),last_seen_at=now()
                    WHERE id=:id AND (last_claim_at IS NULL OR last_claim_at<now()-interval '20 seconds')
                    RETURNING id
                """), {"id": worker_id}).first()
                if not allowed:
                    return None
            elif not session.execute(text("SELECT pg_try_advisory_xact_lock(42612042)")).scalar():
                return None

            # Cloud crashes fall through; relay crashes consume a retry.
            session.execute(text("""
                UPDATE video_transcript_fetch_jobs SET status='queued',fetch_stage='relay',
                    worker_id=NULL,lease_token=NULL,leased_until=NULL,available_at=now(),
                    last_error='server_timeout'
                WHERE status='processing' AND fetch_stage='server' AND leased_until<now()
            """))
            session.execute(text("""
                UPDATE video_transcript_fetch_jobs SET status='failed',lease_token=NULL,leased_until=NULL,
                    last_error='attempts_exhausted'
                WHERE fetch_stage='relay' AND attempt_count>=3 AND
                    (status='queued' OR (status='processing' AND leased_until<now()))
            """))
            session.execute(text("""
                UPDATE video_transcript_fetch_jobs j SET status='completed',completed_at=now(),
                    lease_token=NULL,leased_until=NULL
                WHERE j.status IN ('queued','processing') AND EXISTS (
                    SELECT 1 FROM video_transcript t WHERE t.video_id=j.video_id AND t.cue_count>0)
            """))
            active = session.execute(text("""
                SELECT 1 FROM video_transcript_fetch_jobs WHERE status='processing' AND leased_until>now()
                AND ((:stage='server' AND fetch_stage='server') OR (:stage='relay' AND worker_id=:worker)) LIMIT 1
            """), {"stage": stage, "worker": worker_id}).first()
            if active:
                return None
            row = session.execute(text("""
                SELECT video_id FROM video_transcript_fetch_jobs WHERE fetch_stage=:stage AND
                    ((status='queued' AND available_at<=now()) OR (status='processing' AND leased_until<now()))
                ORDER BY priority DESC,requested_at FOR UPDATE SKIP LOCKED LIMIT 1
            """), {"stage": stage}).first()
            if not row:
                return None
            lease = secrets.token_urlsafe(32)
            session.execute(text("""
                UPDATE video_transcript_fetch_jobs SET status='processing',worker_id=:worker,
                    lease_token=:lease,leased_until=now()+interval '3 minutes',
                    attempt_count=attempt_count+CASE WHEN :stage='relay' THEN 1 ELSE 0 END,
                    server_attempted_at=CASE WHEN :stage='server' THEN now() ELSE server_attempted_at END,
                    last_error=NULL WHERE video_id=:id
            """), {"worker": worker_id, "lease": lease, "stage": stage, "id": row[0]})
            return {"video_id": row[0], "lease_token": lease, "lease_seconds": 180}

    def finish(self, video_id, lease_token, worker_id=None, transcript=None, error="fetch_failed"):
        with get_db_session() as session:
            if worker_id:
                if not session.execute(text("""
                    SELECT id FROM caption_relay_devices WHERE id=:id AND revoked_at IS NULL FOR UPDATE
                """), {"id": worker_id}).first():
                    raise LeaseLost("Device revoked")
            job = session.execute(text("""
                SELECT * FROM video_transcript_fetch_jobs WHERE video_id=:id AND status='processing'
                AND lease_token=:lease AND worker_id IS NOT DISTINCT FROM :worker
                AND leased_until>now() FOR UPDATE
            """), {"id": video_id, "lease": lease_token, "worker": worker_id}).mappings().first()
            if not job:
                raise LeaseLost("Job lease expired or no longer owned")
            if transcript:
                cues = transcript["cues"]
                # Cache and completion commit together. An existing cache wins.
                session.execute(text("""
                    INSERT INTO video_transcript (video_id,language,is_generated,cues,cue_count,
                        duration_seconds,source,fetched_at)
                    VALUES (:id,:language,:generated,CAST(:cues AS jsonb),:count,:duration,:source,now())
                    ON CONFLICT (video_id) DO UPDATE SET cues=EXCLUDED.cues,cue_count=EXCLUDED.cue_count,
                        language=EXCLUDED.language,is_generated=EXCLUDED.is_generated,
                        duration_seconds=EXCLUDED.duration_seconds,source=EXCLUDED.source,fetched_at=now()
                    WHERE video_transcript.cue_count=0
                """), {"id": video_id, "language": transcript.get("language"),
                         "generated": transcript.get("is_generated", True), "cues": json.dumps(cues),
                         "count": len(cues), "duration": max(c["end"] for c in cues),
                         "source": "caption_relay" if worker_id else "caption_server"})
                status, delay = "completed", 0
            elif job["fetch_stage"] == "server":
                status, delay = "queued", 0
            else:
                terminal = error in ("no_captions", "unavailable") or job["attempt_count"] >= 3
                status, delay = ("failed" if terminal else "queued"), 60 * 2 ** job["attempt_count"]
            session.execute(text("""
                UPDATE video_transcript_fetch_jobs SET status=:status,fetch_stage='relay',
                    leased_until=NULL,lease_token=NULL,worker_id=NULL,
                    completed_at=CASE WHEN :status='completed' THEN now() ELSE NULL END,
                    available_at=now()+make_interval(secs => :delay),last_error=:error WHERE video_id=:id
            """), {"status": status, "delay": delay, "error": None if transcript else error, "id": video_id})
