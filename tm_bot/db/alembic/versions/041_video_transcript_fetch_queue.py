"""Queue cache misses for a residential transcript worker.

Revision ID: 041_video_transcript_fetch_queue
Revises: 040_drop_reserve_caretaker
Create Date: 2026-09-23
"""
from alembic import op
import sqlalchemy as sa


revision = "041_video_transcript_fetch_queue"
down_revision = "040_drop_reserve_caretaker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_transcript_fetch_jobs",
        sa.Column("video_id", sa.Text(), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("leased_until", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.CheckConstraint("status IN ('queued', 'processing', 'completed', 'failed')", name="check_video_transcript_job_status"),
    )
    op.create_index(
        "ix_video_transcript_fetch_jobs_ready",
        "video_transcript_fetch_jobs",
        ["priority", "available_at", "requested_at"],
        postgresql_where=sa.text("status = 'queued'"),
    )


def downgrade() -> None:
    op.drop_index("ix_video_transcript_fetch_jobs_ready", table_name="video_transcript_fetch_jobs")
    op.drop_table("video_transcript_fetch_jobs")
