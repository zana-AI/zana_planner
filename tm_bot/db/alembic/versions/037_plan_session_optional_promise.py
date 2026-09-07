"""Let a planned session exist without a promise

`plan_sessions.content_id` has been here since 023, but `promise_uuid` was NOT
NULL, so a session could only ever hang off a promise. That made "watch this
video on Thursday at 20:00" inexpressible: the closest the app could get was a
session *titled* "watch the video", attached to some promise chosen for it.

It is also why assigning a shared link felt arbitrary. The bot was not ranking
promises badly — it was forced to produce a container before it could save
anything, and when nothing matched it created a throwaway non-recurring promise
purely to hold the session (see `callback_handlers.py`, the `is_one_time`
branch). Those rows are real promises in every report that counts promises.

Dropping the constraint makes the promise what it always should have been: an
optional grouping. A session now needs only a time; it may point at content, at
a promise, at both, or at neither. Existing rows are unaffected — every one of
them keeps the promise it already has.

The foreign key stays as it is. ON DELETE CASCADE is still correct for a
session that names a promise, and it simply does not apply to one that does not.

Revision ID: 037_plan_session_optional_promise
Revises: 036_video_transcript
Create Date: 2026-09-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "037_plan_session_optional_promise"
down_revision: Union[str, None] = "036_video_transcript"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "plan_sessions",
        "promise_uuid",
        existing_type=sa.Text(),
        nullable=True,
    )


def downgrade() -> None:
    # A promise-less session cannot be represented by the old schema, so the
    # rows this feature creates are deleted rather than silently reassigned to
    # a promise they were never about.
    op.execute("DELETE FROM plan_sessions WHERE promise_uuid IS NULL")
    op.alter_column(
        "plan_sessions",
        "promise_uuid",
        existing_type=sa.Text(),
        nullable=False,
    )
