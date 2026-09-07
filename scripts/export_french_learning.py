#!/usr/bin/env python3
"""Export personal French flashcards and Atena quiz content to editable CSVs."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

USER_ID = "108648163"
FRENCH_CHALLENGE_IDS = (
    "660762b526d849ffa4470a9e690fc2d3",  # French with Atena
    "8780918c227541c089498430da290c8d",  # French Naturalization Prep
)
HOST = "root@169.58.186.195"


def run_sql(sql: str):
    p = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", HOST, "docker", "exec", "-i",
         "zana-postgres", "psql", "-U", "zana", "-d", "zana", "-At",
         "-P", "footer=off"], input=sql, text=True, capture_output=True,
        encoding="utf-8", check=True)
    return json.loads(p.stdout or "null")


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("exports/french_learning"))
    out = ap.parse_args().out
    out.mkdir(parents=True, exist_ok=True)

    cte = f"""
      WITH RECURSIVE tree AS (
        SELECT deck_id, user_id, name, parent_deck_id, created_at, promise_id,
               name::text AS deck_path
        FROM flashcard_deck
        WHERE user_id='{USER_ID}' AND parent_deck_id IS NULL
        UNION ALL
        SELECT d.deck_id, d.user_id, d.name, d.parent_deck_id, d.created_at,
               d.promise_id, tree.deck_path || '::' || d.name
        FROM flashcard_deck d JOIN tree ON d.parent_deck_id=tree.deck_id
        WHERE d.user_id='{USER_ID}'
      )
    """
    decks = run_sql(cte + "SELECT COALESCE(json_agg(x ORDER BY deck_path), '[]'::json) FROM (SELECT * FROM tree) x;") or []
    notes = run_sql(cte + f"""
      SELECT COALESCE(json_agg(x ORDER BY deck_path, source_key), '[]'::json)
      FROM (
        SELECT n.note_id, n.user_id, n.deck_id, d.deck_path, n.note_type,
               n.fields, n.source_key, n.source, n.created_at, n.updated_at,
               COALESCE((SELECT json_agg(to_jsonb(r)-'note_id' ORDER BY r.created_at)
                         FROM flashcard_note_reference r WHERE r.note_id=n.note_id), '[]'::json) AS references
        FROM flashcard_note n JOIN tree d ON d.deck_id=n.deck_id
        WHERE n.user_id='{USER_ID}'
      ) x;
    """) or []
    challenge_ids = ",".join(f"'{x}'" for x in FRENCH_CHALLENGE_IDS)
    quizzes = run_sql(f"""
      SELECT json_build_object(
        'challenges', (SELECT COALESCE(json_agg(row_to_json(c) ORDER BY c.title), '[]'::json)
                       FROM challenges c WHERE c.challenge_id IN ({challenge_ids})),
        'decks', (SELECT COALESCE(json_agg(json_build_object(
                    'challenge_title', c.title, 'challenge_id', d.challenge_id,
                    'deck_id', d.deck_id, 'title', d.title, 'position', d.position,
                    'release_at', d.release_at, 'created_at_utc', d.created_at_utc,
                    'source_ref', d.source_ref) ORDER BY c.title, d.position), '[]'::json)
                  FROM challenge_decks d JOIN challenges c ON c.challenge_id=d.challenge_id
                  WHERE d.challenge_id IN ({challenge_ids})),
        'items', (SELECT COALESCE(json_agg(json_build_object(
                    'challenge_title', c.title, 'challenge_id', d.challenge_id,
                    'deck_id', i.deck_id, 'item_id', i.item_id, 'position', i.position,
                    'front', i.front, 'back', i.back, 'example', i.example,
                    'media_url', i.media_url, 'options', i.options,
                    'created_at_utc', i.created_at_utc) ORDER BY c.title, d.position, i.position), '[]'::json)
                  FROM challenge_items i JOIN challenge_decks d ON d.deck_id=i.deck_id
                  JOIN challenges c ON c.challenge_id=d.challenge_id
                  WHERE d.challenge_id IN ({challenge_ids}))
      );
    """) or {}

    note_rows = []
    for n in notes:
        fields = n.pop("fields") or {}
        n["references_json"] = json.dumps(n.pop("references") or [], ensure_ascii=False, separators=(",", ":"))
        n["fields_json"] = json.dumps(fields, ensure_ascii=False, separators=(",", ":"))
        for key in ("front", "back", "example", "note_fa", "source_page", "lingoda_status"):
            n[key] = fields.get(key, "")
        note_rows.append(n)

    quiz_items = quizzes.get("items", [])
    for item in quiz_items:
        item["options_json"] = json.dumps(item.get("options") or [], ensure_ascii=False, separators=(",", ":"))

    write_csv(out / "flashcard_decks.csv", decks, ["deck_id", "user_id", "name", "parent_deck_id", "deck_path", "created_at", "promise_id"])
    write_csv(out / "flashcards.csv", note_rows, ["note_id", "user_id", "deck_id", "deck_path", "note_type", "front", "back", "example", "note_fa", "source_page", "lingoda_status", "fields_json", "source_key", "source", "created_at", "updated_at", "references_json"])
    write_csv(out / "french_quiz_decks.csv", quizzes.get("decks", []), ["challenge_title", "challenge_id", "deck_id", "title", "position", "release_at", "created_at_utc", "source_ref"])
    write_csv(out / "french_quiz_items.csv", quiz_items, ["challenge_title", "challenge_id", "deck_id", "item_id", "position", "front", "back", "example", "media_url", "options_json", "created_at_utc"])
    (out / "README.txt").write_text(
        "French learning content export\n"
        f"Generated: {datetime.now(timezone.utc).isoformat()}\n\n"
        "flashcards.csv contains authored cards. Edit front/back/example/note_fa and keep note_id.\n"
        "flashcard_decks.csv contains the deck tree.\n"
        "french_quiz_decks.csv contains Atena and French Naturalization deck metadata.\n"
        "french_quiz_items.csv contains both French quiz collections; options_json is a JSON array.\n"
        "Scheduling/review history and quiz attempts are intentionally excluded.\n",
        encoding="utf-8")
    print(f"Exported {len(note_rows)} flashcards and {len(quiz_items)} French quiz items to {out}")


if __name__ == "__main__":
    main()
