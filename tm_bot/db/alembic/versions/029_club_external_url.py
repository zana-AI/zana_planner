"""Add clubs.external_url — the club's primary outbound link (channel / website)

Distinct from telegram_invite_link (the group the bot sits in). Used to point users
to a Telegram channel (e.g. a challenge host's channel) or an external site.

Revision ID: 029_club_external_url
Revises: 028_challenge_source_key_unique
Create Date: 2026-06-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "029_club_external_url"
down_revision: Union[str, None] = "028_challenge_source_key_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clubs", sa.Column("external_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("clubs", "external_url")
