#!/usr/bin/env python3
"""Enrich Language Reactor flashcards with a video timestamp and a clean sentence.

Language Reactor gave us `source_url` + `source_context` (a raw caption window)
but no timestamp, so a card cannot deep-link into the moment it came from. This
locates each context inside the fetched transcript and writes back:

    source_start    float seconds - where the word is spoken
    source_sentence clean sentence built from surrounding cues
    source_context  left untouched (Language Reactor's original window)

Transcripts are fetched separately (scripts/fetch_transcripts.py) because
YouTube blocks the datacenter IP - this must run from a residential connection.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

USER_ID = "108648163"
HOST = "root@169.58.186.195"
TRANSCRIPT_DIR = Path(__file__).resolve().parent.parent / "exports" / "transcripts"

# A cue window that still reads as speech: enough context to show the word in
# use, short enough to fit on a flashcard.
SENTENCE_MAX_CHARS = 220


def run_sql(sql: str) -> list[list[str]]:
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", HOST, "docker", "exec", "-i",
         "zana-postgres", "psql", "-U", "zana", "-d", "zana", "-At",
         "-F", "\x1f", "-P", "footer=off"],
        input=sql, text=True, capture_output=True, encoding="utf-8", check=True)
    return [line.split("\x1f") for line in proc.stdout.strip().splitlines() if line]


def normalise(text: str) -> str:
    """Fold to comparable form: no accents, no punctuation, single spaces."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def load_transcript(video_id: str) -> list[dict]:
    path = TRANSCRIPT_DIR / f"{video_id}.json"
    if not path.exists():
        raise SystemExit(f"missing transcript {path} - run fetch_transcripts.py first")
    return json.loads(path.read_text(encoding="utf-8"))["segments"]


def locate(context: str, segments: list[dict]) -> tuple[int, float]:
    """Return (segment index, match ratio) for the cue that starts the context."""
    target = normalise(context)
    if not target:
        return -1, 0.0
    best_idx, best_ratio = -1, 0.0
    # The context spans several cues, so score each cue as the possible start of
    # a window of the same length and keep the best alignment.
    for i in range(len(segments)):
        window = normalise(" ".join(s["text"] for s in segments[i:i + 6]))[:len(target) + 40]
        if not window:
            continue
        ratio = SequenceMatcher(None, target, window).ratio()
        if ratio > best_ratio:
            best_idx, best_ratio = i, ratio
    return best_idx, best_ratio


def build_sentence(segments: list[dict], idx: int, word: str) -> str:
    """Grow a readable sentence outward from the matched cue."""
    text = " ".join(s["text"] for s in segments[max(0, idx - 1):idx + 5])
    text = re.sub(r"\[[^\]]*\]", " ", text)          # [musique], [rires]
    text = re.sub(r"\s+", " ", text).strip()
    # Prefer the sentence that actually contains the word.
    parts = re.split(r"(?<=[.!?])\s+", text)
    stem = normalise(word).split(" ")[-1][:6]
    hit = next((p for p in parts if stem and stem in normalise(p)), None)
    sentence = hit or text
    if len(sentence) > SENTENCE_MAX_CHARS:
        sentence = sentence[:SENTENCE_MAX_CHARS].rsplit(" ", 1)[0] + "…"
    return sentence.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write to the database")
    ap.add_argument("--min-ratio", type=float, default=0.55,
                    help="skip cards whose context does not match this well")
    args = ap.parse_args()

    rows = run_sql(
        "SELECT note_id, fields->>'front', fields->>'source_url', "
        "fields->>'source_context' FROM flashcard_note "
        f"WHERE user_id='{USER_ID}' AND source='language-reactor' "
        "ORDER BY fields->>'source_url', fields->>'front';")

    cache: dict[str, list[dict]] = {}
    updates, skipped = [], []
    for note_id, front, url, context in rows:
        video_id = url.rsplit("v=", 1)[-1]
        segments = cache.setdefault(video_id, load_transcript(video_id))
        idx, ratio = locate(context, segments)
        if idx < 0 or ratio < args.min_ratio:
            skipped.append((front, ratio))
            continue
        start = float(segments[idx]["start"])
        updates.append({
            "note_id": note_id, "front": front, "video_id": video_id,
            "start": start, "ratio": ratio,
            "sentence": build_sentence(segments, idx, front),
        })

    for u in sorted(updates, key=lambda u: (u["video_id"], u["start"])):
        m, s = divmod(int(u["start"]), 60)
        print(f'{u["front"][:22]:24} {m:02d}:{s:02d}  r={u["ratio"]:.2f}  {u["sentence"][:88]}')
    print(f"\nmatched {len(updates)}/{len(rows)}")
    for front, ratio in skipped:
        print(f"  SKIP {front} (best ratio {ratio:.2f})")

    if not args.apply:
        print("\ndry run - pass --apply to write")
        return

    backup = TRANSCRIPT_DIR.parent / "language_reactor_fields_backup.json"
    if not backup.exists():
        current = run_sql(
            "SELECT note_id, fields::text FROM flashcard_note "
            f"WHERE user_id='{USER_ID}' AND source='language-reactor';")
        backup.write_text(json.dumps({r[0]: r[1] for r in current}, ensure_ascii=False, indent=1),
                          encoding="utf-8")
        print(f"backed up original fields -> {backup}")

    statements = []
    for u in updates:
        patch = json.dumps({"source_start": round(u["start"], 2),
                            "source_sentence": u["sentence"]}, ensure_ascii=False)
        statements.append(
            "UPDATE flashcard_note SET fields = fields || "
            f"$patch${patch}$patch$::jsonb, updated_at = now() "
            f"WHERE note_id = '{u['note_id']}';")
    run_sql("BEGIN;\n" + "\n".join(statements) + "\nCOMMIT;")
    print(f"applied {len(statements)} updates")


if __name__ == "__main__":
    main()
