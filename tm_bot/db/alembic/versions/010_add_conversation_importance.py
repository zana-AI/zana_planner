"""Add importance scoring fields to conversations table

Revision ID: 010_add_conversation_importance
Revises: 009_add_focus_timer_fields
Create Date: 2026-01-30

This migration adds:
- conversation_session_id: Groups messages into conversation sessions based on time gaps
- importance_score: LLM-assigned importance score (0-100)
- importance_reasoning: LLM explanation for the score
- intent_category: Categorized intent (e.g., "promise_creation", "action_logging")
- key_themes: Array of key themes extracted from the conversation
- scored_at_utc: Timestamp when the conversation was scored
"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '010_add_conversation_importance'
down_revision: Union[str, None] = '009_add_focus_timer_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add conversation session tracking
    op.add_column('conversations', sa.Column('conversation_session_id', sa.Text(), nullable=True))
    
    # Add importance scoring fields
    op.add_column('conversations', sa.Column('importance_score', sa.Integer(), nullable=True))
    op.add_column('conversations', sa.Column('importance_reasoning', sa.Text(), nullable=True))
    op.add_column('conversations', sa.Column('intent_category', sa.Text(), nullable=True))
    op.add_column('conversations', sa.Column('key_themes', postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column('conversations', sa.Column('scored_at_utc', sa.Text(), nullable=True))
    
    # Create indexes for efficient retrieval
    op.create_index(
        'ix_conversations_user_importance',
        'conversations',
        ['user_id', 'importance_score'],
        postgresql_ops={'importance_score': 'DESC NULLS LAST'}
    )
    op.create_index(
        'ix_conversations_user_session',
        'conversations',
        ['user_id', 'conversation_session_id']
    )
    op.create_index(
        'ix_conversations_user_intent',
        'conversations',
        ['user_id', 'intent_category']
    )
    # Index for finding unscored conversations efficiently
    op.create_index(
        'ix_conversations_unscored',
        'conversations',
        ['user_id'],
        postgresql_where=sa.text('importance_score IS NULL')
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_conversations_unscored', 'conversations')
    op.drop_index('ix_conversations_user_intent', 'conversations')
    op.drop_index('ix_conversations_user_session', 'conversations')
    op.drop_index('ix_conversations_user_importance', 'conversations')
    
    # Drop columns
    op.drop_column('conversations', 'scored_at_utc')
    op.drop_column('conversations', 'key_themes')
    op.drop_column('conversations', 'intent_category')
    op.drop_column('conversations', 'importance_reasoning')
    op.drop_column('conversations', 'importance_score')
    op.drop_column('conversations', 'conversation_session_id')
