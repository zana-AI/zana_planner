"""Credit earned by an action, kept separate from the time it really took

An hours-based promise scored nothing for a quiz: `club_checkin` rows carry no
duration, and the real measured one is under a minute, so a week of daily
quizzes left "Learn French" reading 0%.

Credits fix that by valuing work rather than elapsed time — one answered
question or rated card is worth one credit-minute. See services/credits.py for
the rates and the reasoning.

`credits_minutes` is its own column rather than being folded into
`time_spent_hours` on purpose. A credited minute is not a minute that passed;
writing it into the duration field would corrupt the one record that says how
long the user actually studied, and that record cannot be reconstructed. Keeping
both means progress can be generous while history stays true.

Revision ID: 035_action_credits
Revises: 034_action_challenge_id
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "035_action_credits"
down_revision: Union[str, None] = "034_action_challenge_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "actions",
        sa.Column("credits_minutes", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("actions", "credits_minutes")
