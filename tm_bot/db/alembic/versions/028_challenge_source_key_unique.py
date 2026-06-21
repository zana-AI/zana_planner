"""Unique index on challenges.source_key (deep-link tokens must be unique)

get_by_source_key() resolves a startapp deep-link token with LIMIT 1, so two
challenges sharing a source_key would route ambiguously. Enforce uniqueness.
Postgres allows multiple NULLs in a unique index, so link-less challenges are fine.

Revision ID: 028_challenge_source_key_unique
Revises: 027_challenge_promise_bridge
Create Date: 2026-06-21
"""
from typing import Sequence, Union

from alembic import op


revision: str = "028_challenge_source_key_unique"
down_revision: Union[str, None] = "027_challenge_promise_bridge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ux_challenges_source_key",
        "challenges",
        ["source_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_challenges_source_key", table_name="challenges")
