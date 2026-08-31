#!/usr/bin/env python3
"""Fetch YouTube transcripts to exports/transcripts/<video_id>.json.

MUST RUN FROM A RESIDENTIAL CONNECTION. YouTube blocks the Contabo VM outright
("Sign in to confirm you're not a bot" / RequestBlocked), so the production
server cannot do this - transcripts are fetched here and the results are pushed
to the database by the scripts that consume them.

    python scripts/fetch_transcripts.py https://www.youtube.com/watch?v=ID ...
    python scripts/fetch_transcripts.py --from-cards      # every video our cards cite

Costs ~1.5 MB of traffic per video, almost all of it the watch page.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi

USER_ID = "108648163"
HOST = "root@169.58.186.195"
OUT_DIR = Path(__file__).resolve().parent.parent / "exports" / "transcripts"
LANGUAGES = ["fr", "en"]


def extract_video_id(url: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([\w-]{6,20})", url)
    if not match:
        raise ValueError(f"no video id in {url!r}")
    return match.group(1)


def video_ids_from_cards() -> list[str]:
    """Every distinct video cited by a flashcard, so ingest follows the content."""
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", HOST, "docker", "exec", "-i",
         "zana-postgres", "psql", "-U", "zana", "-d", "zana", "-At", "-P", "footer=off"],
        input="SELECT DISTINCT fields->>'source_url' FROM flashcard_note "
              f"WHERE user_id='{USER_ID}' AND fields ? 'source_url';",
        text=True, capture_output=True, encoding="utf-8", check=True)
    return [extract_video_id(u) for u in proc.stdout.split() if u.strip()]


def fetch(video_id: str, force: bool = False) -> bool:
    out = OUT_DIR / f"{video_id}.json"
    if out.exists() and not force:
        print(f"{video_id}: cached")
        return True
    try:
        transcript = YouTubeTranscriptApi().fetch(video_id, languages=LANGUAGES)
    except Exception as exc:                       # noqa: BLE001 - report and continue
        name = type(exc).__name__
        hint = "  <- run this from a home connection, not a server" if "Blocked" in name else ""
        print(f"{video_id}: FAILED {name}{hint}")
        return False
    segments = transcript.to_raw_data()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "video_id": video_id,
        "language": transcript.language_code,
        "is_generated": transcript.is_generated,
        "segments": segments,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{video_id}: {len(segments)} cues, {transcript.language_code}"
          f"{' (auto)' if transcript.is_generated else ''} -> {out.name}")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="*", help="YouTube URLs or bare video ids")
    ap.add_argument("--from-cards", action="store_true",
                    help="fetch every video referenced by a flashcard")
    ap.add_argument("--force", action="store_true", help="refetch even if cached")
    args = ap.parse_args()

    ids = [extract_video_id(u) if "/" in u or "v=" in u else u for u in args.urls]
    if args.from_cards:
        ids += video_ids_from_cards()
    if not ids:
        ap.error("give at least one URL, or --from-cards")

    ok = sum(fetch(v, args.force) for v in dict.fromkeys(ids))
    print(f"\n{ok}/{len(set(ids))} transcripts available in {OUT_DIR}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
