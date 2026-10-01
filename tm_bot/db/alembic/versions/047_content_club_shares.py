"""Allow one content item to be shared with multiple clubs independently.

Revision ID: 047_content_club_shares
Revises: 046_plan_session_completion_metrics
"""
from alembic import op
import sqlalchemy as sa


revision = "047_content_club_shares"
down_revision = "046_plan_session_completion_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_club_shares",
        sa.Column("content_id", sa.Text(), sa.ForeignKey("content.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("club_id", sa.Text(), sa.ForeignKey("clubs.club_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("shared_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'sent')", name="check_content_club_share_status"),
    )
    op.create_index("ix_content_club_shares_club_created", "content_club_shares", ["club_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_content_club_shares_club_created", table_name="content_club_shares")
    op.drop_table("content_club_shares")
