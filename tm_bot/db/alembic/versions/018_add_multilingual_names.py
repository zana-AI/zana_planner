"""Add non_latin_name and latin_name columns to users table

Revision ID: 018_add_multilingual_names
Revises: 017_add_broadcast_media_fields
Create Date: 2026-04-24

Stores curated alternative-script name variants so the bot can recognise
club members regardless of whether a message uses Latin or non-Latin script.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '018_add_multilingual_names'
down_revision: Union[str, None] = '017_add_broadcast_media_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('non_latin_name', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('latin_name', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'latin_name')
    op.drop_column('users', 'non_latin_name')
