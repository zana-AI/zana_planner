#!/usr/bin/env python3
"""Import a Lingoda "Your vocabulary" PDF export into the flashcard engine.

Lingoda's vocabulary page prints as a three-column table (French | English |
Status). Extracting that PDF as plain text flattens the columns onto one line,
so `l'intelligence artificielle artificial intelligence Known` has no reliable
French/English boundary — splitting on whitespace guesses wrong on every
multi-word term.

The French column *does* carry usable text coordinates, though, while the
English and Status cells collapse to (0,0) because they sit inside nested form
objects. So the French terms are read positionally and then used as prefixes to
split the flat lines. That is exact rather than heuristic: a line is only
accepted if it starts with a known French term and ends with a known status.

    python3 scripts/import_lingoda_vocab.py --file a.pdf --file b.pdf --dry-run
    docker exec -i zana-webapp python3 scripts/import_lingoda_vocab.py \
        --file /tmp/a.pdf --user-id 123456 --publish

These cards are French -> English, unlike the monolingual French definitions in
vocab.md, so they default to their own deck. Mixing the two in one deck would
mean the same prompt sometimes wants a French definition and sometimes an
English gloss.

Import is idempotent: notes are keyed on (user_id, normalised front), so
re-running updates a card rather than duplicating it or resetting its schedule.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_DECK = "French::B2.1::Lingoda"

_STATUSES = ("Known", "New", "Reviewing")

# The French column's left edge, in text-space units. Everything else in the
# table extracts without usable coordinates.
_FR_COL_MIN, _FR_COL_MAX = 40.0, 60.0


def _french_terms(page) -> List[str]:
    """French column entries for one page, top to bottom."""
    found: List[Tuple[float, str]] = []

    def visit(text, cm, tm, font, size):
        value = (text or "").strip()
        if value and _FR_COL_MIN < tm[4] < _FR_COL_MAX:
            found.append((tm[5], value))

    page.extract_text(visitor_text=visit)
    found.sort(key=lambda item: -item[0])
    # 'French' is the column header, not a word.
    return [t for _, t in found if t.lower() != "french"]


def _level(text: str) -> Optional[str]:
    match = re.search(r"\b([ABC][12](?:\.\d)?)\b", text)
    return match.group(1) if match else None


def parse_pdf(path: Path) -> Dict[str, Any]:
    """Extract {front, back, status} rows from one Lingoda export."""
    import pypdf  # deferred: parsing is optional tooling, not a runtime dep

    reader = pypdf.PdfReader(str(path))
    terms: List[str] = []
    lines: List[str] = []
    full_text: List[str] = []

    for page in reader.pages:
        terms += _french_terms(page)
        text = page.extract_text() or ""
        full_text.append(text)
        lines += [ln.strip() for ln in text.splitlines() if ln.strip()]

    # Longest first so "le blogueur, la blogueuse" wins over a shorter prefix.
    terms_by_length = sorted(set(terms), key=len, reverse=True)

    rows: List[Dict[str, str]] = []
    unmatched: List[str] = []
    seen: set = set()

    for line in lines:
        status = next((s for s in _STATUSES if line.endswith(s)), None)
        if status is None:
            continue
        body = line[: -len(status)].strip()
        if not body:
            # The page's stats header prints "Reviewing" / "Known" alone.
            continue
        french = next((t for t in terms_by_length if body.startswith(t)), None)
        if french is None:
            unmatched.append(line)
            continue
        english = body[len(french):].strip()
        if not english or french in seen:
            continue
        seen.add(french)
        rows.append({"front": french, "back": english, "status": status})

    # Any French term that never produced a row is a silent loss — report it.
    missing = [t for t in dict.fromkeys(terms) if t not in seen]

    return {
        "rows": rows,
        "unmatched": unmatched,
        "missing": missing,
        "level": _level("\n".join(full_text)),
        "declared_total": _declared_total("\n".join(full_text)),
    }


def _declared_total(text: str) -> Optional[int]:
    """Lingoda prints 'Showing 1-20 of 38 words' — a checksum for the parse."""
    match = re.search(r"Showing\s+[\d]+-[\d]+\s+of\s+(\d+)\s+words", text)
    return int(match.group(1)) if match else None


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--file", action="append", default=[],
                    help="Lingoda PDF export (repeat for several)")
    # Parsing needs pypdf, which is deliberately not in the runtime image. So
    # parse where pypdf lives (--json), then publish from that inside the
    # container (--from-json) without shipping a PDF library to production.
    ap.add_argument("--from-json",
                    help="publish rows previously produced by --json")
    ap.add_argument("--deck", default=None,
                    help=f"deck path (default: {DEFAULT_DECK}, level auto-detected)")
    ap.add_argument("--user-id", help="Telegram user id (required with --publish)")
    ap.add_argument("--dry-run", action="store_true", help="parse only (the default)")
    ap.add_argument("--publish", action="store_true", help="write to the database")
    ap.add_argument("--json", action="store_true", help="emit parsed rows as JSON")
    args = ap.parse_args()

    if not args.file and not args.from_json:
        ap.error("need --file (to parse a PDF) or --from-json (to publish)")

    merged: Dict[str, Dict[str, str]] = {}
    declared: Optional[int] = None
    level: Optional[str] = None
    problems: List[str] = []

    if args.from_json:
        rows_in = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        for row in rows_in:
            merged[row["front"]] = row
            level = level or row.get("level")

    for name in args.file:
        path = Path(name)
        result = parse_pdf(path)
        declared = declared or result["declared_total"]
        level = level or result["level"]
        # Progress goes to stderr so --json output stays pipeable.
        print(f"{path.name}: {len(result['rows'])} words"
              + (f", level {result['level']}" if result["level"] else ""),
              file=sys.stderr)
        for row in result["rows"]:
            # Same word in two exports: keep the first, they carry equal content.
            merged.setdefault(row["front"], row)
        for line in result["unmatched"]:
            problems.append(f"{path.name}: could not split {line!r}")
        for term in result["missing"]:
            problems.append(f"{path.name}: no English found for {term!r}")

    deck = args.deck or (
        f"French::{level}::Lingoda" if level else DEFAULT_DECK
    )
    rows = list(merged.values())

    if args.json:
        # Carry the level through so --from-json picks the same deck.
        for row in rows:
            row.setdefault("level", level)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print(f"\n{len(rows)} unique words -> {deck}")
    known = sum(1 for r in rows if r["status"] == "Known")
    print(f"  Lingoda status: {known} Known, {len(rows) - known} New")

    if declared is not None:
        mark = "OK" if declared == len(rows) else "MISMATCH"
        print(f"  checksum: Lingoda says {declared} words, parsed {len(rows)} [{mark}]")
        if declared != len(rows):
            problems.append(
                f"expected {declared} words but parsed {len(rows)} — "
                "an export page may be missing"
            )

    if problems:
        print("\nProblems:")
        for p in problems:
            print(f"  · {p}")

    if not args.publish:
        print("\nDRY RUN — nothing written. Add --publish --user-id <id> to import.")
        return 0

    if not args.user_id:
        print("\nERROR: --publish requires --user-id", file=sys.stderr)
        return 2
    if problems:
        print("\nRefusing to publish while the parse has problems.", file=sys.stderr)
        return 3

    sys.path.insert(0, "/app/tm_bot")
    from services import flashcard_service  # noqa: E402

    for row in rows:
        fields: Dict[str, Any] = {"front": row["front"], "back": row["back"]}
        # Lingoda's own assessment, kept for reference. It deliberately does not
        # seed FSRS state: "Known" there is not a review history here.
        fields["lingoda_status"] = row["status"]
        flashcard_service.create_note(
            str(args.user_id),
            deck_path=deck,
            fields=fields,
            note_type="vocab",
            source="lingoda",
        )
    print(f"\nImported {len(rows)} notes for user {args.user_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
