#!/usr/bin/env python3
"""Reorganize and lightly post-process Javad's French learning content.

Run inside zana-webapp. Dry-run is the default; --apply publishes changes.
The script never touches flashcard scheduling/review tables or quiz attempts.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from typing import Any

sys.path.insert(0, "/app/tm_bot")

from sqlalchemy import text

from db.postgres_db import get_db_session
from repositories.flashcard_repo import normalise_key
from services import flashcard_service

USER_ID = "108648163"
ATENA_ID = "660762b526d849ffa4470a9e690fc2d3"
NATURALISATION_ID = "8780918c227541c089498430da290c8d"

# These are unambiguous normalization improvements from the Edito cards.
# The old front is retained in original_front for provenance.
FRONT_REWRITES = {
    "Ça me gêne.": "gêner",
    "Ça me plaît.": "plaire à",
    "Tu te trompes.": "se tromper",
    "citoyennes dès l'enfance": "citoyen / citoyenne",
    "des rapports de voyage": "rapport de voyage",
    "des règles de conduite": "règle de conduite",
    "suis": "être / suivre : suis",
}


def source_ref(session, note_id: str) -> dict[str, Any]:
    row = session.execute(text("""
        SELECT label, locator, asset_id, content_id, segment_id
        FROM flashcard_note_reference
        WHERE note_id=:note_id
        ORDER BY created_at
        LIMIT 1
    """), {"note_id": note_id}).mappings().fetchone()
    if not row:
        return {}
    result = dict(row)
    locator = result.get("locator") or {}
    if isinstance(locator, str):
        try:
            locator = json.loads(locator)
        except json.JSONDecodeError:
            locator = {}
    result["url"] = locator.get("url") if isinstance(locator, dict) else None
    return result


def video_deck_name(ref: dict[str, Any]) -> str:
    label = re.sub(r"\s+", " ", str(ref.get("label") or "YouTube video")).strip()
    # Deck names are UI labels; avoid accidental path nesting and excessive width.
    label = label.replace("::", " — ")
    return label[:120].rstrip()


def target_for(note: dict[str, Any], ref: dict[str, Any]) -> str:
    source = note.get("source") or ""
    old_path = note.get("deck_path") or ""
    if source == "vocab.md":
        leaf = old_path.rsplit("::", 1)[-1]
        leaf = {"Édito B1 Livre": "Livre"}.get(leaf, leaf)
        return f"French::Édito B1::{leaf}"
    if source == "language-reactor":
        return f"French::Language Reactor::{video_deck_name(ref)}"
    if source == "lingoda":
        return "French::Lingoda"
    return f"French::Other::{source or 'Unclassified'}"


def load_notes() -> list[dict[str, Any]]:
    with get_db_session() as session:
        rows = session.execute(text("""
          WITH RECURSIVE tree AS (
            SELECT deck_id, name, name::text AS deck_path
            FROM flashcard_deck WHERE user_id=:u AND parent_deck_id IS NULL
            UNION ALL
            SELECT d.deck_id, d.name, tree.deck_path || '::' || d.name
            FROM flashcard_deck d JOIN tree ON d.parent_deck_id=tree.deck_id
            WHERE d.user_id=:u
          )
          SELECT n.note_id, n.user_id, n.deck_id, t.deck_path, n.note_type,
                 n.fields, n.source, n.source_key
          FROM flashcard_note n JOIN tree t ON t.deck_id=n.deck_id
          WHERE n.user_id=:u ORDER BY t.deck_path, n.source_key
        """), {"u": USER_ID}).mappings().all()
        notes = []
        for row in rows:
            note = dict(row)
            if isinstance(note.get("fields"), str):
                note["fields"] = json.loads(note["fields"])
            note["reference"] = source_ref(session, note["note_id"])
            notes.append(note)
        return notes


def plan(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for note in notes:
        fields = dict(note.get("fields") or {})
        ref = note["reference"]
        old_front = fields.get("front", "")
        new_front = FRONT_REWRITES.get(old_front, old_front)
        if new_front != old_front:
            fields["original_front"] = old_front
            fields["front"] = new_front
        if note.get("source") == "language-reactor":
            if ref.get("label"):
                fields["source_title"] = ref["label"]
            if ref.get("url"):
                fields["source_url"] = ref["url"]
            if fields.get("example"):
                fields["source_context"] = fields["example"]
        elif note.get("source") == "vocab.md":
            fields["source_collection"] = "Édito B1"
            if fields.get("example"):
                fields["source_context"] = fields["example"]
        target = target_for(note, ref)
        result.append({"note": note, "fields": fields, "target": target})
    return result


def validate(changes: list[dict[str, Any]]) -> list[str]:
    errors = []
    seen: dict[str, str] = {}
    for change in changes:
        fields = change["fields"]
        key = normalise_key(fields.get("front", ""))
        note_id = change["note"]["note_id"]
        if not key:
            errors.append(f"{note_id}: empty front")
        elif key in seen and seen[key] != note_id:
            errors.append(f"duplicate normalized front {key!r}: {seen[key]}, {note_id}")
        else:
            seen[key] = note_id
    return errors


def apply(changes: list[dict[str, Any]]) -> None:
    # The service recomputes source_key correctly and keeps note_id-linked FSRS state.
    for change in changes:
        note = change["note"]
        updated = flashcard_service.update_note(
            USER_ID, note["note_id"], change["fields"],
            note_type=note["note_type"], deck_path=change["target"],
        )
        if updated is None:
            raise RuntimeError(f"note disappeared during update: {note['note_id']}")

    # Remove only the old empty containers/leaves after all notes have moved.
    # Repeat bottom-up because the old B1/B2.1 parents contain now-empty leaves.
    with get_db_session() as session:
        for _ in range(10):
            deleted = session.execute(text("""
              WITH RECURSIVE old AS (
                SELECT d.deck_id
                FROM flashcard_deck d
                JOIN flashcard_deck root ON root.deck_id=d.parent_deck_id
                WHERE d.user_id=:u AND root.name='French'
                  AND d.name IN ('B1','B2.1','Actualités')
                UNION ALL
                SELECT child.deck_id
                FROM flashcard_deck child JOIN old ON child.parent_deck_id=old.deck_id
              )
              DELETE FROM flashcard_deck d
              WHERE d.deck_id IN (SELECT deck_id FROM old)
                AND NOT EXISTS (SELECT 1 FROM flashcard_note n WHERE n.deck_id=d.deck_id)
                AND NOT EXISTS (SELECT 1 FROM flashcard_deck c WHERE c.parent_deck_id=d.deck_id)
            """), {"u": USER_ID}).rowcount
            if not deleted:
                break


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="publish changes; default is dry-run")
    args = ap.parse_args()
    notes = load_notes()
    changes = plan(notes)
    errors = validate(changes)
    print("Current notes:", len(notes))
    print("Target decks:")
    for deck, count in sorted(Counter(c["target"] for c in changes).items()):
        print(f"  {count:3d}  {deck}")
    rewrites = [c for c in changes if c["note"]["fields"].get("front") != c["fields"].get("front")]
    print("Front normalizations:", len(rewrites))
    for c in rewrites:
        print(f"  {c['note']['fields']['front']} -> {c['fields']['front']}")
    print("Validation errors:", len(errors))
    for error in errors:
        print("  ERROR:", error)
    if errors:
        return 1
    if not args.apply:
        print("DRY RUN — no database changes")
        return 0
    apply(changes)
    print("APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
