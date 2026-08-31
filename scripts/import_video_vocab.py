#!/usr/bin/env python3
"""Import a video vocabulary deck into the flashcard SRS engine.

Takes a manifest of videos and the words worth learning from each, and creates
one leaf deck per video with a card per word. Every card is aligned to the
moment its word is spoken, so it links into the player exactly like the
Language Reactor cards do.

Alignment is done here rather than by hand: the word is located in the cached
transcript (`video_transcript`, filled by scripts/fetch_transcripts.py), which
yields both the timestamp and the sentence as actually said. Authoring a card
therefore only means choosing the word and writing its definition.

Runs inside the app container, which has the database and the app on the path:

    scp cards.json root@169.58.186.195:/tmp/
    ssh root@169.58.186.195 "docker cp /tmp/cards.json zana-webapp:/tmp/ && \
        docker cp /tmp/import_video_vocab.py zana-webapp:/tmp/ && \
        docker exec zana-webapp python3 /tmp/import_video_vocab.py \
            --file /tmp/cards.json --user-id 108648163 --publish"

Import is idempotent: notes are keyed on (user_id, normalised front), so a
re-run updates a definition rather than duplicating a card or resetting its
scheduling.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

DECK_ROOT = "French::Vidéos"
SENTENCE_MAX_CHARS = 220


def fold(text: str) -> str:
    """Accent- and case-insensitive form, for matching French inflection."""
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def stem_of(front: str) -> str:
    """'une décennie' -> 'decenn': drop the article, trim for inflection."""
    stem = fold(front)
    stem = re.sub(r"^(un|une|le|la|les|des|du|de|d'|l')\s*", "", stem)
    stem = re.split(r"[\s(,/]", stem)[0]
    return stem[: max(4, len(stem) - 2)] if len(stem) > 4 else stem


def locate(front: str, cues: List[Dict[str, Any]]) -> Tuple[Optional[int], str]:
    """Find the cue where the word is spoken; return its index and a sentence."""
    stem = stem_of(front)
    if not stem:
        return None, ""
    for index, cue in enumerate(cues):
        if stem in fold(cue.get("text") or ""):
            return index, build_sentence(cues, index, stem)
    return None, ""


def build_sentence(cues: List[Dict[str, Any]], index: int, stem: str) -> str:
    """Grow a readable line outward from the matched cue.

    Captions break mid-sentence, so a single cue usually reads as a fragment.
    Joining a small window and then cutting on sentence punctuation gives a line
    that stands on its own on the back of a card.
    """
    window = " ".join(c.get("text") or "" for c in cues[max(0, index - 1): index + 4])
    window = re.sub(r"\[[^\]]*\]", " ", window)          # [musique], [rires]
    window = re.sub(r"\s+", " ", window).strip()
    parts = re.split(r"(?<=[.!?])\s+", window)
    sentence = next((p for p in parts if stem in fold(p)), window)
    if len(sentence) > SENTENCE_MAX_CHARS:
        sentence = sentence[:SENTENCE_MAX_CHARS].rsplit(" ", 1)[0] + "…"
    return sentence.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="JSON manifest of videos and words")
    ap.add_argument("--user-id", help="Telegram user id to import for")
    ap.add_argument("--publish", action="store_true", help="write to the database")
    args = ap.parse_args()

    manifest = json.load(open(args.file, encoding="utf-8"))
    videos = manifest["videos"]

    sys.path.insert(0, "/app/tm_bot")
    from repositories.video_transcript_repo import VideoTranscriptRepository  # noqa: E402

    transcripts = VideoTranscriptRepository()
    planned: List[Dict[str, Any]] = []
    unaligned: List[str] = []

    for video in videos:
        cached = transcripts.get(video["video_id"])
        if not cached or not cached.get("cues"):
            print(f'!! no transcript cached for {video["video_id"]} — skipping {video["title"]}')
            continue
        cues = cached["cues"]
        deck_path = f'{DECK_ROOT}::{video["title"]}'
        for word in video["words"]:
            index, sentence = locate(word["front"], cues)
            fields = {
                "front": word["front"],
                "back": word["back"],
                "source_url": f'https://www.youtube.com/watch?v={video["video_id"]}',
                "source_title": video["title"],
            }
            if index is None:
                # Still a usable card, it just cannot link into the video.
                unaligned.append(f'{video["title"]}: {word["front"]}')
            else:
                fields["source_start"] = round(float(cues[index]["start"]), 2)
                fields["source_sentence"] = sentence
            planned.append({"deck_path": deck_path, "fields": fields})

    for note in planned:
        at = note["fields"].get("source_start")
        stamp = f"{int(at) // 60}:{int(at) % 60:02d}" if at is not None else "  -  "
        print(f'{note["fields"]["front"][:26]:28} {stamp:6} {note["fields"].get("source_sentence", "")[:70]}')
    print(f"\n{len(planned)} cards across {len(videos)} videos; "
          f"{len(planned) - len(unaligned)} aligned to a moment")
    for miss in unaligned:
        print(f"  unaligned: {miss}")

    if not args.publish:
        print("\nDRY RUN — nothing written. Re-run with --publish --user-id <id>.")
        return 0
    if not args.user_id:
        print("\nERROR: --publish requires --user-id", file=sys.stderr)
        return 2

    from services import flashcard_service  # noqa: E402
    for note in planned:
        flashcard_service.create_note(
            str(args.user_id),
            deck_path=note["deck_path"],
            fields=note["fields"],
            note_type="vocab",
            source="video",
        )
    print(f"\nImported {len(planned)} notes for user {args.user_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
