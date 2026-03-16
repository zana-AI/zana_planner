"""Add snoozed_until column to promises table

Revision ID: 015_add_snoozed_until
Revises: 014_plan_sessions_notified_at
Create Date: 2026-03-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "015_add_snoozed_until"
down_revision: Union[str, None] = "014_plan_sessions_notified_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "promises",
        sa.Column("snoozed_until", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("promises", "snoozed_until")
