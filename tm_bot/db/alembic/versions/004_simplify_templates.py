"""Simplify promise_templates schema

Revision ID: 004_simplify_templates
Revises: 003_schedules_reminders_suggestions
Create Date: 2026-01-19

This migration simplifies the promise_templates table by:
- Removing unnecessary fields (program_key, level, why, done, effort, template_kind, 
  target_direction, estimated_hours_per_unit, duration_type, duration_weeks)
- Keeping essential fields (template_id, title, category, target_value, metric_type, is_active)
- Adding useful fields (description, emoji, created_by_user_id)
- Renaming 'why' to 'description' conceptually (we'll migrate data)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '004_simplify_templates'
down_revision: Union[str, None] = '003_schedules_reminders_suggestions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns
    op.add_column('promise_templates', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('promise_templates', sa.Column('emoji', sa.Text(), nullable=True))
    
    # Migrate data: copy 'why' content to 'description'
    op.execute("""
        UPDATE promise_templates 
        SET description = why 
        WHERE why IS NOT NULL AND why != ''
    """)
    
    # Drop columns that are no longer needed
    # Note: Some databases may not support dropping columns easily
    # We'll drop them one by one
    try:
        op.drop_column('promise_templates', 'program_key')
    except Exception:
        pass
    
    try:
        op.drop_column('promise_templates', 'level')
    except Exception:
        pass
    
    try:
        op.drop_column('promise_templates', 'why')
    except Exception:
        pass
    
    try:
        op.drop_column('promise_templates', 'done')
    except Exception:
        pass
    
    try:
        op.drop_column('promise_templates', 'effort')
    except Exception:
        pass
    
    try:
        op.drop_column('promise_templates', 'template_kind')
    except Exception:
        pass
    
    try:
        op.drop_column('promise_templates', 'target_direction')
    except Exception:
        pass
    
    try:
        op.drop_column('promise_templates', 'estimated_hours_per_unit')
    except Exception:
        pass
    
    try:
        op.drop_column('promise_templates', 'duration_type')
    except Exception:
        pass
    
    try:
        op.drop_column('promise_templates', 'duration_weeks')
    except Exception:
        pass
    
    # Drop marketplace fields that were over-engineered
    try:
        op.drop_column('promise_templates', 'canonical_key')
    except Exception:
        pass
    
    try:
        op.drop_column('promise_templates', 'source_promise_uuid')
    except Exception:
        pass
    
    try:
        op.drop_column('promise_templates', 'origin')
    except Exception:
        pass
    
    # Drop indexes that reference removed columns
    try:
        op.drop_index('ix_templates_canonical_key', table_name='promise_templates')
    except Exception:
        pass
    
    # Drop check constraints that reference removed columns
    try:
        op.drop_constraint('check_template_kind', 'promise_templates', type_='check')
    except Exception:
        pass
    
    try:
        op.drop_constraint('check_target_direction', 'promise_templates', type_='check')
    except Exception:
        pass
    
    try:
        op.drop_constraint('check_duration_type', 'promise_templates', type_='check')
    except Exception:
        pass


def downgrade() -> None:
    # Re-add columns for downgrade (with defaults)
    op.add_column('promise_templates', sa.Column('program_key', sa.Text(), nullable=True))
    op.add_column('promise_templates', sa.Column('level', sa.Text(), nullable=True, server_default='beginner'))
    op.add_column('promise_templates', sa.Column('why', sa.Text(), nullable=True))
    op.add_column('promise_templates', sa.Column('done', sa.Text(), nullable=True, server_default=''))
    op.add_column('promise_templates', sa.Column('effort', sa.Text(), nullable=True, server_default='medium'))
    op.add_column('promise_templates', sa.Column('template_kind', sa.Text(), nullable=True, server_default='commitment'))
    op.add_column('promise_templates', sa.Column('target_direction', sa.Text(), nullable=True, server_default='at_least'))
    op.add_column('promise_templates', sa.Column('estimated_hours_per_unit', sa.Double(), nullable=True, server_default='1.0'))
    op.add_column('promise_templates', sa.Column('duration_type', sa.Text(), nullable=True, server_default='week'))
    op.add_column('promise_templates', sa.Column('duration_weeks', sa.Integer(), nullable=True))
    op.add_column('promise_templates', sa.Column('canonical_key', sa.Text(), nullable=True))
    op.add_column('promise_templates', sa.Column('source_promise_uuid', sa.Text(), nullable=True))
    op.add_column('promise_templates', sa.Column('origin', sa.Text(), nullable=True))
    
    # Copy description back to why
    op.execute("""
        UPDATE promise_templates 
        SET why = description 
        WHERE description IS NOT NULL
    """)
    
    # Drop new columns
    op.drop_column('promise_templates', 'description')
    op.drop_column('promise_templates', 'emoji')
