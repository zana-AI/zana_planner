"""Add Telegram setup fields to clubs

Revision ID: 015_club_telegram_setup
Revises: 014_plan_sessions_notified_at
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op


revision: str = "015_club_telegram_setup"
down_revision: Union[str, None] = "014_plan_sessions_notified_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE clubs ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'")
    op.execute("ALTER TABLE clubs ADD COLUMN IF NOT EXISTS telegram_status TEXT NOT NULL DEFAULT 'not_connected'")
    op.execute("ALTER TABLE clubs ADD COLUMN IF NOT EXISTS telegram_invite_link TEXT")
    op.execute("ALTER TABLE clubs ADD COLUMN IF NOT EXISTS telegram_chat_id TEXT")
    op.execute("ALTER TABLE clubs ADD COLUMN IF NOT EXISTS telegram_requested_at_utc TEXT")
    op.execute("ALTER TABLE clubs ADD COLUMN IF NOT EXISTS telegram_ready_at_utc TEXT")
    op.execute("ALTER TABLE clubs ADD COLUMN IF NOT EXISTS telegram_setup_by_admin_id TEXT")


def downgrade() -> None:
    op.drop_column("clubs", "status")
    op.drop_column("clubs", "telegram_setup_by_admin_id")
    op.drop_column("clubs", "telegram_ready_at_utc")
    op.drop_column("clubs", "telegram_requested_at_utc")
    op.drop_column("clubs", "telegram_chat_id")
    op.drop_column("clubs", "telegram_invite_link")
    op.drop_column("clubs", "telegram_status")
