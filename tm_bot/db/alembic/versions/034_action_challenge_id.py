"""Attribute a scored check-in to the challenge that produced it

`club_checkin` actions were keyed by (user, promise, day) alone. That was
unambiguous while every challenge had its own backing promise — and became
lossy the moment one promise backed several, which is what consolidating all
French courses under a single promise does.

Two concrete failures without this column:

  1. `append_scored_checkin` DELETEs any existing check-in for the promise+day
     before inserting. Play the Atena quiz, then the Naturalization quiz, and
     the second **erases** the first — a real row lost, not just a display
     collision.
  2. The club leaderboard resolved members through `promise_club_shares`, so a
     promise shared to two clubs scored the same check-in in both. Doing one
     quiz credited you in the other course's league table.

With `challenge_id` recorded, a check-in belongs to one challenge, idempotency
is scoped per challenge per day, and the leaderboard can select exactly the
check-ins its own challenge produced.

Nullable: rows written before this migration have no challenge to point at, and
the leaderboard falls back to promise-matching for them.

Revision ID: 034_action_challenge_id
Revises: 033_flashcard_deck_promise
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "034_action_challenge_id"
down_revision: Union[str, None] = "033_flashcard_deck_promise"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("actions", sa.Column("challenge_id", sa.Text(), nullable=True))
    # No foreign key: `actions` is an append-only history, and a check-in must
    # survive its challenge being deleted rather than block the delete.
    op.create_index(
        "ix_actions_challenge",
        "actions",
        ["user_id", "challenge_id"],
        postgresql_where=sa.text("challenge_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_actions_challenge", table_name="actions")
    op.drop_column("actions", "challenge_id")
