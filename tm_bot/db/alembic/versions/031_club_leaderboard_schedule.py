"""Add clubs.timezone and clubs.leaderboard_time

clubs.timezone (IANA name, e.g. "Asia/Tehran") lets a club override the UTC
day boundary used for check-ins/streaks and the owner's personal timezone
used for scheduling. NULL preserves current behavior exactly.

clubs.leaderboard_time ("HH:MM", interpreted in clubs.timezone if set, else
the owner's personal timezone) is when the rendered leaderboard image is
sent to the group. NULL disables the feature for that club (opt-in only).

Revision ID: 031_club_leaderboard_schedule
Revises: 030_challenge_deck_source_ref
Create Date: 2026-08-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "031_club_leaderboard_schedule"
down_revision: Union[str, None] = "030_challenge_deck_source_ref"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clubs", sa.Column("timezone", sa.Text(), nullable=True))
    op.add_column("clubs", sa.Column("leaderboard_time", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("clubs", "leaderboard_time")
    op.drop_column("clubs", "timezone")
