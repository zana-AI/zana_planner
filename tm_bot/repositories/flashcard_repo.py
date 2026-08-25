"""
Repository for flashcard content: decks, notes and source references.

Follows the existing raw-SQL pattern, with one deliberate difference: methods
take an explicit `session` rather than opening their own. The scheduling side
must update a card and append its review-log row in a single transaction, and
that is only possible if the caller owns the session. `flashcard_service`
opens the session; nothing outside this package should call repositories
directly.

See migration 032_flashcards_srs for why these tables are separate from
challenge_*.
"""
from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def _new_id() -> str:
    return uuid.uuid4().hex


def normalise_key(value: str) -> str:
    """Stable comparison key built from a note's front field.

    Strips HTML, accents, case and repeated whitespace so that editing a
    definition — or re-importing the same word from a different source — finds
    the existing note instead of orphaning its review history. Only ever used
    for matching, never for display.
    """
    stripped = re.sub(r"<[^>]+>", "", value or "")
    stripped = unicodedata.normalize("NFKD", stripped)
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip().lower()


# Expands :deck into that deck plus every deck beneath it. Prepended to a query
# so filtering by a parent ("French") also reaches its children's notes.
DECK_SUBTREE_CTE = (
    "WITH RECURSIVE sub AS ("
    " SELECT deck_id FROM flashcard_deck WHERE deck_id = :deck"
    " UNION ALL"
    " SELECT d.deck_id FROM flashcard_deck d JOIN sub s ON d.parent_deck_id = s.deck_id"
    ") "
)


def _decode_json(row: Dict[str, Any], *fields: str) -> Dict[str, Any]:
    for field in fields:
        value = row.get(field)
        if isinstance(value, str):
            row[field] = json.loads(value)
    return row


class FlashcardDeckRepository:
    def get(self, session: Session, deck_id: str) -> Optional[dict]:
        row = session.execute(
            text(
                "SELECT deck_id, user_id, name, parent_deck_id, promise_id "
                "FROM flashcard_deck WHERE deck_id = :d"
            ),
            {"d": deck_id},
        ).mappings().fetchone()
        return dict(row) if row else None

    def list_for_user(self, session: Session, user_id: str) -> List[dict]:
        rows = session.execute(
            text(
                "SELECT deck_id, user_id, name, parent_deck_id, promise_id "
                "FROM flashcard_deck WHERE user_id = :u ORDER BY name"
            ),
            {"u": str(user_id)},
        ).mappings().all()
        return [dict(r) for r in rows]

    def list_roots_with_counts(
        self, session: Session, user_id: str, now: datetime
    ) -> List[dict]:
        """Top-level decks with counts aggregated over their whole subtree.

        Notes always hang off leaf decks ("French::B1::Édito B1 Livre"), so a
        root's totals have to be summed recursively — counting only its direct
        notes would report zero for every root.
        """
        rows = session.execute(
            text(
                """
                WITH RECURSIVE tree AS (
                    SELECT deck_id AS root_id, deck_id
                    FROM flashcard_deck
                    WHERE user_id = :u AND parent_deck_id IS NULL
                  UNION ALL
                    SELECT t.root_id, d.deck_id
                    FROM flashcard_deck d JOIN tree t ON d.parent_deck_id = t.deck_id
                )
                SELECT r.deck_id, r.name,
                       count(c.card_id) AS total,
                       count(c.card_id) FILTER (
                           WHERE c.suspended = false AND c.reps > 0 AND c.due <= :now
                       ) AS due,
                       count(c.card_id) FILTER (
                           WHERE c.suspended = false AND c.reps = 0
                       ) AS new
                FROM flashcard_deck r
                JOIN tree t ON t.root_id = r.deck_id
                LEFT JOIN flashcard_note n ON n.deck_id = t.deck_id
                LEFT JOIN flashcard_card c ON c.note_id = n.note_id
                WHERE r.user_id = :u AND r.parent_deck_id IS NULL
                GROUP BY r.deck_id, r.name
                ORDER BY r.name
                """
            ),
            {"u": str(user_id), "now": now},
        ).mappings().all()
        return [dict(r) for r in rows]

    def list_by_promise(
        self, session: Session, user_id: str, now: datetime
    ) -> List[dict]:
        """Decks attached to a promise, with counts over each deck's subtree.

        Same recursive shape as `list_roots_with_counts`, but rooted at decks
        carrying a `promise_id` instead of at parentless decks — a promise can
        own a mid-tree deck ("French::B1") without owning its siblings.
        """
        rows = session.execute(
            text(
                """
                WITH RECURSIVE tree AS (
                    SELECT deck_id AS root_id, deck_id
                    FROM flashcard_deck
                    WHERE user_id = :u AND promise_id IS NOT NULL
                  UNION ALL
                    SELECT t.root_id, d.deck_id
                    FROM flashcard_deck d JOIN tree t ON d.parent_deck_id = t.deck_id
                )
                SELECT r.deck_id, r.name, r.promise_id,
                       count(c.card_id) AS total,
                       count(c.card_id) FILTER (
                           WHERE c.suspended = false AND c.reps > 0 AND c.due <= :now
                       ) AS due,
                       count(c.card_id) FILTER (
                           WHERE c.suspended = false AND c.reps = 0
                       ) AS new
                FROM flashcard_deck r
                JOIN tree t ON t.root_id = r.deck_id
                LEFT JOIN flashcard_note n ON n.deck_id = t.deck_id
                LEFT JOIN flashcard_card c ON c.note_id = n.note_id
                WHERE r.user_id = :u AND r.promise_id IS NOT NULL
                GROUP BY r.deck_id, r.name, r.promise_id
                ORDER BY r.name
                """
            ),
            {"u": str(user_id), "now": now},
        ).mappings().all()
        return [dict(r) for r in rows]

    def find_promise_for_deck(self, session: Session, deck_id: str) -> Optional[str]:
        """The promise owning this deck, or the nearest ancestor that has one.

        Notes hang off leaf decks while the promise is attached at the root, so
        a leaf has to look upward. Returns the closest match, letting a subtree
        be assigned to its own promise later without disturbing its siblings.
        """
        row = session.execute(
            text(
                """
                WITH RECURSIVE up AS (
                    SELECT deck_id, parent_deck_id, promise_id, 0 AS depth
                    FROM flashcard_deck WHERE deck_id = :d
                  UNION ALL
                    SELECT p.deck_id, p.parent_deck_id, p.promise_id, up.depth + 1
                    FROM flashcard_deck p JOIN up ON up.parent_deck_id = p.deck_id
                )
                SELECT promise_id FROM up
                WHERE promise_id IS NOT NULL
                ORDER BY depth
                LIMIT 1
                """
            ),
            {"d": deck_id},
        ).fetchone()
        return row[0] if row else None

    def set_promise(
        self, session: Session, user_id: str, deck_id: str, promise_id: Optional[str]
    ) -> bool:
        """Attach a deck to a promise, or detach it when `promise_id` is None."""
        result = session.execute(
            text(
                "UPDATE flashcard_deck SET promise_id = :p "
                "WHERE deck_id = :d AND user_id = :u"
            ),
            {"p": promise_id, "d": deck_id, "u": str(user_id)},
        )
        return result.rowcount > 0

    def reparent(
        self, session: Session, user_id: str, deck_id: str, parent_deck_id: Optional[str]
    ) -> bool:
        """Move a deck under a different parent. Notes and cards follow untouched."""
        result = session.execute(
            text(
                "UPDATE flashcard_deck SET parent_deck_id = :p "
                "WHERE deck_id = :d AND user_id = :u"
            ),
            {"p": parent_deck_id, "d": deck_id, "u": str(user_id)},
        )
        return result.rowcount > 0

    def _find_child(
        self, session: Session, user_id: str, name: str, parent_id: Optional[str]
    ) -> Optional[dict]:
        # NULL != NULL in SQL, so the root level needs its own branch.
        if parent_id is None:
            sql = (
                "SELECT deck_id, user_id, name, parent_deck_id FROM flashcard_deck "
                "WHERE user_id = :u AND name = :n AND parent_deck_id IS NULL"
            )
            params = {"u": str(user_id), "n": name}
        else:
            sql = (
                "SELECT deck_id, user_id, name, parent_deck_id FROM flashcard_deck "
                "WHERE user_id = :u AND name = :n AND parent_deck_id = :p"
            )
            params = {"u": str(user_id), "n": name, "p": parent_id}
        row = session.execute(text(sql), params).mappings().fetchone()
        return dict(row) if row else None

    def get_or_create_path(self, session: Session, user_id: str, path: str) -> dict:
        """Resolve a "Parent::Child" path, creating missing levels."""
        parent_id: Optional[str] = None
        deck: Optional[dict] = None

        for part in [p.strip() for p in path.split("::") if p.strip()]:
            deck = self._find_child(session, user_id, part, parent_id)
            if deck is None:
                deck_id = _new_id()
                session.execute(
                    text(
                        "INSERT INTO flashcard_deck (deck_id, user_id, name, parent_deck_id) "
                        "VALUES (:d, :u, :n, :p)"
                    ),
                    {"d": deck_id, "u": str(user_id), "n": part, "p": parent_id},
                )
                deck = {
                    "deck_id": deck_id,
                    "user_id": str(user_id),
                    "name": part,
                    "parent_deck_id": parent_id,
                }
            parent_id = deck["deck_id"]

        if deck is None:
            raise ValueError(f"Empty deck path: {path!r}")
        return deck


class FlashcardNoteRepository:
    _COLUMNS = (
        "note_id, user_id, deck_id, note_type, fields, source_key, source, "
        "created_at, updated_at"
    )

    def get(self, session: Session, note_id: str) -> Optional[dict]:
        row = session.execute(
            text(f"SELECT {self._COLUMNS} FROM flashcard_note WHERE note_id = :n"),
            {"n": note_id},
        ).mappings().fetchone()
        return _decode_json(dict(row), "fields") if row else None

    def get_by_source_key(
        self, session: Session, user_id: str, source_key: str
    ) -> Optional[dict]:
        row = session.execute(
            text(
                f"SELECT {self._COLUMNS} FROM flashcard_note "
                "WHERE user_id = :u AND source_key = :k"
            ),
            {"u": str(user_id), "k": source_key},
        ).mappings().fetchone()
        return _decode_json(dict(row), "fields") if row else None

    def list_for_user(
        self,
        session: Session,
        user_id: str,
        deck_id: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 500,
    ) -> List[dict]:
        # A deck means that deck and everything under it. Notes hang off leaf
        # decks, so an exact match on a parent silently returns nothing.
        prefix = DECK_SUBTREE_CTE if deck_id else ""
        sql = f"{prefix}SELECT {self._COLUMNS} FROM flashcard_note WHERE user_id = :u"
        params: Dict[str, Any] = {"u": str(user_id), "lim": limit}
        if deck_id:
            sql += " AND deck_id IN (SELECT deck_id FROM sub)"
            params["deck"] = deck_id
        if search:
            # source_key is already normalised, so search the same way.
            sql += " AND source_key LIKE :q"
            params["q"] = f"%{normalise_key(search)}%"
        sql += " ORDER BY updated_at DESC LIMIT :lim"

        rows = session.execute(text(sql), params).mappings().all()
        return [_decode_json(dict(r), "fields") for r in rows]

    def upsert(
        self,
        session: Session,
        user_id: str,
        deck_id: str,
        fields: Dict[str, Any],
        note_type: str = "vocab",
        source: Optional[str] = None,
    ) -> dict:
        """Create or update a note, matched on the normalised front field.

        Sets `_created` on the result so importers can report what changed.
        """
        key = normalise_key(fields.get("front", ""))
        if not key:
            raise ValueError("Note must have a non-empty 'front' field")

        payload = json.dumps(fields, ensure_ascii=False)
        existing = self.get_by_source_key(session, user_id, key)

        if existing:
            session.execute(
                text(
                    "UPDATE flashcard_note SET fields = :f, note_type = :t, "
                    "deck_id = :d, source = :s, updated_at = now() "
                    "WHERE note_id = :n"
                ),
                {
                    "f": payload,
                    "t": note_type,
                    "d": deck_id,
                    "s": source,
                    "n": existing["note_id"],
                },
            )
            existing.update(fields=fields, note_type=note_type, deck_id=deck_id)
            existing["_created"] = False
            return existing

        note_id = _new_id()
        session.execute(
            text(
                "INSERT INTO flashcard_note (note_id, user_id, deck_id, note_type, "
                "fields, source_key, source) "
                "VALUES (:n, :u, :d, :t, :f, :k, :s)"
            ),
            {
                "n": note_id,
                "u": str(user_id),
                "d": deck_id,
                "t": note_type,
                "f": payload,
                "k": key,
                "s": source,
            },
        )
        created = self.get(session, note_id)
        assert created is not None
        created["_created"] = True
        return created

    def update_fields(
        self,
        session: Session,
        note_id: str,
        fields: Dict[str, Any],
        note_type: Optional[str] = None,
        deck_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Edit an existing note in place.

        `source_key` is recomputed, so renaming the front field re-keys the
        note. Its card and history follow the note, because they hang off
        note_id rather than the key.
        """
        note = self.get(session, note_id)
        if note is None:
            return None

        merged = {**note["fields"], **fields}
        key = normalise_key(merged.get("front", ""))
        if not key:
            raise ValueError("Note must have a non-empty 'front' field")

        session.execute(
            text(
                "UPDATE flashcard_note SET fields = :f, source_key = :k, "
                "note_type = COALESCE(:t, note_type), "
                "deck_id = COALESCE(:d, deck_id), updated_at = now() "
                "WHERE note_id = :n"
            ),
            {
                "f": json.dumps(merged, ensure_ascii=False),
                "k": key,
                "t": note_type,
                "d": deck_id,
                "n": note_id,
            },
        )
        return self.get(session, note_id)

    def delete(self, session: Session, note_id: str) -> None:
        """Delete a note and, by cascade, its cards and their review history."""
        session.execute(
            text("DELETE FROM flashcard_note WHERE note_id = :n"), {"n": note_id}
        )


class FlashcardReferenceRepository:
    """Links from a note into the source material.

    Targets are the content tables the ingestion pipeline already fills:
    `content` (article/episode), `content_segment` (a timed span — this is how
    a card points at a moment in a video or podcast), `content_highlight` (a
    PDF selection) and `content_asset` (a file). `locator` carries any position
    finer than a row can express.
    """

    _COLUMNS = (
        "reference_id, note_id, kind, content_id, asset_id, segment_id, "
        "highlight_id, locator, label, created_at"
    )

    def list_for_note(self, session: Session, note_id: str) -> List[dict]:
        rows = session.execute(
            text(
                f"SELECT {self._COLUMNS} FROM flashcard_note_reference "
                "WHERE note_id = :n ORDER BY created_at"
            ),
            {"n": note_id},
        ).mappings().all()
        return [_decode_json(dict(r), "locator") for r in rows]

    def add(
        self,
        session: Session,
        note_id: str,
        kind: str,
        content_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        segment_id: Optional[str] = None,
        highlight_id: Optional[str] = None,
        locator: Optional[Dict[str, Any]] = None,
        label: Optional[str] = None,
    ) -> dict:
        if kind not in ("content", "segment", "highlight", "asset", "url"):
            raise ValueError(f"Unknown reference kind: {kind!r}")

        reference_id = _new_id()
        session.execute(
            text(
                "INSERT INTO flashcard_note_reference (reference_id, note_id, kind, "
                "content_id, asset_id, segment_id, highlight_id, locator, label) "
                "VALUES (:r, :n, :k, :c, :a, :sg, :h, :loc, :l)"
            ),
            {
                "r": reference_id,
                "n": note_id,
                "k": kind,
                "c": content_id,
                "a": asset_id,
                "sg": segment_id,
                "h": highlight_id,
                "loc": json.dumps(locator or {}, ensure_ascii=False),
                "l": label,
            },
        )
        return {
            "reference_id": reference_id,
            "note_id": note_id,
            "kind": kind,
            "content_id": content_id,
            "asset_id": asset_id,
            "segment_id": segment_id,
            "highlight_id": highlight_id,
            "locator": locator or {},
            "label": label,
        }

    def delete(self, session: Session, reference_id: str) -> None:
        session.execute(
            text("DELETE FROM flashcard_note_reference WHERE reference_id = :r"),
            {"r": reference_id},
        )
