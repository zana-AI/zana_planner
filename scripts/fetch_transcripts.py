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
import base64
import json
import re
import subprocess
import sys
import time
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


def fetch_with_backoff(video_id: str, force: bool, delay: float, attempts: int = 4) -> bool:
    """Fetch one transcript, backing off when YouTube starts refusing.

    Even a residential IP gets throttled if you pull transcripts back to back —
    a batch of ten will trip it. Pace the requests and retry the block with a
    widening wait rather than failing the whole batch.
    """
    wait = delay
    for attempt in range(1, attempts + 1):
        if fetch(video_id, force):
            time.sleep(delay)
            return True
        if attempt == attempts:
            return False
        wait *= 2
        print(f"   backing off {wait:.0f}s before retry {attempt + 1}/{attempts}")
        time.sleep(wait)
    return False


def psql(sql: str) -> str:
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", HOST, "docker", "exec", "-i",
         "zana-postgres", "psql", "-U", "zana", "-d", "zana", "-At", "-P", "footer=off"],
        input=sql, text=True, capture_output=True, encoding="utf-8", check=True)
    return proc.stdout.strip()


def push(video_id: str) -> bool:
    """Upload a fetched transcript into the video_transcript cache.

    The cues travel base64-encoded: a transcript is tens of kilobytes of French
    with quotes and apostrophes in it, and base64 survives the trip through ssh
    and psql without any quoting to get wrong.
    """
    path = OUT_DIR / f"{video_id}.json"
    if not path.exists():
        print(f"{video_id}: nothing to push (fetch it first)")
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    cues = [
        {"start": round(float(s["start"]), 2),
         "end": round(float(s["start"]) + float(s.get("duration") or 0), 2),
         "text": " ".join(s["text"].split())}
        for s in data["segments"] if s.get("text", "").strip()
    ]
    blob = base64.b64encode(json.dumps(cues, ensure_ascii=False).encode("utf-8")).decode("ascii")
    duration = cues[-1]["end"] if cues else 0
    language = (data.get("language") or "").replace("'", "")
    generated = str(bool(data.get("is_generated"))).lower()
    psql(
        "INSERT INTO video_transcript (video_id, language, is_generated, cues, cue_count,"
        " duration_seconds, source, fetched_at) VALUES ("
        f"'{video_id}', '{language}', {generated},"
        f" convert_from(decode('{blob}', 'base64'), 'UTF8')::jsonb,"
        f" {len(cues)}, {duration}, 'youtube_transcript_api', now())"
        " ON CONFLICT (video_id) DO UPDATE SET language = EXCLUDED.language,"
        " is_generated = EXCLUDED.is_generated, cues = EXCLUDED.cues,"
        " cue_count = EXCLUDED.cue_count, duration_seconds = EXCLUDED.duration_seconds,"
        " fetched_at = now();"
    )
    print(f"{video_id}: pushed {len(cues)} cues")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="*", help="YouTube URLs or bare video ids")
    ap.add_argument("--from-cards", action="store_true",
                    help="fetch every video referenced by a flashcard")
    ap.add_argument("--force", action="store_true", help="refetch even if cached")
    ap.add_argument("--delay", type=float, default=6.0,
                    help="seconds to pause between videos (YouTube throttles bursts)")
    ap.add_argument("--push", action="store_true",
                    help="upload fetched transcripts into the production cache")
    args = ap.parse_args()

    ids = [extract_video_id(u) if "/" in u or "v=" in u else u for u in args.urls]
    if args.from_cards:
        ids += video_ids_from_cards()
    if not ids:
        ap.error("give at least one URL, or --from-cards")

    unique = list(dict.fromkeys(ids))
    ok = sum(fetch_with_backoff(v, args.force, args.delay) for v in unique)
    print(f"\n{ok}/{len(unique)} transcripts available in {OUT_DIR}")

    if args.push:
        pushed = sum(push(v) for v in unique)
        print(f"{pushed}/{len(unique)} pushed to the production cache")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
