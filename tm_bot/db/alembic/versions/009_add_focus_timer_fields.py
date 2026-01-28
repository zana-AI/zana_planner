"""Add focus timer fields to sessions table

Revision ID: 009_add_focus_timer_fields
Revises: 008_remove_promise_viz_fields
Create Date: 2026-01-29

This migration adds:
- expected_end_utc: when the timer should complete (ISO datetime string)
- planned_duration_minutes: planned duration in minutes
- timer_kind: "focus" | "break"
- notified_at_utc: when Telegram notification was sent (ISO datetime string, nullable)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '009_add_focus_timer_fields'
down_revision: Union[str, None] = '008_remove_promise_viz_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add focus timer fields to sessions table (all nullable for backward compatibility)
    op.add_column('sessions', sa.Column('expected_end_utc', sa.Text(), nullable=True))
    op.add_column('sessions', sa.Column('planned_duration_minutes', sa.Integer(), nullable=True))
    op.add_column('sessions', sa.Column('timer_kind', sa.Text(), nullable=True))
    op.add_column('sessions', sa.Column('notified_at_utc', sa.Text(), nullable=True))


def downgrade() -> None:
    # Drop focus timer fields from sessions table
    op.drop_column('sessions', 'notified_at_utc')
    op.drop_column('sessions', 'timer_kind')
    op.drop_column('sessions', 'planned_duration_minutes')
    op.drop_column('sessions', 'expected_end_utc')
