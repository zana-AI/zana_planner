"""Content consumption manager: content catalog, user_content, consumption events, rollup heatmaps

Revision ID: 011_content_manager
Revises: 010_add_conversation_importance
Create Date: 2026-02-19

Tables:
- content: global catalog (canonical_url, provider, content_type, title, thumbnail_url, etc.)
- user_content: user <-> content relationship (status, progress_ratio, last_position)
- content_consumption_event: append-only telemetry (start/end position, client)
- user_content_rollup: heatmap buckets per user+content

Future schema hooks (not created): content_tags, playlists, playlist_items, ai_content_features
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '011_content_manager'
down_revision: Union[str, None] = '010_add_conversation_importance'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Table A: content (global catalog)
    op.create_table(
        'content',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('canonical_url', sa.Text(), nullable=False),
        sa.Column('original_url', sa.Text(), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('content_type', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('author_channel', sa.Text(), nullable=True),
        sa.Column('language', sa.Text(), nullable=True),
        sa.Column('published_at', sa.Text(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('estimated_read_seconds', sa.Integer(), nullable=True),
        sa.Column('thumbnail_url', sa.Text(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_content_canonical_url', 'content', ['canonical_url'], unique=True)
    op.create_index('ix_content_provider', 'content', ['provider'])
    op.create_index('ix_content_content_type', 'content', ['content_type'])
    op.create_index('ix_content_created_at', 'content', ['created_at'])

    # Table B: user_content (user <-> content)
    op.create_table(
        'user_content',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('content_id', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='saved'),
        sa.Column('added_at', sa.Text(), nullable=False),
        sa.Column('last_interaction_at', sa.Text(), nullable=True),
        sa.Column('completed_at', sa.Text(), nullable=True),
        sa.Column('last_position', sa.Float(), nullable=True),
        sa.Column('position_unit', sa.Text(), nullable=True),
        sa.Column('progress_ratio', sa.Float(), nullable=True, server_default='0'),
        sa.Column('total_consumed_seconds', sa.Float(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('rating', sa.SmallInteger(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['content_id'], ['content.id']),
        sa.UniqueConstraint('user_id', 'content_id', name='uq_user_content_user_content')
    )
    op.create_index('ix_user_content_user_id', 'user_content', ['user_id'])
    op.create_index('ix_user_content_status', 'user_content', ['status'])
    op.create_index('ix_user_content_last_interaction_at', 'user_content', ['last_interaction_at'], postgresql_ops={'last_interaction_at': 'DESC NULLS LAST'})

    # Table C: content_consumption_event (append-only)
    op.create_table(
        'content_consumption_event',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('content_id', sa.Text(), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=False, server_default='consume'),
        sa.Column('start_position', sa.Float(), nullable=False),
        sa.Column('end_position', sa.Float(), nullable=False),
        sa.Column('position_unit', sa.Text(), nullable=False),
        sa.Column('started_at', sa.Text(), nullable=True),
        sa.Column('ended_at', sa.Text(), nullable=True),
        sa.Column('client', sa.Text(), nullable=True),
        sa.Column('device_id', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'])
    )
    op.create_index('ix_content_consumption_event_user_content_created', 'content_consumption_event', ['user_id', 'content_id', 'created_at'])
    op.create_index('ix_content_consumption_event_content_created', 'content_consumption_event', ['content_id', 'created_at'])

    # Table D: user_content_rollup (heatmap buckets)
    op.create_table(
        'user_content_rollup',
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('content_id', sa.Text(), nullable=False),
        sa.Column('bucket_count', sa.Integer(), nullable=False, server_default='120'),
        sa.Column('buckets', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('updated_at', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('user_id', 'content_id'),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'])
    )


def downgrade() -> None:
    op.drop_table('user_content_rollup')
    op.drop_index('ix_content_consumption_event_content_created', 'content_consumption_event')
    op.drop_index('ix_content_consumption_event_user_content_created', 'content_consumption_event')
    op.drop_table('content_consumption_event')
    op.drop_index('ix_user_content_last_interaction_at', 'user_content')
    op.drop_index('ix_user_content_status', 'user_content')
    op.drop_index('ix_user_content_user_id', 'user_content')
    op.drop_table('user_content')
    op.drop_index('ix_content_created_at', 'content')
    op.drop_index('ix_content_content_type', 'content')
    op.drop_index('ix_content_provider', 'content')
    op.drop_index('ix_content_canonical_url', 'content')
    op.drop_table('content')
