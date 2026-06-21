"""Bridge challenges into the promise model: scored check-ins + backing template/promise links

A challenge becomes a subscribable, club-backed count promise whose daily check-in is the
attached quiz, scored non-binary. See docs/CHALLENGES_DESIGN.md and the plan.

- actions.score              : per-day non-binary score (0..100) for a scored check-in; NULL otherwise
- challenges.template_id     : backing promise_template subscribers subscribe to
- challenges.reminder_local_time : daily "your quiz is ready" DM time, e.g. "18:00"
- challenge_participants.promise_uuid : the subscriber's own backing promise

Revision ID: 027_challenge_promise_bridge
Revises: 026_challenges
Create Date: 2026-06-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "027_challenge_promise_bridge"
down_revision: Union[str, None] = "026_challenges"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("actions", sa.Column("score", sa.Float(), nullable=True))
    op.add_column("challenges", sa.Column("template_id", sa.Text(), nullable=True))
    op.add_column("challenges", sa.Column("reminder_local_time", sa.Text(), nullable=True))
    op.add_column("challenge_participants", sa.Column("promise_uuid", sa.Text(), nullable=True))
    op.create_index(
        "ix_challenge_participants_promise",
        "challenge_participants",
        ["user_id", "promise_uuid"],
    )


def downgrade() -> None:
    op.drop_index("ix_challenge_participants_promise", table_name="challenge_participants")
    op.drop_column("challenge_participants", "promise_uuid")
    op.drop_column("challenges", "reminder_local_time")
    op.drop_column("challenges", "template_id")
    op.drop_column("actions", "score")
