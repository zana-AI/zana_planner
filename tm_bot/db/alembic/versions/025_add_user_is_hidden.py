"""Add is_hidden flag to users for hiding noise accounts from community

Revision ID: 025_add_user_is_hidden
Revises: 024_plan_session_reminder_preferences
Create Date: 2026-05-31

Lets admins hide bots, test, or mistaken accounts from the community
discovery surfaces (Discover Active Users + Recent Activity) without
deactivating the account itself. See issue #65.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "025_add_user_is_hidden"
down_revision: Union[str, None] = "024_plan_session_reminder_preferences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_hidden")
