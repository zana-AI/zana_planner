"""Add chat_not_found flag to users table

Revision ID: 013_add_chat_not_found
Revises: 012_content_learning_pipeline
Create Date: 2026-02-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "013_add_chat_not_found"
down_revision: Union[str, None] = "012_content_learning_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "chat_not_found",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "chat_not_found")
