"""
Repository for flashcard scheduling: cards and the review log.

`flashcard_review_log` is APPEND ONLY. There is deliberately no update or
delete method — cards can be rebuilt by replaying the log, but the log cannot
be rebuilt from anything, and it is what the FSRS optimizer trains on.

Like flashcard_repo, methods take an explicit session: a review must update
the card and append its log row in one transaction.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

CARD_COLUMNS = (
    "card_id, note_id, template_ord, state, step, stability, difficulty, "
    "due, last_review, reps, lapses, suspended"
)

# Expands :deck into that deck plus every deck beneath it. Prepended to a query
# so filtering by a parent ("Français") also picks up its children's notes.
SUBTREE_CTE = (
    "WITH RECURSIVE sub AS ("
    " SELECT deck_id FROM flashcard_deck WHERE deck_id = :deck"
    " UNION ALL"
    " SELECT d.deck_id FROM flashcard_deck d JOIN sub s ON d.parent_deck_id = s.deck_id"
    ") "
)


def _new_id() -> str:
    return uuid.uuid4().hex


def _as_utc(value: Any) -> Optional[datetime]:
    """Force a stored timestamp to timezone-aware UTC.

    FSRS compares datetimes; mixing naive and aware raises. Anything naive that
    reaches here was stored as UTC.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class FlashcardCardRepository:
    @staticmethod
    def _decode(row: Dict[str, Any]) -> Dict[str, Any]:
        row["due"] = _as_utc(row.get("due"))
        row["last_review"] = _as_utc(row.get("last_review"))
        row["suspended"] = bool(row.get("suspended"))
        return row

    def get(self, session: Session, card_id: str) -> Optional[dict]:
        row = session.execute(
            text(f"SELECT {CARD_COLUMNS} FROM flashcard_card WHERE card_id = :c"),
            {"c": card_id},
        ).mappings().fetchone()
        return self._decode(dict(row)) if row else None

    def get_for_note(
        self, session: Session, note_id: str, template_ord: int = 0
    ) -> Optional[dict]:
        row = session.execute(
            text(
                f"SELECT {CARD_COLUMNS} FROM flashcard_card "
                "WHERE note_id = :n AND template_ord = :o"
            ),
            {"n": note_id, "o": template_ord},
        ).mappings().fetchone()
        return self._decode(dict(row)) if row else None

    def create(
        self,
        session: Session,
        note_id: str,
        due: datetime,
        template_ord: int = 0,
    ) -> dict:
        card_id = _new_id()
        session.execute(
            text(
                "INSERT INTO flashcard_card (card_id, note_id, template_ord, due) "
                "VALUES (:c, :n, :o, :d)"
            ),
            {"c": card_id, "n": note_id, "o": template_ord, "d": due},
        )
        created = self.get(session, card_id)
        assert created is not None
        return created

    def get_or_create(
        self, session: Session, note_id: str, due: datetime, template_ord: int = 0
    ) -> dict:
        existing = self.get_for_note(session, note_id, template_ord)
        return existing or self.create(session, note_id, due, template_ord)

    def update_scheduling(
        self,
        session: Session,
        card_id: str,
        *,
        state: int,
        step: Optional[int],
        stability: Optional[float],
        difficulty: Optional[float],
        due: datetime,
        last_review: Optional[datetime],
        increment_reps: bool = True,
        increment_lapses: bool = False,
    ) -> None:
        session.execute(
            text(
                "UPDATE flashcard_card SET state = :st, step = :sp, stability = :s, "
                "difficulty = :d, due = :due, last_review = :lr, "
                "reps = reps + :ri, lapses = lapses + :li WHERE card_id = :c"
            ),
            {
                "st": state,
                "sp": step,
                "s": stability,
                "d": difficulty,
                "due": due,
                "lr": last_review,
                "ri": 1 if increment_reps else 0,
                "li": 1 if increment_lapses else 0,
                "c": card_id,
            },
        )

    def get_due_queue(
        self,
        session: Session,
        user_id: str,
        now: datetime,
        new_limit: int,
        limit: int = 50,
        deck_id: Optional[str] = None,
    ) -> List[dict]:
        """Cards to study now.

        Overdue cards come first and new material only fills what is left:
        letting new cards jump a backlog is how a deck spirals out of control.
        """
        # Selecting a deck means that deck *and everything under it* — notes hang
        # off leaf decks, so an exact match on a parent would return nothing.
        prefix = SUBTREE_CTE if deck_id else ""
        deck_filter = " AND n.deck_id IN (SELECT deck_id FROM sub)" if deck_id else ""
        params: Dict[str, Any] = {"u": str(user_id), "now": now, "lim": limit}
        if deck_id:
            params["deck"] = deck_id

        due_rows = session.execute(
            text(
                f"{prefix}SELECT c.{CARD_COLUMNS.replace(', ', ', c.')} "
                "FROM flashcard_card c JOIN flashcard_note n ON n.note_id = c.note_id "
                "WHERE n.user_id = :u AND c.suspended = false AND c.reps > 0 "
                f"AND c.due <= :now{deck_filter} ORDER BY c.due LIMIT :lim"
            ),
            params,
        ).mappings().all()

        remaining = max(0, limit - len(due_rows))
        new_rows: List[Any] = []
        if remaining and new_limit > 0:
            new_params = dict(params, lim=min(remaining, new_limit))
            new_rows = session.execute(
                text(
                    f"{prefix}SELECT c.{CARD_COLUMNS.replace(', ', ', c.')} "
                    "FROM flashcard_card c JOIN flashcard_note n ON n.note_id = c.note_id "
                    "WHERE n.user_id = :u AND c.suspended = false AND c.reps = 0"
                    f"{deck_filter} ORDER BY n.created_at LIMIT :lim"
                ),
                new_params,
            ).mappings().all()

        return [self._decode(dict(r)) for r in list(due_rows) + list(new_rows)]

    def counts(
        self,
        session: Session,
        user_id: str,
        now: datetime,
        deck_id: Optional[str] = None,
    ) -> Dict[str, int]:
        prefix = SUBTREE_CTE if deck_id else ""
        deck_filter = " AND n.deck_id IN (SELECT deck_id FROM sub)" if deck_id else ""
        params: Dict[str, Any] = {"u": str(user_id), "now": now}
        if deck_id:
            params["deck"] = deck_id

        row = session.execute(
            text(
                f"{prefix}SELECT "
                "SUM(CASE WHEN c.reps > 0 AND c.due <= :now THEN 1 ELSE 0 END) AS due, "
                "SUM(CASE WHEN c.reps = 0 THEN 1 ELSE 0 END) AS new, "
                "COUNT(*) AS total "
                "FROM flashcard_card c JOIN flashcard_note n ON n.note_id = c.note_id "
                f"WHERE n.user_id = :u AND c.suspended = false{deck_filter}"
            ),
            params,
        ).mappings().fetchone()
        return {
            "due": int(row["due"] or 0),
            "new": int(row["new"] or 0),
            "total": int(row["total"] or 0),
        }


class FlashcardReviewLogRepository:
    """Append-only. No update, no delete — by design."""

    def append(
        self,
        session: Session,
        card_id: str,
        rating: int,
        review_datetime: datetime,
        review_duration_ms: Optional[int] = None,
        state_before: Optional[int] = None,
    ) -> None:
        session.execute(
            text(
                "INSERT INTO flashcard_review_log (review_id, card_id, rating, "
                "review_datetime, review_duration_ms, state_before) "
                "VALUES (:r, :c, :rt, :dt, :dur, :sb)"
            ),
            {
                "r": _new_id(),
                "c": card_id,
                "rt": rating,
                "dt": review_datetime,
                "dur": review_duration_ms,
                "sb": state_before,
            },
        )

    def list_for_card(self, session: Session, card_id: str) -> List[dict]:
        rows = session.execute(
            text(
                "SELECT review_id, card_id, rating, review_datetime, "
                "review_duration_ms, state_before FROM flashcard_review_log "
                "WHERE card_id = :c ORDER BY review_datetime"
            ),
            {"c": card_id},
        ).mappings().all()
        return [dict(r) for r in rows]

    def list_for_user(self, session: Session, user_id: str) -> List[dict]:
        """Every review by a user, oldest first — the optimizer's input."""
        rows = session.execute(
            text(
                "SELECT l.review_id, l.card_id, l.rating, l.review_datetime, "
                "l.review_duration_ms, l.state_before "
                "FROM flashcard_review_log l "
                "JOIN flashcard_card c ON c.card_id = l.card_id "
                "JOIN flashcard_note n ON n.note_id = c.note_id "
                "WHERE n.user_id = :u ORDER BY l.review_datetime"
            ),
            {"u": str(user_id)},
        ).mappings().all()
        return [dict(r) for r in rows]
