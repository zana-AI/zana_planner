"""Add marketplace fields to promise_templates and unique constraint on promise_instances

Revision ID: 002_marketplace
Revises: 001_initial
Create Date: 2025-01-29

This migration adds fields to support public promises becoming marketplace templates
and ensures idempotent linking of promises to templates.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002_marketplace'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add marketplace fields to promise_templates
    op.add_column('promise_templates', sa.Column('canonical_key', sa.Text(), nullable=True))
    op.add_column('promise_templates', sa.Column('created_by_user_id', sa.Text(), nullable=True))
    op.add_column('promise_templates', sa.Column('source_promise_uuid', sa.Text(), nullable=True))
    op.add_column('promise_templates', sa.Column('origin', sa.Text(), nullable=True))
    
    # Create index on canonical_key for fast lookups
    op.create_index('ix_templates_canonical_key', 'promise_templates', ['canonical_key'], unique=False)
    
    # Add unique constraint on promise_instances(promise_uuid) to ensure idempotent linking
    # First check if constraint already exists (might be added manually)
    try:
        op.create_unique_constraint(
            'uq_instances_promise_uuid',
            'promise_instances',
            ['promise_uuid']
        )
    except Exception:
        # Constraint might already exist, skip
        pass


def downgrade() -> None:
    # Remove unique constraint
    try:
        op.drop_constraint('uq_instances_promise_uuid', 'promise_instances', type_='unique')
    except Exception:
        pass
    
    # Drop index
    op.drop_index('ix_templates_canonical_key', table_name='promise_templates')
    
    # Remove columns
    op.drop_column('promise_templates', 'origin')
    op.drop_column('promise_templates', 'source_promise_uuid')
    op.drop_column('promise_templates', 'created_by_user_id')
    op.drop_column('promise_templates', 'canonical_key')
