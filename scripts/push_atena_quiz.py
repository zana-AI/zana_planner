#!/usr/bin/env python3
"""Push (or dry-run validate) a generated MCQ deck into the challenges engine.

Used by the `atena-daily-french-quiz` scheduled task. Reads a deck JSON payload
(title, source_ref, items) from stdin or --file, validates it, and either just
reports the result (--dry-run, default) or writes it via ChallengesRepository
(--publish).

Run inside the zana-prod/zana-staging container, where PYTHONPATH includes
/app and /app/tm_bot (see Dockerfile):

    docker exec -i zana-prod python3 scripts/push_atena_quiz.py --dry-run < deck.json
    docker exec -i zana-prod python3 scripts/push_atena_quiz.py --publish < deck.json

Expected input JSON shape:
{
  "title": "Day N — <theme>",
  "source_ref": "<stable id for the source post/image, e.g. its CDN URL or t.me permalink>",
  "items": [
    {"front": "...", "back": "<correct answer, must equal one option>",
     "options": ["...", "...", "...", "..."], "example": null},
    ... exactly 10 items ...
  ]
}
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

DEFAULT_CHALLENGE_ID = "660762b526d849ffa4470a9e690fc2d3"  # "French with Atena 🇫🇷"
EXPECTED_ITEM_COUNT = 10
LETTERS = "abcd"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate(deck: dict) -> list[str]:
    """Return a list of error strings; empty list means the deck is publishable."""
    errors = []
    title = deck.get("title")
    if not title or not isinstance(title, str):
        errors.append("missing/invalid 'title'")
    if not deck.get("source_ref"):
        errors.append("missing 'source_ref' (needed for dedup)")

    items = deck.get("items")
    if not isinstance(items, list):
        errors.append("'items' must be a list")
        return errors
    if len(items) != EXPECTED_ITEM_COUNT:
        errors.append(f"expected {EXPECTED_ITEM_COUNT} items, got {len(items)}")

    for i, item in enumerate(items, start=1):
        front, back, options = item.get("front"), item.get("back"), item.get("options")
        if not front:
            errors.append(f"item {i}: missing 'front'")
        if not back:
            errors.append(f"item {i}: missing 'back'")
        if not isinstance(options, list) or len(options) != 4:
            errors.append(f"item {i}: 'options' must have exactly 4 entries")
            continue
        if len(set(options)) != 4:
            errors.append(f"item {i}: duplicate options")
        if back not in options:
            errors.append(f"item {i}: 'back' ({back!r}) is not among 'options'")

    return errors


def answer_letter_distribution(items: list[dict]) -> Counter:
    dist = Counter()
    for item in items:
        options = item.get("options") or []
        back = item.get("back")
        if back in options:
            dist[LETTERS[options.index(back)]] += 1
    return dist


def compute_next_release_at(latest_release_at: str | None) -> str:
    """One day after the queue tail, but never in the past (skips forward to the next
    future day if the queue has been dry — e.g. after a multi-day gap)."""
    now = datetime.now(timezone.utc)
    if not latest_release_at:
        candidate = now + timedelta(days=1)
    else:
        candidate = _parse_iso(latest_release_at) + timedelta(days=1)
        while candidate <= now:
            candidate += timedelta(days=1)
    return candidate.isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", help="Path to deck JSON (default: stdin)")
    parser.add_argument("--challenge-id", default=DEFAULT_CHALLENGE_ID)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                       help="Validate + report only, no DB write (default)")
    mode.add_argument("--publish", action="store_true", help="Write the deck to the DB")
    args = parser.parse_args()
    publish = args.publish

    raw = open(args.file, encoding="utf-8").read() if args.file else sys.stdin.read()
    try:
        deck = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"PUSH_STATUS=ERROR invalid JSON: {exc}")
        return 2

    errors = validate(deck)

    from repositories.challenges_repo import ChallengesRepository  # noqa: E402 (deferred import)
    repo = ChallengesRepository()

    existing_refs = set(repo.get_source_refs(args.challenge_id))
    source_ref = deck.get("source_ref")
    is_dup = source_ref in existing_refs
    if is_dup:
        errors.append(f"source_ref {source_ref!r} already used for this challenge")

    latest_release_at = repo.get_latest_release_at(args.challenge_id)
    next_release_at = compute_next_release_at(latest_release_at)

    items = deck.get("items") or []
    dist = answer_letter_distribution(items)

    print(f"title: {deck.get('title')}")
    print(f"source_ref: {source_ref}")
    print(f"item_count: {len(items)}")
    print(f"answer_letter_distribution: {dict(sorted(dist.items()))}")
    print(f"latest_existing_release_at: {latest_release_at}")
    print(f"computed_release_at: {next_release_at}")

    if errors:
        print("VALIDATION_ERRORS:")
        for e in errors:
            print(f"  - {e}")
        print("PUSH_STATUS=REJECTED")
        return 1

    if not publish:
        print("PUSH_STATUS=DRY_RUN_OK (no DB write — pass --publish to push)")
        return 0

    result = repo.add_deck(
        args.challenge_id,
        deck["title"],
        items,
        position=repo.get_deck_count(args.challenge_id),  # append after existing decks
        release_at=next_release_at,
        source_ref=source_ref,
    )
    print(f"deck_id: {result['deck_id']}")
    print("PUSH_STATUS=PUBLISHED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
