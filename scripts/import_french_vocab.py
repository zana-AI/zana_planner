#!/usr/bin/env python3
"""Import a markdown vocabulary table into the flashcard SRS engine.

Reads the `vocab.md` produced from Zotero highlights (Edito B1) and turns each
row into a `flashcard_note` plus a card that is due immediately.

Parsing is deliberately kept free of any database import so it can be run and
tested anywhere:

    python3 scripts/import_french_vocab.py --file vocab.md --dry-run

Writing needs the app on PYTHONPATH, so run it inside a container where /app
and /app/tm_bot are importable (see Dockerfile):

    docker exec -i zana-webapp python3 scripts/import_french_vocab.py \
        --file /tmp/vocab.md --user-id 123456 --publish

The file has three different table shapes, so each is parsed by column header
rather than by position:

  | Mot / expression | Définition (fr) | Page | Ma note |   -> vocab, with page
  | Mot / expression | Définition (fr) | Ma note |          -> vocab, no page
  | Point | Règle | Exemples |                              -> grammar

A fourth section ("Notes libres") is *not* imported: those rows are Zotero
notes that point at a word already in the tables, so importing them would
create duplicate cards for the same word. They are reported instead.

Import is idempotent. `flashcard_note` is uniquely keyed on
(user_id, source_key) where source_key is the normalised front field, so
re-running updates the definition of an existing card and never duplicates it
or resets its scheduling.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

# Deck names, nested with '::' the way the deck repository splits them.
# The root is English because it surfaces as a label in the app's (English)
# chrome; the levels below it keep the source's own French names.
DECK_ROOT = "French::B1"

# Header cell -> canonical field name. Compared after lowercasing and
# stripping accents, so "Définition (fr)" and "Definition (FR)" both match.
_HEADER_ALIASES = {
    "mot / expression": "front",
    "mot": "front",
    "expression": "front",
    "point": "front",
    "definition (fr)": "back",
    "definition": "back",
    "regle": "back",
    "page": "source_page",
    "ma note": "note_fa",
    "note": "note_fa",
    "exemples": "example",
    "exemple": "example",
    "rapport": "relation",
}


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def _canonical_header(cell: str) -> Optional[str]:
    key = _strip_accents(cell.strip().lower())
    key = re.sub(r"\s+", " ", key).strip()
    return _HEADER_ALIASES.get(key)


def _split_row(line: str) -> List[str]:
    """Split a markdown table row into cells.

    Only splits on unescaped pipes, so a definition containing `\\|` survives.
    """
    parts = re.split(r"(?<!\\)\|", line.strip())
    # A well-formed row starts and ends with '|', producing empty edge cells.
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [p.replace(r"\|", "|").strip() for p in parts]


def _is_separator_row(cells: List[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c)


def parse(markdown: str) -> Dict[str, Any]:
    """Parse the vocab file into importable notes plus a report.

    Returns {"notes": [...], "skipped": [...], "sections": {...}}.
    """
    notes: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    sections: Dict[str, int] = {}

    section = ""          # current '##' heading
    subsection = ""       # current '###' heading
    headers: List[Optional[str]] = []
    in_free_notes = False

    for raw in markdown.splitlines():
        line = raw.rstrip()

        if line.startswith("## "):
            section = line[3:].strip()
            subsection = ""
            headers = []
            in_free_notes = _strip_accents(section.lower()).startswith("notes libres")
            continue
        if line.startswith("### "):
            subsection = line[4:].strip()
            headers = []
            continue

        if not line.startswith("|"):
            continue

        cells = _split_row(line)
        if not cells:
            continue
        if _is_separator_row(cells):
            continue

        mapped = [_canonical_header(c) for c in cells]
        # A row where every cell is a known header starts a new table. The
        # free-notes table has no "front" column, but must still be recognised
        # so its rows get reported rather than silently dropped.
        if all(m is not None for m in mapped) and ("front" in mapped or in_free_notes):
            headers = mapped
            continue

        if not headers:
            continue

        row: Dict[str, str] = {}
        for name, value in zip(headers, cells):
            if name and value:
                row[name] = value

        # The free-notes table's first column is the note itself, not a front.
        front = (row.get("front") or (row.get("note_fa", "") if in_free_notes else "")).strip()
        if not front:
            continue

        deck_path, note_type = _classify(section, subsection)

        if in_free_notes:
            # Rows in "Notes libres" have no definition column, so there is
            # nothing to put on the back of a card. Some duplicate a word that
            # is already in the tables; others are genuinely new vocabulary or
            # just a topic reminder. Deciding which is a judgement call, so
            # report them all and import none.
            skipped.append({
                "front": front,
                "reason": "free-form Zotero note (no definition column)",
                "detail": row.get("relation") or row.get("source_page") or "",
            })
            continue

        back = row.get("back", "").strip()
        if not back:
            skipped.append({"front": front, "reason": "no definition", "detail": ""})
            continue

        fields: Dict[str, Any] = {"front": front, "back": back}
        if row.get("note_fa"):
            fields["note_fa"] = row["note_fa"]
        if row.get("example"):
            fields["example"] = row["example"]
        if row.get("source_page"):
            fields["source_page"] = row["source_page"]

        notes.append({
            "deck_path": deck_path,
            "note_type": note_type,
            "fields": fields,
        })
        sections[deck_path] = sections.get(deck_path, 0) + 1

    return {"notes": notes, "skipped": skipped, "sections": sections}


def _classify(section: str, subsection: str) -> tuple[str, str]:
    """Map a heading pair onto (deck_path, note_type)."""
    sub = _strip_accents(subsection.lower())
    sec = _strip_accents(section.lower())

    if "grammaire" in sub or "grammaire" in sec:
        return f"{DECK_ROOT}::Grammaire", "grammar"
    if "unite" in sec:
        match = re.search(r"unite\s*(\d+)", sec)
        label = f"Unité {match.group(1)}" if match else "Unité"
        return f"{DECK_ROOT}::{label}", "vocab"
    if "livre" in sec or "edito" in sec:
        return f"{DECK_ROOT}::Édito B1 Livre", "vocab"
    return DECK_ROOT, "vocab"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", required=True, help="path to vocab.md")
    ap.add_argument("--user-id", help="Telegram user id to own the notes (required with --publish)")
    ap.add_argument("--dry-run", action="store_true",
                    help="parse and report without writing (the default)")
    ap.add_argument("--publish", action="store_true", help="write to the database")
    ap.add_argument("--json", action="store_true", help="emit parsed notes as JSON")
    args = ap.parse_args()

    text = Path(args.file).read_text(encoding="utf-8")
    result = parse(text)
    notes, skipped = result["notes"], result["skipped"]

    if args.json:
        print(json.dumps(notes, ensure_ascii=False, indent=2))
        return 0

    print(f"Parsed {len(notes)} notes from {args.file}")
    for deck, count in sorted(result["sections"].items()):
        print(f"  {count:4d}  {deck}")

    types: Dict[str, int] = {}
    with_page = with_fa = with_example = 0
    for note in notes:
        types[note["note_type"]] = types.get(note["note_type"], 0) + 1
        with_page += "source_page" in note["fields"]
        with_fa += "note_fa" in note["fields"]
        with_example += "example" in note["fields"]
    print(f"\n  types: {types}")
    print(f"  with page ref: {with_page}   with personal note: {with_fa}   with examples: {with_example}")

    if skipped:
        print(f"\nNot imported ({len(skipped)}):")
        for item in skipped:
            detail = f" — {item['detail']}" if item["detail"] else ""
            print(f"  · {item['front']}: {item['reason']}{detail}")

    if not args.publish:
        print("\nDRY RUN — nothing written. Re-run with --publish --user-id <id> to import.")
        return 0

    if not args.user_id:
        print("\nERROR: --publish requires --user-id", file=sys.stderr)
        return 2

    # Deferred so that parsing/dry-run needs no database or app imports.
    sys.path.insert(0, "/app/tm_bot")
    from services import flashcard_service  # noqa: E402

    created = 0
    for note in notes:
        flashcard_service.create_note(
            str(args.user_id),
            deck_path=note["deck_path"],
            fields=note["fields"],
            note_type=note["note_type"],
            source="vocab.md",
        )
        created += 1
    print(f"\nImported {created} notes for user {args.user_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
