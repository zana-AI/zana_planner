"""Drop the reserve caretaker: reserve groups now hold no human member.

Telegram keeps a bot's admin rights intact in an ownerless supergroup, so a
reserve can sit in the pool with only the bot inside. The club creator is
promoted directly on join and there is nobody to hand off from, which removes
the caretaker column along with the departure-window states it drove.

Revision ID: 040_drop_reserve_caretaker
Revises: 039_telegram_group_reserves
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa


revision = "040_drop_reserve_caretaker"
down_revision = "039_telegram_group_reserves"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("telegram_group_reserves", "caretaker_user_id")


def downgrade() -> None:
    # Existing rows have no caretaker to restore, so backfill the sentinel 0
    # before restoring the NOT NULL the original schema declared.
    op.add_column(
        "telegram_group_reserves",
        sa.Column("caretaker_user_id", sa.BigInteger(), nullable=True),
    )
    op.execute("UPDATE telegram_group_reserves SET caretaker_user_id = 0")
    op.alter_column("telegram_group_reserves", "caretaker_user_id", nullable=False)
