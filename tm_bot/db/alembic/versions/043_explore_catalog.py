"""Store the curated Explore catalog independently of application images.

Revision ID: 043_explore_catalog
Revises: 042_caption_relay
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "043_explore_catalog"
down_revision = "042_caption_relay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "explore_catalog",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("id = 'main'", name="check_explore_catalog_singleton"),
    )


def downgrade() -> None:
    op.drop_table("explore_catalog")
