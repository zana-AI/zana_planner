"""Server-first caption jobs and scoped relay identities.

Revision ID: 042_caption_relay
Revises: 041_video_transcript_fetch_queue
"""
from alembic import op
import sqlalchemy as sa

revision = "042_caption_relay"
down_revision = "041_video_transcript_fetch_queue"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "caption_relay_devices",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), unique=True),
        sa.Column("pairing_hash", sa.Text(), unique=True),
        sa.Column("pairing_expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_claim_at", sa.DateTime(timezone=True)),
    )
    op.add_column("video_transcript_fetch_jobs", sa.Column("fetch_stage", sa.Text(), nullable=False, server_default="server"))
    op.add_column("video_transcript_fetch_jobs", sa.Column("lease_token", sa.Text()))
    op.add_column("video_transcript_fetch_jobs", sa.Column("worker_id", sa.Text()))
    op.add_column("video_transcript_fetch_jobs", sa.Column("server_attempted_at", sa.DateTime(timezone=True)))
    op.create_check_constraint("check_caption_fetch_stage", "video_transcript_fetch_jobs", "fetch_stage IN ('server', 'relay')")
    # Existing jobs already attempted the cloud. Preserve retry history.
    op.execute("UPDATE video_transcript_fetch_jobs SET fetch_stage='relay', server_attempted_at=requested_at")


def downgrade():
    op.drop_constraint("check_caption_fetch_stage", "video_transcript_fetch_jobs", type_="check")
    for column in ("server_attempted_at", "worker_id", "lease_token", "fetch_stage"):
        op.drop_column("video_transcript_fetch_jobs", column)
    op.drop_table("caption_relay_devices")
