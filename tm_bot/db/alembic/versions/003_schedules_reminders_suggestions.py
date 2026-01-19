"""Add schedules, reminders, and promise suggestions tables

Revision ID: 003_schedules_reminders_suggestions
Revises: 002_marketplace
Create Date: 2025-01-29

This migration adds tables for per-promise weekly schedules, reminders,
and promise suggestions between users.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '003_schedules_reminders_suggestions'
down_revision: Union[str, None] = '002_marketplace'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Weekly schedule slots (optional rows)
    op.create_table(
        'promise_schedule_weekly_slots',
        sa.Column('slot_id', sa.Text(), nullable=False),
        sa.Column('promise_uuid', sa.Text(), nullable=False),
        sa.Column('weekday', sa.SmallInteger(), nullable=False),
        sa.Column('start_local_time', sa.Time(), nullable=False),
        sa.Column('end_local_time', sa.Time(), nullable=True),
        sa.Column('tz', sa.Text(), nullable=True),
        sa.Column('start_date', sa.Text(), nullable=True),
        sa.Column('end_date', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('updated_at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('slot_id'),
        sa.ForeignKeyConstraint(['promise_uuid'], ['promises.promise_uuid']),
        sa.CheckConstraint("weekday >= 0 AND weekday <= 6", name='check_weekday_range')
    )
    
    # 2) Reminders (slot-derived + fixed-time)
    op.create_table(
        'promise_reminders',
        sa.Column('reminder_id', sa.Text(), nullable=False),
        sa.Column('promise_uuid', sa.Text(), nullable=False),
        sa.Column('slot_id', sa.Text(), nullable=True),
        sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('offset_minutes', sa.Integer(), nullable=True),
        sa.Column('weekday', sa.SmallInteger(), nullable=True),
        sa.Column('time_local', sa.Time(), nullable=True),
        sa.Column('tz', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('last_sent_at_utc', sa.Text(), nullable=True),
        sa.Column('next_run_at_utc', sa.Text(), nullable=True),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('updated_at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('reminder_id'),
        sa.ForeignKeyConstraint(['promise_uuid'], ['promises.promise_uuid']),
        sa.ForeignKeyConstraint(['slot_id'], ['promise_schedule_weekly_slots.slot_id']),
        sa.CheckConstraint("kind IN ('slot_offset', 'fixed_time')", name='check_reminder_kind'),
        sa.CheckConstraint("(weekday IS NULL OR (weekday >= 0 AND weekday <= 6))", name='check_reminder_weekday_range')
    )
    
    # 3) Promise suggestions (invite/accept)
    op.create_table(
        'promise_suggestions',
        sa.Column('suggestion_id', sa.Text(), nullable=False),
        sa.Column('from_user_id', sa.Text(), nullable=False),
        sa.Column('to_user_id', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('template_id', sa.Text(), nullable=True),
        sa.Column('draft_json', sa.Text(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('responded_at_utc', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('suggestion_id'),
        sa.ForeignKeyConstraint(['from_user_id'], ['users.user_id']),
        sa.ForeignKeyConstraint(['to_user_id'], ['users.user_id']),
        sa.ForeignKeyConstraint(['template_id'], ['promise_templates.template_id']),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'declined', 'cancelled')", name='check_suggestion_status')
    )
    
    # Create indexes for efficient queries
    op.create_index('ix_schedule_slots_promise', 'promise_schedule_weekly_slots', ['promise_uuid', 'is_active'])
    op.create_index('ix_reminders_promise', 'promise_reminders', ['promise_uuid', 'enabled'])
    op.create_index('ix_reminders_next_run', 'promise_reminders', ['next_run_at_utc'], postgresql_where=sa.text("enabled = 1 AND next_run_at_utc IS NOT NULL"))
    op.create_index('ix_reminders_slot', 'promise_reminders', ['slot_id'])
    op.create_index('ix_suggestions_to_user', 'promise_suggestions', ['to_user_id', 'status', 'created_at_utc'], postgresql_ops={'created_at_utc': 'DESC'})
    op.create_index('ix_suggestions_from_user', 'promise_suggestions', ['from_user_id', 'status', 'created_at_utc'], postgresql_ops={'created_at_utc': 'DESC'})


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_suggestions_from_user', table_name='promise_suggestions')
    op.drop_index('ix_suggestions_to_user', table_name='promise_suggestions')
    op.drop_index('ix_reminders_slot', table_name='promise_reminders')
    op.drop_index('ix_reminders_next_run', table_name='promise_reminders')
    op.drop_index('ix_reminders_promise', table_name='promise_reminders')
    op.drop_index('ix_schedule_slots_promise', table_name='promise_schedule_weekly_slots')
    
    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table('promise_suggestions')
    op.drop_table('promise_reminders')
    op.drop_table('promise_schedule_weekly_slots')
