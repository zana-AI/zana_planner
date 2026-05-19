"""Add Slack support columns to clubs

Revision ID: 022_add_slack_support
Revises: 021_uc_promise_assign
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "022_add_slack_support"
down_revision: Union[str, None] = "021_uc_promise_assign"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # slack_status: not_connected | pending_setup | ready
    op.add_column("clubs", sa.Column("slack_status", sa.Text(), nullable=True, server_default="not_connected"))
    op.add_column("clubs", sa.Column("slack_workspace_id", sa.Text(), nullable=True))
    op.add_column("clubs", sa.Column("slack_channel_id", sa.Text(), nullable=True))
    # Per-club bot token (stored after OAuth install)
    op.add_column("clubs", sa.Column("slack_bot_token", sa.Text(), nullable=True))
    op.add_column("clubs", sa.Column("slack_team_name", sa.Text(), nullable=True))
    op.add_column("clubs", sa.Column("slack_channel_name", sa.Text(), nullable=True))
    op.add_column("clubs", sa.Column("slack_connected_at_utc", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("clubs", "slack_connected_at_utc")
    op.drop_column("clubs", "slack_channel_name")
    op.drop_column("clubs", "slack_team_name")
    op.drop_column("clubs", "slack_bot_token")
    op.drop_column("clubs", "slack_channel_id")
    op.drop_column("clubs", "slack_workspace_id")
    op.drop_column("clubs", "slack_status")
