#!/usr/bin/env python3
"""Push (or dry-run validate) flashcard decks into the challenges engine.

Used for the "Entretien de naturalisation française" challenge (flashcard
activity_type, self-paced — unlike the Atena MCQ challenge's daily drip).
Reads a JSON array of decks (title, source_ref, items) from stdin or --file,
validates each, and either just reports the result (--dry-run, default) or
writes them via ChallengesRepository (--publish). All decks are released
immediately (release_at = now), a few seconds apart to keep a stable order.

Run inside the zana-prod/zana-staging container, where PYTHONPATH includes
/app and /app/tm_bot (see Dockerfile):

    docker exec -i zana-prod python3 scripts/push_naturalisation_quiz.py \
        --challenge-id <id> --dry-run < decks.json
    docker exec -i zana-prod python3 scripts/push_naturalisation_quiz.py \
        --challenge-id <id> --publish < decks.json

Expected input JSON shape (a list of decks):
[
  {
    "title": "<theme>",
    "source_ref": "<stable id for the source content, e.g. youtube:<id>#axe=1>",
    "items": [
      {"front": "...", "back": "..."},
      ...
    ]
  },
  ...
]

Unlike push_atena_quiz.py, items here are flashcards: no 'options', no fixed
item count per deck, and 'back' is the answer shown after reveal rather than
a value that must appear in a 4-choice list.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def validate(decks: list) -> list[str]:
    """Return a list of error strings; empty list means the decks are publishable."""
    errors = []
    if not isinstance(decks, list) or not decks:
        return ["input must be a non-empty JSON array of decks"]

    seen_source_refs = set()
    for d, deck in enumerate(decks, start=1):
        title = deck.get("title")
        if not title or not isinstance(title, str):
            errors.append(f"deck {d}: missing/invalid 'title'")

        source_ref = deck.get("source_ref")
        if not source_ref:
            errors.append(f"deck {d}: missing 'source_ref' (needed for dedup)")
        elif source_ref in seen_source_refs:
            errors.append(f"deck {d}: duplicate source_ref {source_ref!r} within this input")
        else:
            seen_source_refs.add(source_ref)

        items = deck.get("items")
        if not isinstance(items, list) or not items:
            errors.append(f"deck {d} ({title!r}): 'items' must be a non-empty list")
            continue

        for i, item in enumerate(items, start=1):
            front, back = item.get("front"), item.get("back")
            if not front or not isinstance(front, str):
                errors.append(f"deck {d} item {i}: missing/invalid 'front'")
            if not back or not isinstance(back, str):
                errors.append(f"deck {d} item {i}: missing/invalid 'back'")
            if item.get("options"):
                errors.append(f"deck {d} item {i}: flashcard items must not have 'options'")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", help="Path to decks JSON (default: stdin)")
    parser.add_argument("--challenge-id", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                       help="Validate + report only, no DB write (default)")
    mode.add_argument("--publish", action="store_true", help="Write the decks to the DB")
    args = parser.parse_args()
    publish = args.publish

    raw = open(args.file, encoding="utf-8").read() if args.file else sys.stdin.read()
    try:
        decks = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"PUSH_STATUS=ERROR invalid JSON: {exc}")
        return 2

    errors = validate(decks)

    from repositories.challenges_repo import ChallengesRepository  # noqa: E402 (deferred import)
    repo = ChallengesRepository()

    existing_refs = set(repo.get_source_refs(args.challenge_id))
    for d, deck in enumerate(decks, start=1):
        source_ref = deck.get("source_ref")
        if source_ref in existing_refs:
            errors.append(f"deck {d}: source_ref {source_ref!r} already used for this challenge")

    total_items = sum(len(deck.get("items") or []) for deck in decks)
    print(f"deck_count: {len(decks)}")
    print(f"total_item_count: {total_items}")
    for d, deck in enumerate(decks, start=1):
        print(f"  deck {d}: {deck.get('title')!r} — {len(deck.get('items') or [])} items "
              f"(source_ref={deck.get('source_ref')})")

    if errors:
        print("VALIDATION_ERRORS:")
        for e in errors:
            print(f"  - {e}")
        print("PUSH_STATUS=REJECTED")
        return 1

    if not publish:
        print("PUSH_STATUS=DRY_RUN_OK (no DB write — pass --publish to push)")
        return 0

    base_position = repo.get_deck_count(args.challenge_id)
    now = datetime.now(timezone.utc)
    for d, deck in enumerate(decks):
        # Stagger release_at by a second per deck so ordering is stable and
        # deterministic, while every deck is playable immediately (self-paced).
        release_at = (now + timedelta(seconds=d)).isoformat().replace("+00:00", "Z")
        result = repo.add_deck(
            args.challenge_id,
            deck["title"],
            deck["items"],
            position=base_position + d,
            release_at=release_at,
            source_ref=deck.get("source_ref"),
        )
        print(f"deck_id: {result['deck_id']} ({deck['title']!r})")

    print("PUSH_STATUS=PUBLISHED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
