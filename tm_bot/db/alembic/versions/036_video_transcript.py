"""Cache YouTube transcripts so the server never has to fetch one

YouTube blocks the production IP outright — the datacenter address fails both
yt-dlp ("Sign in to confirm you're not a bot") and youtube_transcript_api
(RequestBlocked). Only *discovery* is blocked; the caption tracks themselves
serve fine from anywhere, but reaching them needs a signed URL that expires in
about seven hours, so a URL cache would be worthless.

Cues are therefore fetched from a residential connection
(scripts/fetch_transcripts.py) and stored here. The server only ever reads this
table, which also takes the fetch off the request path: rendering a transcript
becomes one indexed lookup instead of a multi-second scrape that fails in
production anyway.

Keyed by video_id rather than content_id on purpose. The same video can be
several users' content, and a flashcard cites a video without any content row
existing at all — the transcript belongs to the video, not to anyone's copy.

Revision ID: 036_video_transcript
Revises: 035_action_credits
Create Date: 2026-09-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "036_video_transcript"
down_revision: Union[str, None] = "035_action_credits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "video_transcript",
        sa.Column("video_id", sa.Text(), primary_key=True),
        sa.Column("language", sa.Text(), nullable=True),
        # Automatic captions carry ASR errors, so the UI labels them and the
        # content pipeline knows they need a cleanup pass before becoming cards.
        sa.Column("is_generated", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        # [{"start": 177.84, "end": 181.2, "text": "..."}] in video order.
        sa.Column("cues", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cue_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        # Which fetcher produced this, so a better pass can supersede a worse one.
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'youtube_transcript_api'")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("video_transcript")
