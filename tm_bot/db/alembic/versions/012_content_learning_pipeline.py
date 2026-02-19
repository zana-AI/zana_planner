"""Add content-to-learning pipeline schema

Revision ID: 012_content_learning_pipeline
Revises: 011_content_manager
Create Date: 2026-02-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "012_content_learning_pipeline"
down_revision: Union[str, None] = "011_content_manager"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_ingest_job",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("content_id", sa.Text(), nullable=False),
        sa.Column("pipeline_version", sa.Text(), nullable=False, server_default="v1"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("stage", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["content_id"], ["content.id"]),
        sa.UniqueConstraint("content_id", "pipeline_version", name="uq_content_ingest_job_content_pipeline"),
    )
    op.create_index(
        "ix_content_ingest_job_status_created_at",
        "content_ingest_job",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_content_ingest_job_user_created_at",
        "content_ingest_job",
        ["user_id", "created_at"],
    )

    op.create_table(
        "content_asset",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("content_id", sa.Text(), nullable=False),
        sa.Column("asset_type", sa.Text(), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("checksum", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["content_id"], ["content.id"]),
    )
    op.create_index(
        "ix_content_asset_content_type_created",
        "content_asset",
        ["content_id", "asset_type", "created_at"],
    )

    op.create_table(
        "content_segment",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("content_id", sa.Text(), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=True),
        sa.Column("end_ms", sa.BigInteger(), nullable=True),
        sa.Column("section_path", sa.Text(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["content_id"], ["content.id"]),
        sa.UniqueConstraint("content_id", "segment_index", name="uq_content_segment_content_segment_index"),
    )
    op.create_index("ix_content_segment_content_id", "content_segment", ["content_id"])
    op.create_index("ix_content_segment_content_start_ms", "content_segment", ["content_id", "start_ms"])

    op.create_table(
        "content_artifact",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("content_id", sa.Text(), nullable=False),
        sa.Column("artifact_type", sa.Text(), nullable=False),
        sa.Column("artifact_format", sa.Text(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["content_id"], ["content.id"]),
    )
    op.create_index(
        "ix_content_artifact_content_type_created",
        "content_artifact",
        ["content_id", "artifact_type", "created_at"],
    )

    op.create_table(
        "content_concept",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("content_id", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("concept_type", sa.Text(), nullable=True),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column("examples_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("importance_weight", sa.Float(), nullable=False, server_default="0"),
        sa.Column("support_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["content_id"], ["content.id"]),
        sa.UniqueConstraint("content_id", "label", name="uq_content_concept_content_label"),
    )
    op.create_index("ix_content_concept_content_id", "content_concept", ["content_id"])
    op.create_index(
        "ix_content_concept_content_importance",
        "content_concept",
        ["content_id", "importance_weight"],
    )

    op.create_table(
        "content_concept_edge",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("content_id", sa.Text(), nullable=False),
        sa.Column("source_concept_id", sa.Text(), nullable=False),
        sa.Column("target_concept_id", sa.Text(), nullable=False),
        sa.Column("relation_type", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("weight", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["content_id"], ["content.id"]),
        sa.ForeignKeyConstraint(["source_concept_id"], ["content_concept.id"]),
        sa.ForeignKeyConstraint(["target_concept_id"], ["content_concept.id"]),
    )
    op.create_index("ix_content_concept_edge_content_id", "content_concept_edge", ["content_id"])
    op.create_index(
        "ix_content_concept_edge_source_id",
        "content_concept_edge",
        ["source_concept_id"],
    )
    op.create_index(
        "ix_content_concept_edge_target_id",
        "content_concept_edge",
        ["target_concept_id"],
    )

    op.create_table(
        "quiz_set",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("content_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("difficulty", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["content_id"], ["content.id"]),
        sa.UniqueConstraint("content_id", "version", name="uq_quiz_set_content_version"),
    )

    op.create_table(
        "quiz_question",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("quiz_set_id", sa.Text(), nullable=False),
        sa.Column("concept_id", sa.Text(), nullable=True),
        sa.Column("question_type", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.Text(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("answer_key_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("source_segment_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["quiz_set_id"], ["quiz_set.id"]),
        sa.ForeignKeyConstraint(["concept_id"], ["content_concept.id"]),
    )
    op.create_index("ix_quiz_question_set_position", "quiz_question", ["quiz_set_id", "position"])
    op.create_index("ix_quiz_question_concept_id", "quiz_question", ["concept_id"])

    op.create_table(
        "quiz_attempt",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("quiz_set_id", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("max_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.Text(), nullable=True),
        sa.Column("graded_at", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="in_progress"),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["quiz_set_id"], ["quiz_set.id"]),
    )
    op.create_index("ix_quiz_attempt_user_submitted", "quiz_attempt", ["user_id", "submitted_at"])
    op.create_index("ix_quiz_attempt_set_id", "quiz_attempt", ["quiz_set_id"])
    op.create_index(
        "ix_quiz_attempt_user_set_idempotency",
        "quiz_attempt",
        ["user_id", "quiz_set_id", "idempotency_key"],
        unique=True,
    )

    op.create_table(
        "quiz_attempt_answer",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("attempt_id", sa.Text(), nullable=False),
        sa.Column("question_id", sa.Text(), nullable=False),
        sa.Column("user_answer_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("score_awarded", sa.Float(), nullable=False, server_default="0"),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("graded_by_model", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["attempt_id"], ["quiz_attempt.id"]),
        sa.ForeignKeyConstraint(["question_id"], ["quiz_question.id"]),
    )
    op.create_index("ix_quiz_attempt_answer_attempt_id", "quiz_attempt_answer", ["attempt_id"])
    op.create_index("ix_quiz_attempt_answer_question_id", "quiz_attempt_answer", ["question_id"])

    op.create_table(
        "user_concept_mastery",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("concept_id", sa.Text(), nullable=False),
        sa.Column("mastery_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_tested_at", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "concept_id"),
        sa.ForeignKeyConstraint(["concept_id"], ["content_concept.id"]),
    )
    op.create_index(
        "ix_user_concept_mastery_user_score",
        "user_concept_mastery",
        ["user_id", "mastery_score"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_concept_mastery_user_score", "user_concept_mastery")
    op.drop_table("user_concept_mastery")

    op.drop_index("ix_quiz_attempt_answer_question_id", "quiz_attempt_answer")
    op.drop_index("ix_quiz_attempt_answer_attempt_id", "quiz_attempt_answer")
    op.drop_table("quiz_attempt_answer")

    op.drop_index("ix_quiz_attempt_user_set_idempotency", "quiz_attempt")
    op.drop_index("ix_quiz_attempt_set_id", "quiz_attempt")
    op.drop_index("ix_quiz_attempt_user_submitted", "quiz_attempt")
    op.drop_table("quiz_attempt")

    op.drop_index("ix_quiz_question_concept_id", "quiz_question")
    op.drop_index("ix_quiz_question_set_position", "quiz_question")
    op.drop_table("quiz_question")

    op.drop_table("quiz_set")

    op.drop_index("ix_content_concept_edge_target_id", "content_concept_edge")
    op.drop_index("ix_content_concept_edge_source_id", "content_concept_edge")
    op.drop_index("ix_content_concept_edge_content_id", "content_concept_edge")
    op.drop_table("content_concept_edge")

    op.drop_index("ix_content_concept_content_importance", "content_concept")
    op.drop_index("ix_content_concept_content_id", "content_concept")
    op.drop_table("content_concept")

    op.drop_index("ix_content_artifact_content_type_created", "content_artifact")
    op.drop_table("content_artifact")

    op.drop_index("ix_content_segment_content_start_ms", "content_segment")
    op.drop_index("ix_content_segment_content_id", "content_segment")
    op.drop_table("content_segment")

    op.drop_index("ix_content_asset_content_type_created", "content_asset")
    op.drop_table("content_asset")

    op.drop_index("ix_content_ingest_job_user_created_at", "content_ingest_job")
    op.drop_index("ix_content_ingest_job_status_created_at", "content_ingest_job")
    op.drop_table("content_ingest_job")
