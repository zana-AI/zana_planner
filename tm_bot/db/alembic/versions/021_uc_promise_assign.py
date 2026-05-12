"""Add optional promise link on user_content

Revision ID: 021_uc_promise_assign
Revises: 020_add_pdf_highlights
Create Date: 2026-05-12

Note: Alembic stores revision ids in alembic_version.version_num (varchar(32)).
Keep revision strings <= 32 characters.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "021_uc_promise_assign"
down_revision: Union[str, None] = "020_add_pdf_highlights"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_content",
        sa.Column("assigned_promise_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "user_content",
        sa.Column("assigned_at", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_user_content_assigned_promise",
        "user_content",
        "promises",
        ["assigned_promise_id"],
        ["promise_uuid"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_user_content_assigned_promise",
        "user_content",
        ["user_id", "assigned_promise_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_content_assigned_promise", table_name="user_content")
    op.drop_constraint("fk_user_content_assigned_promise", "user_content", type_="foreignkey")
    op.drop_column("user_content", "assigned_at")
    op.drop_column("user_content", "assigned_promise_id")
