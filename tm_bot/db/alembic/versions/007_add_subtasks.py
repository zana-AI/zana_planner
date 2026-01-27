"""Add subtask support - parent_promise_uuid column

Revision ID: 007_add_subtasks
Revises: 006_bot_tokens
Create Date: 2026-01-22

This migration adds:
- parent_promise_uuid column to promises table: enables hierarchical task structure
- Foreign key constraint linking parent to promise_uuid
- Index on parent_promise_uuid for efficient subtask queries
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '007_add_subtasks'
down_revision: Union[str, None] = '006_bot_tokens'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add parent_promise_uuid column to promises table
    op.add_column('promises', sa.Column('parent_promise_uuid', sa.Text(), nullable=True))
    
    # Add foreign key constraint to ensure parent references valid promise
    op.create_foreign_key(
        'fk_promises_parent',
        'promises', 'promises',
        ['parent_promise_uuid'], ['promise_uuid'],
        ondelete='SET NULL'  # If parent is deleted, set child's parent to NULL
    )
    
    # Add index on parent_promise_uuid for efficient subtask queries
    op.create_index('ix_promises_parent', 'promises', ['parent_promise_uuid'])


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_promises_parent', 'promises')
    
    # Drop foreign key constraint
    op.drop_constraint('fk_promises_parent', 'promises', type_='foreignkey')
    
    # Drop parent_promise_uuid column
    op.drop_column('promises', 'parent_promise_uuid')
