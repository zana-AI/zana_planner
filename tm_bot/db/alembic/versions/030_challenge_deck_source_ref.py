"""Add challenge_decks.source_ref — provenance of the deck's source content

Lets automated ingestion (e.g. the Atena daily-quiz pipeline) dedupe against
lessons already turned into a deck, without re-scraping/re-parsing history.

Revision ID: 030_challenge_deck_source_ref
Revises: 029_club_external_url
Create Date: 2026-07-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "030_challenge_deck_source_ref"
down_revision: Union[str, None] = "029_club_external_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("challenge_decks", sa.Column("source_ref", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("challenge_decks", "source_ref")
