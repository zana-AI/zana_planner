"""Add notes column to actions table

Revision ID: 007_add_action_notes
Revises: 006_bot_tokens
Create Date: 2026-01-29

This migration adds:
- notes column to actions table: optional text field for storing notes associated with each action
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '007_add_action_notes'
down_revision: Union[str, None] = '006_bot_tokens'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add notes column to actions table (nullable for backward compatibility)
    op.add_column('actions', sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    # Drop notes column from actions table
    op.drop_column('actions', 'notes')
