"""Add promise assignment fields to user_content.

Revision ID: 021_add_content_promise_assignment
Revises: 020_add_pdf_highlights
Create Date: 2026-05-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "021_add_content_promise_assignment"
down_revision: Union[str, None] = "020_add_pdf_highlights"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_content", sa.Column("assigned_promise_id", sa.Text(), nullable=True))
    op.add_column("user_content", sa.Column("assigned_at", sa.Text(), nullable=True))
    op.create_index(
        "ix_user_content_assigned_promise",
        "user_content",
        ["user_id", "assigned_promise_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_content_assigned_promise", table_name="user_content")
    op.drop_column("user_content", "assigned_at")
    op.drop_column("user_content", "assigned_promise_id")
