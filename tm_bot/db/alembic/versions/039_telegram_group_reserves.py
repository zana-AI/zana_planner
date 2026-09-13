"""Track pre-created Telegram groups without storing dormant invite links.

Revision ID: 039_telegram_group_reserves
Revises: 038_content_access_control
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa


revision = "039_telegram_group_reserves"
down_revision = "038_content_access_control"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_group_reserves",
        sa.Column("chat_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("label", sa.Text(), nullable=False, unique=True),
        sa.Column("registered_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("caretaker_user_id", sa.BigInteger(), nullable=False),
        sa.Column("bot_user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="available"),
        sa.Column("club_id", sa.Text(), sa.ForeignKey("clubs.club_id"), nullable=True, unique=True),
        sa.Column("original_title", sa.Text(), nullable=False),
        sa.Column("member_count_at_check", sa.Integer(), nullable=False),
        sa.Column("verified_at_utc", sa.Text(), nullable=False),
        sa.Column("cleanliness_attested_at_utc", sa.Text(), nullable=False),
        sa.Column("cleanliness_attested_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("allocated_at_utc", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('available', 'assigning', 'allocated', 'needs_review', 'disabled')",
            name="check_telegram_group_reserve_status",
        ),
    )
    op.create_index(
        "ix_telegram_group_reserves_available",
        "telegram_group_reserves",
        ["verified_at_utc"],
        postgresql_where=sa.text("status = 'available'"),
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_group_reserves_available", table_name="telegram_group_reserves")
    op.drop_table("telegram_group_reserves")
