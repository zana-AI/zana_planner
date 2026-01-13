"""Initial schema migration from SQLite to PostgreSQL

Revision ID: 001_initial
Revises: 
Create Date: 2025-01-13

This migration creates the complete schema matching SQLite versions 1-8,
adapted for PostgreSQL compatibility.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Schema version tracking table
    op.create_table(
        'schema_version',
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('applied_at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('version')
    )
    
    # V1: Core tables
    op.create_table(
        'users',
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('timezone', sa.Text(), nullable=False),
        sa.Column('nightly_hh', sa.Integer(), nullable=False),
        sa.Column('nightly_mm', sa.Integer(), nullable=False),
        sa.Column('language', sa.Text(), nullable=False),
        sa.Column('voice_mode', sa.Text(), nullable=True),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('updated_at_utc', sa.Text(), nullable=False),
        sa.Column('first_name', sa.Text(), nullable=True),
        sa.Column('username', sa.Text(), nullable=True),
        sa.Column('last_seen_utc', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('user_id')
    )
    
    op.create_table(
        'promises',
        sa.Column('promise_uuid', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('current_id', sa.Text(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('hours_per_week', sa.Double(), nullable=False),
        sa.Column('recurring', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Text(), nullable=True),
        sa.Column('end_date', sa.Text(), nullable=True),
        sa.Column('angle_deg', sa.Integer(), nullable=False),
        sa.Column('radius', sa.Integer(), nullable=False),
        sa.Column('is_deleted', sa.Integer(), nullable=False),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('updated_at_utc', sa.Text(), nullable=False),
        sa.Column('visibility', sa.Text(), nullable=False, server_default='private'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('promise_uuid'),
        sa.UniqueConstraint('user_id', 'current_id', name='uq_promises_user_current')
    )
    
    op.create_table(
        'promise_aliases',
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('alias_id', sa.Text(), nullable=False),
        sa.Column('promise_uuid', sa.Text(), nullable=False),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('user_id', 'alias_id'),
        sa.ForeignKeyConstraint(['promise_uuid'], ['promises.promise_uuid'])
    )
    
    op.create_table(
        'promise_events',
        sa.Column('event_uuid', sa.Text(), nullable=False),
        sa.Column('promise_uuid', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('at_utc', sa.Text(), nullable=False),
        sa.Column('snapshot_json', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('event_uuid'),
        sa.ForeignKeyConstraint(['promise_uuid'], ['promises.promise_uuid'])
    )
    
    op.create_table(
        'actions',
        sa.Column('action_uuid', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('promise_uuid', sa.Text(), nullable=True),
        sa.Column('promise_id_text', sa.Text(), nullable=False),
        sa.Column('action_type', sa.Text(), nullable=False),
        sa.Column('time_spent_hours', sa.Double(), nullable=False),
        sa.Column('at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('action_uuid'),
        sa.ForeignKeyConstraint(['promise_uuid'], ['promises.promise_uuid'])
    )
    
    op.create_table(
        'sessions',
        sa.Column('session_id', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('promise_uuid', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('started_at_utc', sa.Text(), nullable=False),
        sa.Column('ended_at_utc', sa.Text(), nullable=True),
        sa.Column('paused_seconds_total', sa.Integer(), nullable=False),
        sa.Column('last_state_change_at_utc', sa.Text(), nullable=True),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('chat_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('session_id'),
        sa.ForeignKeyConstraint(['promise_uuid'], ['promises.promise_uuid'])
    )
    
    op.create_table(
        'legacy_imports',
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('source_mtime_utc', sa.Text(), nullable=True),
        sa.Column('imported_at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('user_id', 'source')
    )
    
    # V2: Conversations table
    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('chat_id', sa.Text(), nullable=True),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('message_type', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    # V3: Social features - users table already has additional columns from V2
    op.add_column('users', sa.Column('last_name', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('display_name', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('is_private', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('default_promise_visibility', sa.Text(), nullable=False, server_default='private'))
    op.add_column('users', sa.Column('avatar_file_id', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('avatar_file_unique_id', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('avatar_path', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('avatar_updated_at_utc', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('avatar_checked_at_utc', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('avatar_visibility', sa.Text(), nullable=False, server_default='public'))
    
    # V3: Social relationship tables (will be consolidated in V4, but we create user_relationships directly)
    op.create_table(
        'user_relationships',
        sa.Column('source_user_id', sa.Text(), nullable=False),
        sa.Column('target_user_id', sa.Text(), nullable=False),
        sa.Column('relationship_type', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('updated_at_utc', sa.Text(), nullable=False),
        sa.Column('ended_at_utc', sa.Text(), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('source_user_id', 'target_user_id', 'relationship_type'),
        sa.CheckConstraint("source_user_id <> target_user_id", name='check_user_relationships_not_self'),
        sa.CheckConstraint("relationship_type IN ('follow', 'block', 'mute')", name='check_relationship_type'),
        sa.ForeignKeyConstraint(['source_user_id'], ['users.user_id']),
        sa.ForeignKeyConstraint(['target_user_id'], ['users.user_id'])
    )
    
    op.create_table(
        'clubs',
        sa.Column('club_id', sa.Text(), nullable=False),
        sa.Column('owner_user_id', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('visibility', sa.Text(), nullable=False, server_default='private'),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('updated_at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('club_id'),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.user_id'])
    )
    
    op.create_table(
        'club_members',
        sa.Column('club_id', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False, server_default='member'),
        sa.Column('status', sa.Text(), nullable=False, server_default='active'),
        sa.Column('joined_at_utc', sa.Text(), nullable=False),
        sa.Column('left_at_utc', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('club_id', 'user_id'),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.club_id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'])
    )
    
    op.create_table(
        'promise_club_shares',
        sa.Column('promise_uuid', sa.Text(), nullable=False),
        sa.Column('club_id', sa.Text(), nullable=False),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('promise_uuid', 'club_id'),
        sa.ForeignKeyConstraint(['promise_uuid'], ['promises.promise_uuid']),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.club_id'])
    )
    
    op.create_table(
        'milestones',
        sa.Column('milestone_uuid', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('milestone_type', sa.Text(), nullable=False),
        sa.Column('value_int', sa.Integer(), nullable=True),
        sa.Column('value_text', sa.Text(), nullable=True),
        sa.Column('promise_uuid', sa.Text(), nullable=True),
        sa.Column('trigger_action_uuid', sa.Text(), nullable=True),
        sa.Column('trigger_session_id', sa.Text(), nullable=True),
        sa.Column('computed_at_utc', sa.Text(), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False, server_default='{}'),
        sa.PrimaryKeyConstraint('milestone_uuid'),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.ForeignKeyConstraint(['promise_uuid'], ['promises.promise_uuid']),
        sa.ForeignKeyConstraint(['trigger_action_uuid'], ['actions.action_uuid']),
        sa.ForeignKeyConstraint(['trigger_session_id'], ['sessions.session_id'])
    )
    
    op.create_table(
        'feed_items',
        sa.Column('feed_item_uuid', sa.Text(), nullable=False),
        sa.Column('actor_user_id', sa.Text(), nullable=False),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('visibility', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('action_uuid', sa.Text(), nullable=True),
        sa.Column('session_id', sa.Text(), nullable=True),
        sa.Column('milestone_uuid', sa.Text(), nullable=True),
        sa.Column('promise_uuid', sa.Text(), nullable=True),
        sa.Column('context_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('dedupe_key', sa.Text(), nullable=True),
        sa.Column('is_deleted', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('feed_item_uuid'),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.user_id']),
        sa.ForeignKeyConstraint(['action_uuid'], ['actions.action_uuid']),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.session_id']),
        sa.ForeignKeyConstraint(['milestone_uuid'], ['milestones.milestone_uuid']),
        sa.ForeignKeyConstraint(['promise_uuid'], ['promises.promise_uuid'])
    )
    
    op.create_table(
        'feed_reactions',
        sa.Column('reaction_uuid', sa.Text(), nullable=False),
        sa.Column('feed_item_uuid', sa.Text(), nullable=False),
        sa.Column('actor_user_id', sa.Text(), nullable=False),
        sa.Column('reaction_type', sa.Text(), nullable=False),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('is_deleted', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('reaction_uuid'),
        sa.UniqueConstraint('feed_item_uuid', 'actor_user_id', 'reaction_type', name='uq_feed_reactions'),
        sa.ForeignKeyConstraint(['feed_item_uuid'], ['feed_items.feed_item_uuid']),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.user_id'])
    )
    
    op.create_table(
        'social_events',
        sa.Column('event_uuid', sa.Text(), nullable=False),
        sa.Column('actor_user_id', sa.Text(), nullable=True),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('subject_type', sa.Text(), nullable=True),
        sa.Column('subject_id', sa.Text(), nullable=True),
        sa.Column('object_type', sa.Text(), nullable=True),
        sa.Column('object_id', sa.Text(), nullable=True),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('metadata_json', sa.Text(), nullable=False, server_default='{}'),
        sa.PrimaryKeyConstraint('event_uuid'),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.user_id'])
    )
    
    # V5: Broadcasts
    op.create_table(
        'broadcasts',
        sa.Column('broadcast_id', sa.Text(), nullable=False),
        sa.Column('admin_id', sa.Text(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('target_user_ids', sa.Text(), nullable=False),
        sa.Column('scheduled_time_utc', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('updated_at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('broadcast_id'),
        sa.CheckConstraint("status IN ('pending', 'completed', 'cancelled')", name='check_broadcast_status')
    )
    
    # V6: Promise templates and instances
    op.create_table(
        'promise_templates',
        sa.Column('template_id', sa.Text(), nullable=False),
        sa.Column('category', sa.Text(), nullable=False),
        sa.Column('program_key', sa.Text(), nullable=True),
        sa.Column('level', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('why', sa.Text(), nullable=False),
        sa.Column('done', sa.Text(), nullable=False),
        sa.Column('effort', sa.Text(), nullable=False),
        sa.Column('template_kind', sa.Text(), nullable=False, server_default='commitment'),
        sa.Column('metric_type', sa.Text(), nullable=False),
        sa.Column('target_value', sa.Double(), nullable=False),
        sa.Column('target_direction', sa.Text(), nullable=False, server_default='at_least'),
        sa.Column('estimated_hours_per_unit', sa.Double(), nullable=False, server_default='1.0'),
        sa.Column('duration_type', sa.Text(), nullable=False),
        sa.Column('duration_weeks', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('updated_at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('template_id'),
        sa.CheckConstraint("template_kind IN ('commitment', 'budget')", name='check_template_kind'),
        sa.CheckConstraint("metric_type IN ('hours', 'count')", name='check_metric_type'),
        sa.CheckConstraint("target_direction IN ('at_least', 'at_most')", name='check_target_direction'),
        sa.CheckConstraint("duration_type IN ('week', 'one_time', 'date')", name='check_duration_type')
    )
    
    op.create_table(
        'template_prerequisites',
        sa.Column('prereq_id', sa.Text(), nullable=False),
        sa.Column('template_id', sa.Text(), nullable=False),
        sa.Column('prereq_group', sa.Integer(), nullable=False),
        sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('required_template_id', sa.Text(), nullable=True),
        sa.Column('min_success_rate', sa.Double(), nullable=True),
        sa.Column('window_weeks', sa.Integer(), nullable=True),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('prereq_id'),
        sa.ForeignKeyConstraint(['template_id'], ['promise_templates.template_id']),
        sa.ForeignKeyConstraint(['required_template_id'], ['promise_templates.template_id']),
        sa.CheckConstraint("kind IN ('completed_template', 'success_rate')", name='check_prereq_kind')
    )
    
    op.create_table(
        'promise_instances',
        sa.Column('instance_id', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('template_id', sa.Text(), nullable=False),
        sa.Column('promise_uuid', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default='active'),
        sa.Column('metric_type', sa.Text(), nullable=False),
        sa.Column('target_value', sa.Double(), nullable=False),
        sa.Column('estimated_hours_per_unit', sa.Double(), nullable=False),
        sa.Column('start_date', sa.Text(), nullable=False),
        sa.Column('end_date', sa.Text(), nullable=True),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('updated_at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('instance_id'),
        sa.ForeignKeyConstraint(['template_id'], ['promise_templates.template_id']),
        sa.ForeignKeyConstraint(['promise_uuid'], ['promises.promise_uuid']),
        sa.CheckConstraint("status IN ('active', 'completed', 'abandoned')", name='check_instance_status'),
        sa.CheckConstraint("metric_type IN ('hours', 'count')", name='check_instance_metric_type')
    )
    
    op.create_table(
        'promise_weekly_reviews',
        sa.Column('review_id', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('instance_id', sa.Text(), nullable=False),
        sa.Column('week_start', sa.Text(), nullable=False),
        sa.Column('week_end', sa.Text(), nullable=False),
        sa.Column('metric_type', sa.Text(), nullable=False),
        sa.Column('target_value', sa.Double(), nullable=False),
        sa.Column('achieved_value', sa.Double(), nullable=False),
        sa.Column('success_ratio', sa.Double(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('computed_at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('review_id'),
        sa.ForeignKeyConstraint(['instance_id'], ['promise_instances.instance_id']),
        sa.CheckConstraint("metric_type IN ('hours', 'count')", name='check_review_metric_type')
    )
    
    op.create_table(
        'distraction_events',
        sa.Column('event_uuid', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('category', sa.Text(), nullable=False),
        sa.Column('minutes', sa.Double(), nullable=False),
        sa.Column('at_utc', sa.Text(), nullable=False),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('event_uuid')
    )
    
    # Create all indexes
    op.create_index('ix_promises_user', 'promises', ['user_id'])
    op.create_index('ix_actions_user_at', 'actions', ['user_id', 'at_utc'])
    op.create_index('ix_actions_user_promise_at', 'actions', ['user_id', 'promise_uuid', 'at_utc'])
    op.create_index('ix_sessions_user_status', 'sessions', ['user_id', 'status'])
    op.create_index('ix_conversations_user_time', 'conversations', ['user_id', 'created_at_utc'], postgresql_ops={'created_at_utc': 'DESC'})
    op.create_index('ix_relationships_target_type', 'user_relationships', ['target_user_id', 'relationship_type', 'is_active', 'created_at_utc'], postgresql_ops={'created_at_utc': 'DESC'})
    op.create_index('ix_relationships_source_type', 'user_relationships', ['source_user_id', 'relationship_type', 'is_active', 'created_at_utc'], postgresql_ops={'created_at_utc': 'DESC'})
    op.create_index('ix_relationships_bidirectional', 'user_relationships', ['source_user_id', 'target_user_id', 'relationship_type', 'is_active'])
    op.create_index('ix_clubs_owner', 'clubs', ['owner_user_id', 'created_at_utc'], postgresql_ops={'created_at_utc': 'DESC'})
    op.create_index('ix_club_members_user', 'club_members', ['user_id', 'club_id'])
    op.create_index('ix_promise_club_shares_promise', 'promise_club_shares', ['promise_uuid'])
    op.create_index('ix_promise_club_shares_club', 'promise_club_shares', ['club_id'])
    op.create_index('ix_milestones_user', 'milestones', ['user_id', 'computed_at_utc'], postgresql_ops={'computed_at_utc': 'DESC'})
    op.create_index('ix_milestones_promise', 'milestones', ['promise_uuid', 'computed_at_utc'], postgresql_ops={'computed_at_utc': 'DESC'})
    op.create_index('ix_feed_items_actor_time', 'feed_items', ['actor_user_id', 'created_at_utc'], postgresql_ops={'created_at_utc': 'DESC'})
    op.create_index('ix_feed_items_time', 'feed_items', ['created_at_utc'], postgresql_ops={'created_at_utc': 'DESC'})
    op.create_index('ix_feed_items_promise', 'feed_items', ['promise_uuid', 'created_at_utc'], postgresql_ops={'created_at_utc': 'DESC'})
    op.create_index('ix_reactions_feed_time', 'feed_reactions', ['feed_item_uuid', 'created_at_utc'], postgresql_ops={'created_at_utc': 'DESC'})
    op.create_index('ix_reactions_actor', 'feed_reactions', ['actor_user_id', 'created_at_utc'], postgresql_ops={'created_at_utc': 'DESC'})
    op.create_index('ix_social_events_actor', 'social_events', ['actor_user_id', 'created_at_utc'], postgresql_ops={'created_at_utc': 'DESC'})
    op.create_index('ix_social_events_type', 'social_events', ['event_type', 'created_at_utc'], postgresql_ops={'created_at_utc': 'DESC'})
    op.create_index('ix_social_events_time', 'social_events', ['created_at_utc'], postgresql_ops={'created_at_utc': 'DESC'})
    op.create_index('ix_broadcasts_admin', 'broadcasts', ['admin_id', 'created_at_utc'], postgresql_ops={'created_at_utc': 'DESC'})
    op.create_index('ix_broadcasts_scheduled', 'broadcasts', ['scheduled_time_utc', 'status'])
    op.create_index('ix_broadcasts_status', 'broadcasts', ['status', 'scheduled_time_utc'])
    op.create_index('ix_templates_category', 'promise_templates', ['category', 'is_active'])
    op.create_index('ix_templates_program', 'promise_templates', ['program_key', 'level'])
    op.create_index('ix_prereqs_template', 'template_prerequisites', ['template_id', 'prereq_group'])
    op.create_index('ix_instances_user', 'promise_instances', ['user_id', 'status'])
    op.create_index('ix_instances_template', 'promise_instances', ['template_id'])
    op.create_index('ix_reviews_instance', 'promise_weekly_reviews', ['instance_id', 'week_start'], postgresql_ops={'week_start': 'DESC'})
    op.create_index('ix_reviews_user', 'promise_weekly_reviews', ['user_id', 'week_start'], postgresql_ops={'week_start': 'DESC'})
    op.create_index('ix_distractions_user', 'distraction_events', ['user_id', 'at_utc'], postgresql_ops={'at_utc': 'DESC'})
    op.create_index('ix_distractions_category', 'distraction_events', ['category', 'at_utc'], postgresql_ops={'at_utc': 'DESC'})
    
    # V7: Create view for promises with type
    op.execute("""
        CREATE VIEW promises_with_type AS
        SELECT 
            promise_uuid,
            user_id,
            current_id,
            text,
            hours_per_week,
            recurring,
            start_date,
            end_date,
            angle_deg,
            radius,
            is_deleted,
            visibility,
            description,
            created_at_utc,
            updated_at_utc,
            CASE WHEN hours_per_week <= 0 THEN 1 ELSE 0 END AS is_check_based,
            CASE WHEN hours_per_week > 0 THEN 1 ELSE 0 END AS is_time_based,
            CASE WHEN hours_per_week <= 0 THEN 'check_based' ELSE 'time_based' END AS promise_type
        FROM promises;
    """)


def downgrade() -> None:
    # Drop view first
    op.execute("DROP VIEW IF EXISTS promises_with_type;")
    
    # Drop all tables in reverse order
    op.drop_table('distraction_events')
    op.drop_table('promise_weekly_reviews')
    op.drop_table('promise_instances')
    op.drop_table('template_prerequisites')
    op.drop_table('promise_templates')
    op.drop_table('broadcasts')
    op.drop_table('social_events')
    op.drop_table('feed_reactions')
    op.drop_table('feed_items')
    op.drop_table('milestones')
    op.drop_table('promise_club_shares')
    op.drop_table('club_members')
    op.drop_table('clubs')
    op.drop_table('user_relationships')
    op.drop_table('conversations')
    op.drop_table('legacy_imports')
    op.drop_table('sessions')
    op.drop_table('actions')
    op.drop_table('promise_events')
    op.drop_table('promise_aliases')
    op.drop_table('promises')
    op.drop_table('users')
    op.drop_table('schema_version')
