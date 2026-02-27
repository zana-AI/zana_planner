"""Add notified_at column to plan_sessions table

Revision ID: 014_plan_sessions_notified_at
Revises: 013_plan_sessions_checklist
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "014_plan_sessions_notified_at"
down_revision: Union[str, None] = "013_plan_sessions_checklist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plan_sessions",
        sa.Column("notified_at", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plan_sessions", "notified_at")
