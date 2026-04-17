"""Add media fields to broadcasts

Revision ID: 017_add_broadcast_media_fields
Revises: 016_club_admin_reminder_tracking
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "017_add_broadcast_media_fields"
down_revision: Union[str, None] = "016_club_admin_reminder_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("broadcasts", sa.Column("media_type", sa.Text(), nullable=True))
    op.add_column("broadcasts", sa.Column("media_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("broadcasts", "media_url")
    op.drop_column("broadcasts", "media_type")
