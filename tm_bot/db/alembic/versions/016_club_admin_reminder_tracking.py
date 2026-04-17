"""Track club admin reminder timestamps

Revision ID: 016_club_admin_reminder_tracking
Revises: 015_club_telegram_setup
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op


revision: str = "016_club_admin_reminder_tracking"
down_revision: Union[str, None] = "015_club_telegram_setup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE clubs ADD COLUMN IF NOT EXISTS telegram_last_admin_reminder_at_utc TEXT")


def downgrade() -> None:
    op.drop_column("clubs", "telegram_last_admin_reminder_at_utc")
