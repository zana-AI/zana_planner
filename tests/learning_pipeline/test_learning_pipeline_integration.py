import uuid

import pytest

from db.postgres_db import check_table_exists, get_db_session
from repositories.content_repo import ContentRepository
from services.learning_pipeline.job_repo import LearningPipelineJobRepository
from services.learning_pipeline.learning_repo import LearningPipelineRepository

pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]


def _require_learning_tables() -> None:
    with get_db_session() as session:
        required = [
            "content_ingest_job",
            "content_segment",
            "content_artifact",
            "content_concept",
            "quiz_set",
            "quiz_question",
            "quiz_attempt",
            "user_concept_mastery",
        ]
        missing = [name for name in required if not check_table_exists(session, name)]
    if missing:
        pytest.skip(f"Learning pipeline tables missing (run migrations): {', '.join(missing)}")


def test_job_repository_lifecycle_roundtrip():
    _require_learning_tables()
    content_repo = ContentRepository()
    job_repo = LearningPipelineJobRepository()

    suffix = uuid.uuid4().hex
    content_id = content_repo.upsert_content(
        canonical_url=f"https://example.com/learning/{suffix}",
        original_url=f"https://example.com/learning/{suffix}?utm_source=test",
        provider="blog",
        content_type="text",
        title="Learning test",
        description="Sample content for pipeline integration test.",
    )

    job = job_repo.create_or_reuse_job(user_id="1001", content_id=content_id, force_rebuild=True)
    assert job["status"] == "pending"
    claimed = job_repo.claim_next_pending(worker_id="worker-test")
    assert claimed is not None
    assert claimed["id"] == job["id"]
    assert claimed["status"] == "running"

    job_repo.set_attempt_count(job["id"], 1)
    job_repo.set_stage(job["id"], "fetch")
    job_repo.mark_error(job["id"], "pipeline_error", "simulated error")
    job_repo.mark_failed(job["id"], "pipeline_failed", "simulated final error")
    failed = job_repo.get_job(job["id"])
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["error_code"] in ("pipeline_failed", "gemini_fallback_used")


def test_learning_repo_quiz_idempotency_roundtrip():
    _require_learning_tables()
    content_repo = ContentRepository()
    learning_repo = LearningPipelineRepository()

    suffix = uuid.uuid4().hex
    content_id = content_repo.upsert_content(
        canonical_url=f"https://example.com/quiz/{suffix}",
        original_url=f"https://example.com/quiz/{suffix}",
        provider="blog",
        content_type="text",
        title="Quiz test",
        description="Sample content for quiz integration test.",
    )
    concept_map = learning_repo.replace_concepts_and_edges(
        content_id=content_id,
        concepts=[{"label": "python", "concept_type": "topic", "definition": "a language", "examples": []}],
        edges=[],
    )
    quiz = learning_repo.create_quiz_set(
        content_id=content_id,
        title="Quiz",
        difficulty="easy",
        questions=[
            {
                "position": 1,
                "concept_label": "python",
                "question_type": "mcq",
                "difficulty": "easy",
                "prompt": "What is python?",
                "options": ["language", "database"],
                "answer_key": {"correct_option": "language", "accepted_answers": ["language"]},
                "rationale": "python is a language",
                "source_segment_ids": [],
            }
        ],
        concept_id_by_label=concept_map,
    )
    attempt_id = learning_repo.create_attempt(user_id="1001", quiz_set_id=quiz["quiz_set_id"], idempotency_key="idem-key-1")
    found = learning_repo.find_attempt_by_idempotency("1001", quiz["quiz_set_id"], "idem-key-1")
    assert found is not None
    assert found["id"] == attempt_id
