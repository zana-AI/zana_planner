"""Add reminder preferences to plan_sessions

Revision ID: 024_plan_session_reminder_preferences
Revises: 023_session_content_link
Create Date: 2026-05-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "024_plan_session_reminder_preferences"
down_revision: Union[str, None] = "023_session_content_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plan_sessions",
        sa.Column("reminder_enabled", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "plan_sessions",
        sa.Column("reminder_offset_min", sa.Integer(), nullable=False, server_default="10"),
    )
    op.create_index(
        "ix_plan_sessions_reminders_due",
        "plan_sessions",
        ["status", "reminder_enabled", "notified_at", "planned_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_plan_sessions_reminders_due", table_name="plan_sessions")
    op.drop_column("plan_sessions", "reminder_offset_min")
    op.drop_column("plan_sessions", "reminder_enabled")
