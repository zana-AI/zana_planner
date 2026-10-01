"""Club reading activity and timestamped video annotations.

Revision ID: 048_club_content_activity
Revises: 047_content_club_shares
"""
from alembic import op
import sqlalchemy as sa


revision = "048_club_content_activity"
down_revision = "047_content_club_shares"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_highlight", sa.Column("club_visible", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table(
        "club_video_annotation",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("content_id", sa.Text(), nullable=False),
        sa.Column("club_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("position_seconds", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("position_seconds >= 0", name="check_club_video_annotation_position"),
        sa.CheckConstraint("length(trim(body)) BETWEEN 1 AND 2000", name="check_club_video_annotation_body"),
        sa.ForeignKeyConstraint(
            ["content_id", "club_id"],
            ["content_club_shares.content_id", "content_club_shares.club_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_club_video_annotation_timeline", "club_video_annotation", ["club_id", "content_id", "position_seconds"])


def downgrade() -> None:
    op.drop_index("ix_club_video_annotation_timeline", table_name="club_video_annotation")
    op.drop_table("club_video_annotation")
    op.drop_column("content_highlight", "club_visible")
