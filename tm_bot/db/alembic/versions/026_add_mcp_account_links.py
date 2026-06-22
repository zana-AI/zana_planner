"""Add MCP account-link tables

Revision ID: 026_add_mcp_account_links
Revises: 025_add_user_is_hidden
Create Date: 2026-06-22

Links an OAuth identity (WorkOS subject) from an MCP client (Claude, ChatGPT, ...)
to a Zana user. `mcp_link_codes` holds short-lived one-time codes minted from an
authenticated Zana surface; redeeming one creates a row in `mcp_account_links`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "026_add_mcp_account_links"
down_revision: Union[str, None] = "025_add_user_is_hidden"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mcp_account_links",
        sa.Column("oauth_issuer", sa.Text(), nullable=False),
        sa.Column("oauth_subject", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("oauth_issuer", "oauth_subject"),
    )
    op.create_index("ix_mcp_account_links_user_id", "mcp_account_links", ["user_id"])

    op.create_table(
        "mcp_link_codes",
        sa.Column("code", sa.Text(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.Text(), nullable=True),
        sa.Column("expires_at_utc", sa.Text(), nullable=True),
        sa.Column("redeemed_at_utc", sa.Text(), nullable=True),
        sa.Column("redeemed_subject", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("mcp_link_codes")
    op.drop_index("ix_mcp_account_links_user_id", table_name="mcp_account_links")
    op.drop_table("mcp_account_links")
