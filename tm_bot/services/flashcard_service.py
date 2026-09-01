"""
Flashcard service: the session-owning layer over the flashcard repositories.

Scheduling is FSRS v6 via py-fsrs. All interval, stability and difficulty maths
lives in that library — this module only converts rows to `fsrs.Card` and back.
Do not reimplement any of it: FSRS is a fitted model, not a heuristic, and an
approximation would be wrong in ways that take months to become visible.

This is the only module outside the flashcard repositories that should open a
database session for them; a review must write the card update and its
review-log row in one transaction.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fsrs import Card, Rating, Scheduler, State

from db.postgres_db import get_db_session
from repositories.flashcard_repo import (
    FlashcardDeckRepository,
    FlashcardNoteRepository,
    FlashcardReferenceRepository,
    normalise_key,
)
from repositories.flashcard_review_repo import (
    FlashcardCardRepository,
    FlashcardReviewLogRepository,
)
from utils.logger import get_logger

logger = get_logger(__name__)

# Stock FSRS-6 parameters. Once a user has a few hundred reviews,
# `optimize_parameters` can refit these and the result should be persisted per
# user and passed to Scheduler(parameters=...).
_scheduler = Scheduler()

_decks = FlashcardDeckRepository()
_notes = FlashcardNoteRepository()
_refs = FlashcardReferenceRepository()
_cards = FlashcardCardRepository()
_log = FlashcardReviewLogRepository()

DEFAULT_NEW_PER_DAY = 20


def _row_to_fsrs_card(row: Dict[str, Any]) -> Card:
    """Column names match the dataclass, so this is a direct field copy."""
    return Card(
        state=State(row["state"]),
        step=row["step"],
        stability=row["stability"],
        difficulty=row["difficulty"],
        due=row["due"],
        last_review=row["last_review"],
    )


# --- review loop -----------------------------------------------------------


def get_queue(
    user_id: str,
    limit: int = 50,
    new_limit: int = DEFAULT_NEW_PER_DAY,
    deck_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Cards due now, with their note content and any source references."""
    now = datetime.now(timezone.utc)
    with get_db_session() as session:
        rows = _cards.get_due_queue(
            session, user_id, now, new_limit=new_limit, limit=limit, deck_id=deck_id
        )
        cards: List[Dict[str, Any]] = []
        for row in rows:
            note = _notes.get(session, row["note_id"])
            if note is None:
                continue
            deck = _decks.get(session, note["deck_id"])
            cards.append(
                {
                    "card_id": row["card_id"],
                    "note_id": note["note_id"],
                    "note_type": note["note_type"],
                    "deck": deck["name"] if deck else "",
                    "fields": note["fields"],
                    "state": row["state"],
                    "reps": row["reps"],
                    "due": row["due"].isoformat(),
                    "references": _refs.list_for_note(session, note["note_id"]),
                }
            )
        return {
            "cards": cards,
            "counts": _cards.counts(session, user_id, now, deck_id=deck_id),
        }


def review_card(
    user_id: str,
    card_id: str,
    rating: int,
    duration_ms: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Apply one review. Returns None if the card is not this user's."""
    if rating not in (1, 2, 3, 4):
        raise ValueError(f"rating must be 1-4, got {rating!r}")

    review_time = now or datetime.now(timezone.utc)

    with get_db_session() as session:
        card = _cards.get(session, card_id)
        if card is None:
            return None

        # A card is only reachable through its note's owner; without this any
        # authenticated user could rate someone else's cards.
        note = _notes.get(session, card["note_id"])
        if note is None or str(note["user_id"]) != str(user_id):
            return None

        state_before = card["state"]
        updated, _ = _scheduler.review_card(
            _row_to_fsrs_card(card),
            Rating(rating),
            review_datetime=review_time,
            review_duration=duration_ms,
        )

        # A lapse is forgetting something that had graduated to Review.
        # Failing a card that was never learned is not forgetting it.
        is_lapse = rating == Rating.Again.value and state_before == State.Review.value

        _cards.update_scheduling(
            session,
            card_id,
            state=updated.state.value,
            step=updated.step,
            stability=updated.stability,
            difficulty=updated.difficulty,
            due=updated.due,
            last_review=updated.last_review,
            increment_lapses=is_lapse,
        )
        _log.append(
            session,
            card_id=card_id,
            rating=rating,
            review_datetime=review_time,
            review_duration_ms=duration_ms,
            state_before=state_before,
        )

        refreshed = _cards.get(session, card_id)
        assert refreshed is not None
        result = {
            "card_id": card_id,
            "state": refreshed["state"],
            "reps": refreshed["reps"],
            "lapses": refreshed["lapses"],
            "due": refreshed["due"].isoformat(),
            "stability": refreshed["stability"],
            "difficulty": refreshed["difficulty"],
            "counts": _cards.counts(session, user_id, datetime.now(timezone.utc)),
        }
        deck_id = note["deck_id"]

    # Outside the transaction above: crediting must never be able to roll back a
    # review. The review is the thing that matters and it is already durable.
    result["credits_minutes"] = _award_review_credit(user_id, deck_id)
    return result


def _award_review_credit(user_id: str, deck_id: str) -> float:
    """Credit one rated card to the promise that owns this card's deck.

    Walks up the deck tree because notes hang off leaf decks ("French::B1::
    Édito B1 Livre") while the promise is attached at the root. Returns the
    running credit total for today, or 0.0 when the deck belongs to no promise —
    an unattached deck is still perfectly usable, it just scores nothing.
    """
    from services import credits as credit_rules

    try:
        with get_db_session() as session:
            promise_id = _decks.find_promise_for_deck(session, deck_id)
        if not promise_id:
            return 0.0

        from repositories.actions_repo import ActionsRepository

        return ActionsRepository().accumulate_credit(
            user_id,
            promise_id,
            credit_rules.flashcard_credits(1),
            source="flashcards",
        )
    except Exception:  # crediting is an add-on; a review must still count
        logger.exception("failed to credit flashcard review")
        return 0.0


# --- authoring -------------------------------------------------------------


def list_decks(user_id: str) -> List[dict]:
    with get_db_session() as session:
        return _decks.list_for_user(session, user_id)


def deck_summary(user_id: str) -> List[dict]:
    """Top-level decks with their due/new/total counts.

    Drives the study entry points elsewhere in the app, so a new subject or
    language shows up on its own once its first deck exists — nothing about it
    is specific to French.
    """
    with get_db_session() as session:
        return _decks.list_roots_with_counts(
            session, user_id, datetime.now(timezone.utc)
        )


def decks_by_promise(user_id: str) -> Dict[str, List[dict]]:
    """{promise_uuid: [deck, ...]} for decks attached to a promise.

    Feeds the Play launcher, which lists what a promise can actually be *done*
    with. Decks with nothing to study are still returned — a promise showing
    "all caught up" is more useful than one whose deck silently vanishes.
    """
    with get_db_session() as session:
        rows = _decks.list_by_promise(session, user_id, datetime.now(timezone.utc))
    grouped: Dict[str, List[dict]] = {}
    for row in rows:
        grouped.setdefault(row["promise_id"], []).append(
            {
                "deck_id": row["deck_id"],
                "name": row["name"],
                "due": int(row["due"]),
                "new": int(row["new"]),
                "total": int(row["total"]),
            }
        )
    return grouped


def set_deck_promise(user_id: str, deck_id: str, promise_id: Optional[str]) -> bool:
    with get_db_session() as session:
        return _decks.set_promise(session, user_id, deck_id, promise_id)


def list_notes(
    user_id: str,
    deck_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 500,
) -> List[dict]:
    with get_db_session() as session:
        notes = _notes.list_for_user(session, user_id, deck_id, search, limit)
        for note in notes:
            note["references"] = _refs.list_for_note(session, note["note_id"])
            card = _cards.get_for_note(session, note["note_id"])
            # Surface scheduling read-only, so the editor can show how a card
            # is actually going without being able to corrupt it.
            note["card"] = (
                {
                    "card_id": card["card_id"],
                    "reps": card["reps"],
                    "lapses": card["lapses"],
                    "due": card["due"].isoformat(),
                    "stability": card["stability"],
                    "difficulty": card["difficulty"],
                    "suspended": card["suspended"],
                }
                if card
                else None
            )
        return notes


def create_note(
    user_id: str,
    deck_path: str,
    fields: Dict[str, Any],
    note_type: str = "vocab",
    source: Optional[str] = "manual",
    references: Optional[List[Dict[str, Any]]] = None,
) -> dict:
    """Author a new note and give it a card that is due immediately."""
    with get_db_session() as session:
        deck = _decks.get_or_create_path(session, user_id, deck_path)
        note = _notes.upsert(
            session, user_id, deck["deck_id"], fields, note_type, source
        )
        _cards.get_or_create(
            session, note["note_id"], due=datetime.now(timezone.utc)
        )
        for reference in references or []:
            _refs.add(session, note["note_id"], **reference)
        note["references"] = _refs.list_for_note(session, note["note_id"])
        return note


def save_context_note(
    user_id: str,
    deck_path: str,
    fields: Dict[str, Any],
    note_type: str = "vocab",
    references: Optional[List[Dict[str, Any]]] = None,
) -> dict:
    """Save a video-mined word while preserving any existing card.

    A normal authoring upsert replaces fields and deck by design. Subtitle
    mining is additive: if the word already exists, keep its definition, deck,
    scheduling and primary example, then attach this video as another context.
    """
    key = normalise_key(fields.get("front", ""))
    if not key:
        raise ValueError("Note must have a non-empty 'front' field")

    with get_db_session() as session:
        existing = _notes.get_by_source_key(session, user_id, key)
        if existing is None:
            deck = _decks.get_or_create_path(session, user_id, deck_path)
            note = _notes.upsert(
                session,
                user_id,
                deck["deck_id"],
                fields,
                note_type,
                "youtube",
            )
            _cards.get_or_create(
                session, note["note_id"], due=datetime.now(timezone.utc)
            )
            context_added = True
        else:
            note = existing
            existing_fields = dict(existing.get("fields") or {})
            additions: Dict[str, Any] = {}

            # Fill genuinely missing learning content, never replace authored
            # definitions or examples merely because a word was clicked.
            for field_name in ("back", "example"):
                if not existing_fields.get(field_name) and fields.get(field_name):
                    additions[field_name] = fields[field_name]

            source_names = (
                "source_sentence",
                "source_video_id",
                "source_title",
                "source_start",
                "source_url",
                "source_language",
            )
            incoming_context = {
                name: fields[name] for name in source_names if fields.get(name) is not None
            }
            same_primary = (
                existing_fields.get("source_url") == incoming_context.get("source_url")
                and existing_fields.get("source_start") == incoming_context.get("source_start")
            )
            if not existing_fields.get("source_url"):
                additions.update(incoming_context)
                context_added = bool(incoming_context)
            elif same_primary:
                context_added = False
            else:
                contexts = existing_fields.get("video_contexts")
                contexts = list(contexts) if isinstance(contexts, list) else []
                already_listed = any(
                    isinstance(item, dict)
                    and item.get("source_url") == incoming_context.get("source_url")
                    and item.get("source_start") == incoming_context.get("source_start")
                    for item in contexts
                )
                if incoming_context and not already_listed:
                    contexts.append(incoming_context)
                    additions["video_contexts"] = contexts
                    context_added = True
                else:
                    context_added = False

            if additions:
                note = _notes.update_fields(session, existing["note_id"], additions) or existing
            note["_created"] = False

        current_references = _refs.list_for_note(session, note["note_id"])
        for reference in references or []:
            locator = reference.get("locator") or {}
            duplicate = any(
                existing_ref.get("kind") == reference.get("kind")
                and (existing_ref.get("locator") or {}) == locator
                for existing_ref in current_references
            )
            if not duplicate:
                current_references.append(
                    _refs.add(session, note["note_id"], **reference)
                )

        note["references"] = current_references
        note["_context_added"] = context_added
        return note


def update_note(
    user_id: str,
    note_id: str,
    fields: Dict[str, Any],
    note_type: Optional[str] = None,
    deck_path: Optional[str] = None,
) -> Optional[dict]:
    """Edit a note's content.

    Scheduling is untouched: editing a definition must never reset how well the
    word is known.
    """
    with get_db_session() as session:
        note = _notes.get(session, note_id)
        if note is None or str(note["user_id"]) != str(user_id):
            return None

        deck_id = None
        if deck_path:
            deck_id = _decks.get_or_create_path(session, user_id, deck_path)["deck_id"]

        updated = _notes.update_fields(session, note_id, fields, note_type, deck_id)
        if updated:
            updated["references"] = _refs.list_for_note(session, note_id)
        return updated


def delete_note(user_id: str, note_id: str) -> bool:
    """Delete a note, its cards and their review history (cascade)."""
    with get_db_session() as session:
        note = _notes.get(session, note_id)
        if note is None or str(note["user_id"]) != str(user_id):
            return False
        _notes.delete(session, note_id)
        return True


def add_reference(user_id: str, note_id: str, **reference: Any) -> Optional[dict]:
    """Attach a source reference — a PDF highlight, a video/podcast moment, a URL."""
    with get_db_session() as session:
        note = _notes.get(session, note_id)
        if note is None or str(note["user_id"]) != str(user_id):
            return None
        return _refs.add(session, note_id, **reference)


def delete_reference(user_id: str, note_id: str, reference_id: str) -> bool:
    with get_db_session() as session:
        note = _notes.get(session, note_id)
        if note is None or str(note["user_id"]) != str(user_id):
            return False
        _refs.delete(session, reference_id)
        return True


def optimize_parameters(user_id: str) -> List[float]:
    """Refit FSRS parameters to this user's own review history.

    Needs a few hundred reviews before it beats the stock parameters, so run it
    periodically rather than per review.
    """
    from fsrs import Optimizer

    with get_db_session() as session:
        logs = _log.list_for_user(session, user_id)
    return Optimizer(logs).compute_optimal_parameters()
