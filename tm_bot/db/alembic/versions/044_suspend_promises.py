"""Allow promises to be paused without changing their dates or history.

Revision ID: 044_suspend_promises
Revises: 043_explore_catalog
"""
from alembic import op
import sqlalchemy as sa


revision = "044_suspend_promises"
down_revision = "043_explore_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("promises", sa.Column("suspended_at_utc", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("promises", "suspended_at_utc")
