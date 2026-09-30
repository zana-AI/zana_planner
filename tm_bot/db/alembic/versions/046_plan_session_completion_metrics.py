"""Store user-confirmed session duration and completion time.

Revision ID: 046_plan_session_completion_metrics
Revises: 045_google_calendar_action_state
"""
from alembic import op
import sqlalchemy as sa


revision = "046_plan_session_completion_metrics"
down_revision = "045_google_calendar_action_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plan_sessions", sa.Column("actual_duration_min", sa.Integer(), nullable=True))
    op.add_column("plan_sessions", sa.Column("completed_at_utc", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("plan_sessions", "completed_at_utc")
    op.drop_column("plan_sessions", "actual_duration_min")
