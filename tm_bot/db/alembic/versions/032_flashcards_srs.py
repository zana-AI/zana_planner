"""Flashcards: a spaced-repetition engine, separate from the challenge engine

Answers the open question in docs/CHALLENGES_DESIGN.md §11 — "Do flashcards
need spaced-repetition (re-surface missed cards) in v1, or simple linear
decks?" — by adding SRS as its own engine rather than by bending
`challenge_*`.

The two engines solve different problems and deliberately do NOT share tables:

  challenge_*        content-scheduled. `challenge_decks.release_at` releases a
                     deck to a whole cohort on a date; a deck is attempted once
                     (`get_due_deck` excludes decks with any attempt) and never
                     returns. `is_correct` is binary and server-graded, and
                     feeds score/streak/leaderboard.

  flashcard_*        learner-scheduled. Each card returns when *this* user is
                     about to forget it, driven by FSRS v6 (py-fsrs). Ratings
                     are the learner's own 1-4 self-assessment, which is the
                     signal the memory model needs — binary correctness cannot
                     drive it.

Bridges between them are one-way and additive (a completed challenge deck may
seed personal cards; a content_highlight may become a note). Review state must
never be stored in `challenge_attempts`, and `challenge_decks.release_at` must
never drive what gets reviewed.

Schema conventions: `id`/`user_id` are Text to match the rest of the database.
Timestamps here are real `timestamptz` rather than the ISO-8601 Text used by
older tables — FSRS does datetime arithmetic on `due`/`last_review` and the
review queue orders by them, so storing them as text would mean parsing on
every comparison and would make correct indexing impossible.

Revision ID: 032_flashcards_srs
Revises: 031_club_leaderboard_schedule
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "032_flashcards_srs"
down_revision: Union[str, None] = "031_club_leaderboard_schedule"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Decks nest via parent_id rather than encoding a path in the name.
    op.create_table(
        "flashcard_deck",
        sa.Column("deck_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_deck_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("deck_id"),
        sa.ForeignKeyConstraint(["parent_deck_id"], ["flashcard_deck.deck_id"]),
    )
    op.create_index("ix_flashcard_deck_user", "flashcard_deck", ["user_id"])

    # Authored content. `fields` is JSONB so note kinds (vocab, grammar, ...)
    # can differ without a migration each time.
    op.create_table(
        "flashcard_note",
        sa.Column("note_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("deck_id", sa.Text(), nullable=False),
        sa.Column("note_type", sa.Text(), nullable=False, server_default="vocab"),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default="{}"),
        # Normalised front field: makes imports idempotent and is how review
        # history survives an edit to a definition.
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("note_id"),
        sa.ForeignKeyConstraint(["deck_id"], ["flashcard_deck.deck_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "source_key", name="uq_flashcard_note_user_key"),
    )
    op.create_index("ix_flashcard_note_deck", "flashcard_note", ["deck_id"])

    # Where a card points in the source material. Kept as its own table (not a
    # JSON blob on the note) so it can carry real foreign keys into the content
    # tables the ingestion pipeline already populates, and so one note can have
    # several references.
    op.create_table(
        "flashcard_note_reference",
        sa.Column("reference_id", sa.Text(), nullable=False),
        sa.Column("note_id", sa.Text(), nullable=False),
        # 'content'   -> whole item (article, episode)
        # 'segment'   -> a timed span of audio/video (content_segment.start_ms)
        # 'highlight' -> a PDF selection (content_highlight page + rects)
        # 'asset'     -> a file, e.g. a PDF page
        # 'url'       -> anything not ingested into `content`
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("content_id", sa.Text(), nullable=True),
        sa.Column("asset_id", sa.Text(), nullable=True),
        sa.Column("segment_id", sa.Text(), nullable=True),
        sa.Column("highlight_id", sa.Text(), nullable=True),
        # Position finer-grained than any row can express:
        # {"page": 16, "rects": [...]} | {"start_ms": 92000, "end_ms": 105000}
        # | {"url": "https://..."}
        sa.Column("locator", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default="{}"),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("reference_id"),
        sa.ForeignKeyConstraint(["note_id"], ["flashcard_note.note_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["content_id"], ["content.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["content_asset.id"]),
        sa.ForeignKeyConstraint(["segment_id"], ["content_segment.id"]),
        sa.ForeignKeyConstraint(["highlight_id"], ["content_highlight.id"]),
        sa.CheckConstraint(
            "kind IN ('content', 'segment', 'highlight', 'asset', 'url')",
            name="check_flashcard_reference_kind",
        ),
    )
    op.create_index("ix_flashcard_note_reference_note", "flashcard_note_reference", ["note_id"])
    op.create_index("ix_flashcard_note_reference_content", "flashcard_note_reference", ["content_id"])

    # Scheduling state. These columns map 1:1 onto py-fsrs's `Card` dataclass
    # (state, step, stability, difficulty, due, last_review) so persistence is
    # a straight field copy with no translation layer.
    op.create_table(
        "flashcard_card",
        sa.Column("card_id", sa.Text(), nullable=False),
        sa.Column("note_id", sa.Text(), nullable=False),
        # 0 = front->back, 1 = reverse. Lets one note yield several cards later.
        sa.Column("template_ord", sa.Integer(), nullable=False, server_default="0"),
        # FSRS State: 1=Learning, 2=Review, 3=Relearning. There is no "new"
        # state; a never-reviewed card is Learning with reps=0, null stability.
        sa.Column("state", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("step", sa.Integer(), nullable=True),
        sa.Column("stability", sa.Float(), nullable=True),
        sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("due", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_review", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lapses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suspended", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("card_id"),
        sa.ForeignKeyConstraint(["note_id"], ["flashcard_note.note_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("note_id", "template_ord", name="uq_flashcard_card_note_template"),
    )
    op.create_index("ix_flashcard_card_due", "flashcard_card", ["due"])

    # APPEND ONLY. Cards can be rebuilt by replaying this; this cannot be
    # rebuilt from anything. It is also the FSRS optimizer's training input.
    op.create_table(
        "flashcard_review_log",
        sa.Column("review_id", sa.Text(), nullable=False),
        sa.Column("card_id", sa.Text(), nullable=False),
        # 1=Again 2=Hard 3=Good 4=Easy (the learner's own assessment)
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("review_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_duration_ms", sa.Integer(), nullable=True),
        sa.Column("state_before", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("review_id"),
        sa.ForeignKeyConstraint(["card_id"], ["flashcard_card.card_id"], ondelete="CASCADE"),
        sa.CheckConstraint("rating BETWEEN 1 AND 4", name="check_flashcard_rating"),
    )
    op.create_index("ix_flashcard_review_log_card", "flashcard_review_log", ["card_id"])
    op.create_index("ix_flashcard_review_log_datetime", "flashcard_review_log", ["review_datetime"])


def downgrade() -> None:
    op.drop_table("flashcard_review_log")
    op.drop_table("flashcard_card")
    op.drop_table("flashcard_note_reference")
    op.drop_table("flashcard_note")
    op.drop_table("flashcard_deck")
