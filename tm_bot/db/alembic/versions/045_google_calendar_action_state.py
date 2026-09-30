"""One-time state for user-initiated Google Calendar additions.

Revision ID: 045_google_calendar_action_state
Revises: 044_suspend_promises
"""
from alembic import op
import sqlalchemy as sa


revision = "045_google_calendar_action_state"
down_revision = "044_suspend_promises"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_calendar_action_state",
        sa.Column("state_digest", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("plan_session_id", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_google_calendar_action_state_expires_at",
        "google_calendar_action_state",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_google_calendar_action_state_expires_at", table_name="google_calendar_action_state")
    op.drop_table("google_calendar_action_state")
