"""Add plan_sessions and checklist_items tables

Revision ID: 013_plan_sessions_checklist
Revises: 012_content_learning_pipeline
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "013_plan_sessions_checklist"
down_revision: Union[str, None] = "012_content_learning_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plan_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("promise_uuid", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="planned"),
        sa.Column("planned_start", sa.Text(), nullable=True),
        sa.Column("planned_duration_min", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["promise_uuid"], ["promises.promise_uuid"], ondelete="CASCADE"),
    )
    op.create_index("ix_plan_sessions_promise", "plan_sessions", ["promise_uuid"])
    op.create_index("ix_plan_sessions_user", "plan_sessions", ["user_id"])

    op.create_table(
        "checklist_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["plan_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_checklist_items_session", "checklist_items", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_checklist_items_session", table_name="checklist_items")
    op.drop_table("checklist_items")
    op.drop_index("ix_plan_sessions_user", table_name="plan_sessions")
    op.drop_index("ix_plan_sessions_promise", table_name="plan_sessions")
    op.drop_table("plan_sessions")
