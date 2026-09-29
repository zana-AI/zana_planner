"""A selected parent must not bring back a child the learner excluded."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from tm_bot.repositories.flashcard_review_repo import FlashcardCardRepository


def test_exact_deck_selection_preserves_due_first_queue_and_counts():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    now = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE flashcard_deck (deck_id TEXT PRIMARY KEY, parent_deck_id TEXT)"))
        connection.execute(text("CREATE TABLE flashcard_note (note_id TEXT PRIMARY KEY, user_id TEXT, deck_id TEXT, created_at DATETIME)"))
        connection.execute(text("""CREATE TABLE flashcard_card (
            card_id TEXT PRIMARY KEY, note_id TEXT, template_ord INTEGER, state INTEGER,
            step INTEGER, stability REAL, difficulty REAL, due DATETIME,
            last_review DATETIME, reps INTEGER, lapses INTEGER, suspended BOOLEAN
        )"""))
        for deck_id, parent_id in [("root", None), ("a", "root"), ("a-child", "a"), ("b", "root")]:
            connection.execute(text("INSERT INTO flashcard_deck VALUES (:id, :parent)"), {"id": deck_id, "parent": parent_id})

        def card(card_id, deck_id, reps, due, *, user_id="1", suspended=False):
            connection.execute(text("INSERT INTO flashcard_note VALUES (:id, :user, :deck, :created)"), {
                "id": card_id, "user": user_id, "deck": deck_id, "created": now - timedelta(days=2),
            })
            connection.execute(text("""INSERT INTO flashcard_card VALUES (
                :id, :note, 0, 2, 0, 1, 1, :due, NULL, :reps, 0, :suspended
            )"""), {"id": card_id, "note": card_id, "due": due, "reps": reps, "suspended": suspended})

        card("parent-due", "a", 1, now - timedelta(days=3))
        card("child-due", "a-child", 1, now - timedelta(days=2))
        card("child-new", "a-child", 0, now)
        card("sibling-due", "b", 1, now - timedelta(days=1))
        card("other-user", "a", 1, now - timedelta(days=4), user_id="2")
        card("suspended", "a", 1, now - timedelta(days=5), suspended=True)

    repo = FlashcardCardRepository()
    with Session(engine) as session:
        # The old one-deck API still expands a whole subtree.
        subtree = repo.get_due_queue(session, "1", now, new_limit=1, deck_id="a")
        assert {row["card_id"] for row in subtree} == {"parent-due", "child-due", "child-new"}

        # The new selection uses exact decks, with one new-card cap across them.
        selected = repo.get_due_queue(session, "1", now, new_limit=1, deck_ids=["a", "b", "b"])
        assert {row["card_id"] for row in selected} == {"parent-due", "sibling-due"}
        assert repo.counts(session, "1", now, deck_ids=["a", "b"]) == {
            "due": 2, "new": 0, "studied": 2, "total": 2,
        }

        without_child = repo.get_due_queue(session, "1", now, new_limit=1, exclude_deck_ids=["a-child"])
        assert {row["card_id"] for row in without_child} == {"parent-due", "sibling-due"}
        assert repo.counts(session, "1", now, exclude_deck_ids=["a-child"])["due"] == 2

        combined = repo.get_due_queue(session, "1", now, new_limit=1, deck_ids=["a", "a-child", "b"])
        assert [row["reps"] for row in combined] == [1, 1, 1, 0]
        assert repo.counts(session, "1", now, deck_ids=["a", "a-child", "b"])["new"] == 1
