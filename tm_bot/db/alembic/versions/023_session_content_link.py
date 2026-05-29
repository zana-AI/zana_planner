"""Add content_id to plan_sessions

Lets a planned session reference the specific content item it is for
(e.g. a "Watch: ..." session created when content is assigned to a
promise). Nullable: ordinary user-created sessions have no content.

Revision ID: 023_session_content_link
Revises: 022_add_auth_sessions
Create Date: 2026-05-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "023_session_content_link"
down_revision: Union[str, None] = "022_add_auth_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("plan_sessions", sa.Column("content_id", sa.Text(), nullable=True))
    op.create_index(
        "ix_plan_sessions_content", "plan_sessions", ["content_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_plan_sessions_content", table_name="plan_sessions")
    op.drop_column("plan_sessions", "content_id")
