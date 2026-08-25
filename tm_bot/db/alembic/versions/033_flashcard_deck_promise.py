"""Attach flashcard decks to a promise, so Play can traverse the promise tree

My Week is a list of promises. Everything a user can *do* already hangs off one:

  challenge_participants.promise_uuid   a daily quiz belongs to a promise
  user_content.assigned_promise_id      a video or PDF belongs to a promise

Decks were the exception — they were reachable only from Explore, which is why
"Français" and "French" looked like two unrelated products rather than two parts
of the same promise. This adds the missing edge so a single promise ("French")
can own its content, its challenge quizzes and its vocabulary decks at once.

Nullable on purpose: an unattached deck is still a valid deck, it just does not
surface under Play. ON DELETE SET NULL because deleting a promise must never
cascade into review history — `flashcard_review_log` is the one table that
cannot be reconstructed.

Revision ID: 033_flashcard_deck_promise
Revises: 032_flashcards_srs
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "033_flashcard_deck_promise"
down_revision: Union[str, None] = "032_flashcards_srs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "flashcard_deck",
        sa.Column("promise_id", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_flashcard_deck_promise",
        "flashcard_deck",
        "promises",
        ["promise_id"],
        ["promise_uuid"],
        ondelete="SET NULL",
    )
    # Play reads "decks for this user's promises" on every open.
    op.create_index(
        "ix_flashcard_deck_promise",
        "flashcard_deck",
        ["user_id", "promise_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_flashcard_deck_promise", table_name="flashcard_deck")
    op.drop_constraint("fk_flashcard_deck_promise", "flashcard_deck", type_="foreignkey")
    op.drop_column("flashcard_deck", "promise_id")
