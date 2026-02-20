import uuid

import pytest
from sqlalchemy import text

from db.postgres_db import check_table_exists, get_db_session
from repositories.content_repo import ContentRepository
from services.learning_pipeline.job_repo import LearningPipelineJobRepository
from services.learning_pipeline.learning_repo import LearningPipelineRepository
from services.learning_pipeline.types import SegmentRecord

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

    # quiz_question: assert get_quiz_questions returns created questions
    questions = learning_repo.get_quiz_questions(quiz["quiz_set_id"])
    assert len(questions) == 1
    assert questions[0]["prompt"] == "What is python?"
    assert questions[0].get("options_json") == ["language", "database"]
    question_id = questions[0]["id"]

    # quiz_attempt_answer: finalize_attempt writes answers; get_attempt_report returns them
    learning_repo.finalize_attempt(
        attempt_id=attempt_id,
        score=1.0,
        max_score=1.0,
        answers=[
            {
                "question_id": question_id,
                "user_answer_json": {"selected": "language"},
                "is_correct": True,
                "score_awarded": 1.0,
                "feedback": None,
                "graded_by_model": None,
            }
        ],
    )
    report = learning_repo.get_attempt_report(attempt_id)
    assert report is not None
    assert report["status"] == "graded"
    assert len(report["answers"]) == 1
    assert report["answers"][0]["is_correct"] is True
    assert report["answers"][0]["score_awarded"] == 1.0


def test_learning_repo_segments_and_assets_roundtrip():
    """content_segment and content_asset: replace_segments and add_asset write; list_segments and DB assert."""
    _require_learning_tables()
    content_repo = ContentRepository()
    learning_repo = LearningPipelineRepository()

    suffix = uuid.uuid4().hex
    content_id = content_repo.upsert_content(
        canonical_url=f"https://example.com/segments/{suffix}",
        original_url=f"https://example.com/segments/{suffix}",
        provider="blog",
        content_type="text",
        title="Segments and assets test",
    )

    learning_repo.add_asset(
        content_id=content_id,
        asset_type="transcript",
        storage_uri="gs://test-bucket/segments-assets-test.txt",
        size_bytes=100,
        checksum="abc123",
    )
    segments = [
        SegmentRecord(text="First segment.", section_path="intro", start_ms=0, end_ms=1000),
        SegmentRecord(text="Second segment.", section_path="intro", start_ms=1000, end_ms=2000),
    ]
    inserted = learning_repo.replace_segments(content_id, segments)
    assert len(inserted) == 2
    listed = learning_repo.list_segments(content_id)
    assert len(listed) == 2
    assert listed[0]["text"] == "First segment."
    assert listed[1]["text"] == "Second segment."

    with get_db_session() as session:
        asset_count = session.execute(
            text("SELECT COUNT(*) AS n FROM content_asset WHERE content_id = :content_id"),
            {"content_id": content_id},
        ).scalar()
    assert asset_count == 1


def test_learning_repo_user_concept_mastery_roundtrip():
    """user_concept_mastery: apply_mastery_result upserts; subsequent call updates attempt/correct counts."""
    _require_learning_tables()
    content_repo = ContentRepository()
    learning_repo = LearningPipelineRepository()

    suffix = uuid.uuid4().hex
    content_id = content_repo.upsert_content(
        canonical_url=f"https://example.com/mastery/{suffix}",
        original_url=f"https://example.com/mastery/{suffix}",
        provider="blog",
        content_type="text",
        title="Mastery test",
    )
    concept_map = learning_repo.replace_concepts_and_edges(
        content_id=content_id,
        concepts=[{"label": "math", "concept_type": "topic", "definition": "mathematics", "examples": []}],
        edges=[],
    )
    concept_id = concept_map.get("math")
    assert concept_id

    user_id = "2002"
    result1 = learning_repo.apply_mastery_result(user_id, concept_id, "correct")
    assert result1["mastery_score"] is not None
    assert result1["attempt_count"] == 1
    assert result1["correct_count"] == 1

    result2 = learning_repo.apply_mastery_result(user_id, concept_id, "incorrect")
    assert result2["attempt_count"] == 2
    assert result2["correct_count"] == 1
    assert result2["mastery_score"] is not None
