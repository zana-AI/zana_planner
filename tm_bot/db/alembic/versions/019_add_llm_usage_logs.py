"""Add llm_usage_logs table for per-call model and token telemetry

Revision ID: 019_add_llm_usage_logs
Revises: 018_add_multilingual_names
Create Date: 2026-04-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '019_add_llm_usage_logs'
down_revision: Union[str, None] = '018_add_multilingual_names'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_usage_logs',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('created_at_utc', sa.Text(), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('model_name', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('error_type', sa.Text(), nullable=True),
    )
    op.create_index(
        'ix_llm_usage_logs_created_at_utc',
        'llm_usage_logs',
        ['created_at_utc'],
    )
    op.create_index(
        'ix_llm_usage_logs_model_role',
        'llm_usage_logs',
        ['model_name', 'role'],
    )


def downgrade() -> None:
    op.drop_index('ix_llm_usage_logs_model_role', table_name='llm_usage_logs')
    op.drop_index('ix_llm_usage_logs_created_at_utc', table_name='llm_usage_logs')
    op.drop_table('llm_usage_logs')
