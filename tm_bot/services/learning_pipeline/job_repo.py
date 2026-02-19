"""
Repository for content_ingest_job operations.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso
from services.learning_pipeline.constants import PIPELINE_VERSION, STAGE_PROGRESS


class LearningPipelineJobRepository:
    def create_or_reuse_job(
        self,
        user_id: str,
        content_id: str,
        force_rebuild: bool = False,
        pipeline_version: str = PIPELINE_VERSION,
    ) -> Dict[str, Any]:
        user_id = str(user_id)
        content_id = str(content_id)
        now = utc_now_iso()
        with get_db_session() as session:
            existing = session.execute(
                text(
                    """
                    SELECT id, user_id, content_id, pipeline_version, status, stage, attempt_count,
                           error_code, error_detail, created_at, started_at, finished_at, trace_id
                    FROM content_ingest_job
                    WHERE content_id = :content_id AND pipeline_version = :pipeline_version
                    LIMIT 1
                    """
                ),
                {"content_id": content_id, "pipeline_version": pipeline_version},
            ).mappings().fetchone()
            if existing and not force_rebuild:
                if str(existing.get("status") or "").lower() == "failed":
                    session.execute(
                        text(
                            """
                            UPDATE content_ingest_job
                            SET user_id = :user_id,
                                status = 'pending',
                                stage = 'queued',
                                attempt_count = 0,
                                error_code = NULL,
                                error_detail = NULL,
                                created_at = :now,
                                started_at = NULL,
                                finished_at = NULL,
                                trace_id = NULL
                            WHERE id = :job_id
                            """
                        ),
                        {"job_id": existing["id"], "user_id": user_id, "now": now},
                    )
                    refreshed = session.execute(
                        text(
                            """
                            SELECT id, user_id, content_id, pipeline_version, status, stage, attempt_count,
                                   error_code, error_detail, created_at, started_at, finished_at, trace_id
                            FROM content_ingest_job
                            WHERE id = :job_id
                            """
                        ),
                        {"job_id": existing["id"]},
                    ).mappings().fetchone()
                    return _job_to_dict(refreshed)
                return _job_to_dict(existing)

            if existing and force_rebuild:
                session.execute(
                    text(
                        """
                        UPDATE content_ingest_job
                        SET user_id = :user_id,
                            status = 'pending',
                            stage = 'queued',
                            attempt_count = 0,
                            error_code = NULL,
                            error_detail = NULL,
                            created_at = :now,
                            started_at = NULL,
                            finished_at = NULL,
                            trace_id = NULL
                        WHERE id = :job_id
                        """
                    ),
                    {"job_id": existing["id"], "user_id": user_id, "now": now},
                )
                refreshed = session.execute(
                    text(
                        """
                        SELECT id, user_id, content_id, pipeline_version, status, stage, attempt_count,
                               error_code, error_detail, created_at, started_at, finished_at, trace_id
                        FROM content_ingest_job
                        WHERE id = :job_id
                        """
                    ),
                    {"job_id": existing["id"]},
                ).mappings().fetchone()
                return _job_to_dict(refreshed)

            job_id = str(uuid.uuid4())
            session.execute(
                text(
                    """
                    INSERT INTO content_ingest_job (
                        id, user_id, content_id, pipeline_version, status, stage, attempt_count, created_at
                    ) VALUES (
                        :id, :user_id, :content_id, :pipeline_version, 'pending', 'queued', 0, :created_at
                    )
                    """
                ),
                {
                    "id": job_id,
                    "user_id": user_id,
                    "content_id": content_id,
                    "pipeline_version": pipeline_version,
                    "created_at": now,
                },
            )
            created = session.execute(
                text(
                    """
                    SELECT id, user_id, content_id, pipeline_version, status, stage, attempt_count,
                           error_code, error_detail, created_at, started_at, finished_at, trace_id
                    FROM content_ingest_job
                    WHERE id = :job_id
                    """
                ),
                {"job_id": job_id},
            ).mappings().fetchone()
            return _job_to_dict(created)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with get_db_session() as session:
            row = session.execute(
                text(
                    """
                    SELECT id, user_id, content_id, pipeline_version, status, stage, attempt_count,
                           error_code, error_detail, created_at, started_at, finished_at, trace_id
                    FROM content_ingest_job
                    WHERE id = :job_id
                    """
                ),
                {"job_id": str(job_id)},
            ).mappings().fetchone()
        return _job_to_dict(row) if row else None

    def claim_next_pending(self, worker_id: str) -> Optional[Dict[str, Any]]:
        now = utc_now_iso()
        with get_db_session() as session:
            row = session.execute(
                text(
                    """
                    WITH candidate AS (
                        SELECT id
                        FROM content_ingest_job
                        WHERE status = 'pending'
                        ORDER BY created_at ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE content_ingest_job AS j
                    SET status = 'running',
                        stage = CASE WHEN j.stage = 'queued' THEN 'resolve' ELSE j.stage END,
                        started_at = COALESCE(j.started_at, :now),
                        trace_id = :worker_id
                    FROM candidate
                    WHERE j.id = candidate.id
                    RETURNING j.id, j.user_id, j.content_id, j.pipeline_version, j.status, j.stage, j.attempt_count,
                              j.error_code, j.error_detail, j.created_at, j.started_at, j.finished_at, j.trace_id
                    """
                ),
                {"worker_id": worker_id, "now": now},
            ).mappings().fetchone()
        return _job_to_dict(row) if row else None

    def set_stage(self, job_id: str, stage: str) -> None:
        with get_db_session() as session:
            session.execute(
                text(
                    """
                    UPDATE content_ingest_job
                    SET stage = :stage
                    WHERE id = :job_id
                    """
                ),
                {"job_id": str(job_id), "stage": stage},
            )

    def set_attempt_count(self, job_id: str, attempt_count: int) -> None:
        with get_db_session() as session:
            session.execute(
                text(
                    """
                    UPDATE content_ingest_job
                    SET attempt_count = :attempt_count
                    WHERE id = :job_id
                    """
                ),
                {"job_id": str(job_id), "attempt_count": int(attempt_count)},
            )

    def mark_error(self, job_id: str, error_code: str, error_detail: str) -> None:
        with get_db_session() as session:
            session.execute(
                text(
                    """
                    UPDATE content_ingest_job
                    SET error_code = :error_code,
                        error_detail = :error_detail
                    WHERE id = :job_id
                    """
                ),
                {
                    "job_id": str(job_id),
                    "error_code": (error_code or "")[:200],
                    "error_detail": (error_detail or "")[:2000],
                },
            )

    def mark_completed(self, job_id: str) -> None:
        now = utc_now_iso()
        with get_db_session() as session:
            session.execute(
                text(
                    """
                    UPDATE content_ingest_job
                    SET status = 'completed',
                        stage = 'done',
                        finished_at = :finished_at
                    WHERE id = :job_id
                    """
                ),
                {"job_id": str(job_id), "finished_at": now},
            )

    def mark_failed(self, job_id: str, error_code: str, error_detail: str) -> None:
        now = utc_now_iso()
        with get_db_session() as session:
            session.execute(
                text(
                    """
                    UPDATE content_ingest_job
                    SET status = 'failed',
                        error_code = :error_code,
                        error_detail = :error_detail,
                        finished_at = :finished_at
                    WHERE id = :job_id
                    """
                ),
                {
                    "job_id": str(job_id),
                    "error_code": (error_code or "")[:200],
                    "error_detail": (error_detail or "")[:2000],
                    "finished_at": now,
                },
            )

    def mark_running(self, job_id: str) -> None:
        with get_db_session() as session:
            session.execute(
                text(
                    """
                    UPDATE content_ingest_job
                    SET status = 'running'
                    WHERE id = :job_id
                    """
                ),
                {"job_id": str(job_id)},
            )

    def mark_gemini_fallback_used(self, job_id: str) -> None:
        with get_db_session() as session:
            session.execute(
                text(
                    """
                    UPDATE content_ingest_job
                    SET error_code = CASE
                        WHEN error_code IS NULL OR error_code = '' THEN 'gemini_fallback_used'
                        ELSE error_code
                    END
                    WHERE id = :job_id
                    """
                ),
                {"job_id": str(job_id)},
            )

    def release_worker_jobs(self, worker_id: str) -> int:
        with get_db_session() as session:
            result = session.execute(
                text(
                    """
                    UPDATE content_ingest_job
                    SET status = 'pending',
                        stage = 'queued',
                        started_at = NULL,
                        trace_id = NULL
                    WHERE status = 'running'
                      AND trace_id = :worker_id
                    """
                ),
                {"worker_id": worker_id},
            )
            return int(result.rowcount or 0)


def _job_to_dict(row: Any) -> Dict[str, Any]:
    job = dict(row)
    stage = str(job.get("stage") or "queued")
    job["progress_pct"] = STAGE_PROGRESS.get(stage, 0)
    return job
