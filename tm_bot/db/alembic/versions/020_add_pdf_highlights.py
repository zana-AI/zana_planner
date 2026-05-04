"""Add PDF highlights table

Revision ID: 020_add_pdf_highlights
Revises: 019_add_llm_usage_logs
Create Date: 2026-05-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "020_add_pdf_highlights"
down_revision: Union[str, None] = "019_add_llm_usage_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_highlight",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("content_id", sa.Text(), nullable=False),
        sa.Column("asset_id", sa.Text(), nullable=False),
        sa.Column("page_index", sa.Integer(), nullable=False),
        sa.Column("rects_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("selected_text", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("color", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("copied_from_highlight_id", sa.Text(), nullable=True),
        sa.Column("migration_status", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["content_id"], ["content.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["content_asset.id"]),
        sa.ForeignKeyConstraint(["copied_from_highlight_id"], ["content_highlight.id"]),
    )
    op.create_index(
        "ix_content_highlight_user_content_asset",
        "content_highlight",
        ["user_id", "content_id", "asset_id"],
    )
    op.create_index(
        "ix_content_highlight_content_asset_page",
        "content_highlight",
        ["content_id", "asset_id", "page_index"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_highlight_content_asset_page", "content_highlight")
    op.drop_index("ix_content_highlight_user_content_asset", "content_highlight")
    op.drop_table("content_highlight")
