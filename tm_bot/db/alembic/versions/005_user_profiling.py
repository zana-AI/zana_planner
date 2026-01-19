"""Add user profiling tables

Revision ID: 005_user_profiling
Revises: 004_simplify_templates
Create Date: 2026-01-20

This migration adds user profiling support:
- user_profile_facts: stores profile field values (status, schedule_type, etc.)
- user_profile_state: tracks pending questions and last question asked
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '005_user_profiling'
down_revision: Union[str, None] = '004_simplify_templates'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # User profile facts table
    op.create_table(
        'user_profile_facts',
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('field_key', sa.Text(), nullable=False),
        sa.Column('value_text', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),  # 'explicit_answer', 'inferred', 'system'
        sa.Column('confidence', sa.Double(), nullable=False),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('updated_at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('user_id', 'field_key'),
        sa.CheckConstraint("source IN ('explicit_answer', 'inferred', 'system')", name='check_profile_source'),
        sa.CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name='check_profile_confidence')
    )
    
    # User profile state table
    op.create_table(
        'user_profile_state',
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('pending_field_key', sa.Text(), nullable=True),
        sa.Column('pending_question_text', sa.Text(), nullable=True),
        sa.Column('pending_asked_at_utc', sa.Text(), nullable=True),
        sa.Column('last_question_asked_at_utc', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('user_id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'])
    )
    
    # Indexes for efficient lookups
    op.create_index('ix_profile_facts_user', 'user_profile_facts', ['user_id'])
    op.create_index('ix_profile_facts_field', 'user_profile_facts', ['user_id', 'field_key'])


def downgrade() -> None:
    op.drop_index('ix_profile_facts_field', 'user_profile_facts')
    op.drop_index('ix_profile_facts_user', 'user_profile_facts')
    op.drop_table('user_profile_state')
    op.drop_table('user_profile_facts')
