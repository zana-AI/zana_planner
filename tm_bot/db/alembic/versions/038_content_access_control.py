"""Add ownership and access control to content and flashcard decks.

Revision ID: 038_content_access_control
Revises: 037_plan_session_optional_promise
Create Date: 2026-09-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "038_content_access_control"
down_revision: Union[str, None] = "037_plan_session_optional_promise"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("check_challenge_visibility", "challenges", type_="check")
    op.execute("UPDATE challenges SET visibility = 'private' WHERE visibility = 'unlisted'")
    op.create_check_constraint(
        "check_challenge_visibility",
        "challenges",
        "visibility IN ('private', 'club', 'public')",
    )
    op.add_column("content", sa.Column("owner_user_id", sa.Text(), nullable=True))
    op.add_column(
        "content",
        sa.Column("visibility", sa.Text(), nullable=False, server_default="private"),
    )
    op.add_column("content", sa.Column("club_id", sa.Text(), nullable=True))
    op.create_check_constraint(
        "check_content_visibility",
        "content",
        "visibility IN ('private', 'club', 'public')",
    )
    op.create_foreign_key(
        "fk_content_access_club", "content", "clubs", ["club_id"], ["club_id"]
    )
    op.create_index("ix_content_owner_visibility", "content", ["owner_user_id", "visibility"])
    op.create_index("ix_content_club", "content", ["club_id"])

    # The earliest saver is the best available owner for the pre-access-control
    # catalog. Rows with no saver remain system-owned (NULL) and admin-visible.
    op.execute(
        """
        UPDATE content AS c
        SET owner_user_id = first_save.user_id
        FROM (
            SELECT DISTINCT ON (content_id) content_id, user_id
            FROM user_content
            ORDER BY content_id, added_at ASC, id ASC
        ) AS first_save
        WHERE c.id = first_save.content_id
        """
    )

    op.add_column(
        "flashcard_deck",
        sa.Column("visibility", sa.Text(), nullable=False, server_default="private"),
    )
    op.add_column("flashcard_deck", sa.Column("club_id", sa.Text(), nullable=True))
    op.create_check_constraint(
        "check_flashcard_deck_visibility",
        "flashcard_deck",
        "visibility IN ('private', 'club', 'public')",
    )
    op.create_foreign_key(
        "fk_flashcard_deck_access_club",
        "flashcard_deck",
        "clubs",
        ["club_id"],
        ["club_id"],
    )
    op.create_index("ix_flashcard_deck_visibility", "flashcard_deck", ["visibility"])
    op.create_index("ix_flashcard_deck_club", "flashcard_deck", ["club_id"])


def downgrade() -> None:
    op.drop_index("ix_flashcard_deck_club", table_name="flashcard_deck")
    op.drop_index("ix_flashcard_deck_visibility", table_name="flashcard_deck")
    op.drop_constraint("fk_flashcard_deck_access_club", "flashcard_deck", type_="foreignkey")
    op.drop_constraint("check_flashcard_deck_visibility", "flashcard_deck", type_="check")
    op.drop_column("flashcard_deck", "club_id")
    op.drop_column("flashcard_deck", "visibility")

    op.drop_index("ix_content_club", table_name="content")
    op.drop_index("ix_content_owner_visibility", table_name="content")
    op.drop_constraint("fk_content_access_club", "content", type_="foreignkey")
    op.drop_constraint("check_content_visibility", "content", type_="check")
    op.drop_column("content", "club_id")
    op.drop_column("content", "visibility")
    op.drop_column("content", "owner_user_id")
    op.drop_constraint("check_challenge_visibility", "challenges", type_="check")
    op.execute("UPDATE challenges SET visibility = 'unlisted' WHERE visibility IN ('private', 'club')")
    op.create_check_constraint(
        "check_challenge_visibility",
        "challenges",
        "visibility IN ('public', 'unlisted')",
    )
