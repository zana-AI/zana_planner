"""Add bot_tokens table and update broadcasts

Revision ID: 006_bot_tokens
Revises: 005_user_profiling
Create Date: 2026-01-29

This migration adds:
- bot_tokens table: stores all Telegram bot API keys (current and historical)
- bot_token_id column to broadcasts table: links broadcasts to specific bot tokens
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '006_bot_tokens'
down_revision: Union[str, None] = '005_user_profiling'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create bot_tokens table
    op.create_table(
        'bot_tokens',
        sa.Column('bot_token_id', sa.Text(), nullable=False),
        sa.Column('bot_token', sa.Text(), nullable=False),
        sa.Column('bot_username', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('updated_at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('bot_token_id')
    )
    
    # Add index on is_active for efficient filtering
    op.create_index('ix_bot_tokens_active', 'bot_tokens', ['is_active'])
    
    # Add bot_token_id column to broadcasts table (nullable for backward compatibility)
    op.add_column('broadcasts', sa.Column('bot_token_id', sa.Text(), nullable=True))
    
    # Add foreign key constraint (optional, can be deferred if needed)
    # Note: We'll add this after data migration if needed
    # op.create_foreign_key(
    #     'fk_broadcasts_bot_token',
    #     'broadcasts', 'bot_tokens',
    #     ['bot_token_id'], ['bot_token_id']
    # )


def downgrade() -> None:
    # Drop foreign key constraint if it exists
    try:
        op.drop_constraint('fk_broadcasts_bot_token', 'broadcasts', type_='foreignkey')
    except Exception:
        pass
    
    # Drop bot_token_id column from broadcasts
    op.drop_column('broadcasts', 'bot_token_id')
    
    # Drop index
    op.drop_index('ix_bot_tokens_active', 'bot_tokens')
    
    # Drop bot_tokens table
    op.drop_table('bot_tokens')
