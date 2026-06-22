"""Challenges engine: challenges, decks, items, participants, attempts

General interactive-challenge engine (flashcard + multiple-choice for v1).
See docs/CHALLENGES_DESIGN.md. Cohort/streak/leaderboard reuse the promise/action
engine via a (nullable) club backing — added in a later migration; these tables are
the self-contained content + answers layer.

Revision ID: 026_challenges
Revises: 025_add_user_is_hidden
Create Date: 2026-06-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "026_challenges"
down_revision: Union[str, None] = "025_add_user_is_hidden"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The challenge itself: host + activity type + schedule + (optional) club cohort.
    op.create_table(
        "challenges",
        sa.Column("challenge_id", sa.Text(), nullable=False),
        sa.Column("host_user_id", sa.Text(), nullable=False),
        sa.Column("club_id", sa.Text(), nullable=True),  # Option-A cohort backing (later)
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("activity_type", sa.Text(), nullable=False, server_default="flashcard"),
        sa.Column("cadence", sa.Text(), nullable=False, server_default="daily"),
        sa.Column("start_date", sa.Text(), nullable=True),
        sa.Column("end_date", sa.Text(), nullable=True),
        sa.Column("visibility", sa.Text(), nullable=False, server_default="public"),
        sa.Column("source_key", sa.Text(), nullable=True),  # startapp deep-link token
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at_utc", sa.Text(), nullable=False),
        sa.Column("updated_at_utc", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("challenge_id"),
        sa.CheckConstraint(
            "activity_type IN ('flashcard', 'multiple_choice')",
            name="check_challenge_activity_type",
        ),
        sa.CheckConstraint("cadence IN ('daily', 'weekly')", name="check_challenge_cadence"),
        sa.CheckConstraint(
            "visibility IN ('public', 'unlisted')", name="check_challenge_visibility"
        ),
        sa.CheckConstraint("status IN ('active', 'archived')", name="check_challenge_status"),
    )

    # A scheduled set of items within a challenge.
    op.create_table(
        "challenge_decks",
        sa.Column("deck_id", sa.Text(), nullable=False),
        sa.Column("challenge_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("release_at", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("deck_id"),
        sa.ForeignKeyConstraint(["challenge_id"], ["challenges.challenge_id"]),
    )

    # One card / question. Same schema serves flashcard AND multiple-choice.
    # `options` is a JSON-encoded list of strings (incl. the correct answer) for MCQ; NULL for flashcards.
    op.create_table(
        "challenge_items",
        sa.Column("item_id", sa.Text(), nullable=False),
        sa.Column("deck_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("front", sa.Text(), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("example", sa.Text(), nullable=True),
        sa.Column("media_url", sa.Text(), nullable=True),  # reserved (audio/img) — unused in v1
        sa.Column("options", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("item_id"),
        sa.ForeignKeyConstraint(["deck_id"], ["challenge_decks.deck_id"]),
    )

    # Who joined (kept explicit for source attribution / funnel analytics).
    op.create_table(
        "challenge_participants",
        sa.Column("challenge_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("joined_at_utc", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("challenge_id", "user_id"),
    )

    # Every answer — drives score, completion, leaderboard and streak.
    op.create_table(
        "challenge_attempts",
        sa.Column("attempt_id", sa.Text(), nullable=False),
        sa.Column("challenge_id", sa.Text(), nullable=False),
        sa.Column("deck_id", sa.Text(), nullable=False),
        sa.Column("item_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("is_correct", sa.Integer(), nullable=True),
        sa.Column("answered_at_utc", sa.Text(), nullable=False),
        sa.Column("time_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("attempt_id"),
    )

    op.create_index("ix_challenges_visibility_status", "challenges", ["visibility", "status"])
    op.create_index("ix_challenges_host", "challenges", ["host_user_id"])
    op.create_index("ix_challenge_decks_challenge", "challenge_decks", ["challenge_id", "position"])
    op.create_index("ix_challenge_items_deck", "challenge_items", ["deck_id", "position"])
    op.create_index("ix_challenge_participants_user", "challenge_participants", ["user_id"])
    op.create_index(
        "ix_challenge_attempts_user_challenge",
        "challenge_attempts",
        ["user_id", "challenge_id", "answered_at_utc"],
    )
    op.create_index("ix_challenge_attempts_deck", "challenge_attempts", ["deck_id"])


def downgrade() -> None:
    op.drop_index("ix_challenge_attempts_deck", table_name="challenge_attempts")
    op.drop_index("ix_challenge_attempts_user_challenge", table_name="challenge_attempts")
    op.drop_index("ix_challenge_participants_user", table_name="challenge_participants")
    op.drop_index("ix_challenge_items_deck", table_name="challenge_items")
    op.drop_index("ix_challenge_decks_challenge", table_name="challenge_decks")
    op.drop_index("ix_challenges_host", table_name="challenges")
    op.drop_index("ix_challenges_visibility_status", table_name="challenges")
    op.drop_table("challenge_attempts")
    op.drop_table("challenge_participants")
    op.drop_table("challenge_items")
    op.drop_table("challenge_decks")
    op.drop_table("challenges")
