"""Fill missing YouTube Library metadata with batched videos.list requests.

Run inside the webapp container from /app with YOUTUBE_API_KEY set. Existing
nonempty values are preserved. A dry run is the default; pass --apply to write.
"""
import argparse
import os
import re
import sys
from pathlib import Path

import requests
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tm_bot"))
from db.postgres_db import get_db_session  # noqa: E402
from utils.youtube_utils import parse_youtube_duration  # noqa: E402


VIDEO_ID = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes to the content table")
    args = parser.parse_args()
    key = os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        parser.error("YOUTUBE_API_KEY or GOOGLE_API_KEY is required")

    with get_db_session() as db:
        rows = db.execute(text("""
            SELECT id, canonical_url, original_url, metadata_json
            FROM content
            WHERE provider = 'youtube'
              AND (NULLIF(TRIM(language), '') IS NULL OR NULLIF(TRIM(published_at), '') IS NULL
                   OR duration_seconds IS NULL OR duration_seconds <= 0
                   OR LOWER(TRIM(COALESCE(description, ''))) = 'no description available')
        """)).mappings().all()

    by_video: dict[str, list[str]] = {}
    for row in rows:
        metadata = row["metadata_json"] or {}
        candidate = metadata.get("video_id") if isinstance(metadata, dict) else None
        match = VIDEO_ID.search(str(row["canonical_url"] or row["original_url"] or ""))
        video_id = candidate if isinstance(candidate, str) and re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate) else match.group(1) if match else None
        if video_id:
            by_video.setdefault(video_id, []).append(str(row["id"]))

    print(f"Eligible rows: {len(rows)}; unique videos: {len(by_video)}; mode: {'apply' if args.apply else 'dry run'}")
    updated = 0
    ids = list(by_video)
    for start in range(0, len(ids), 50):
        batch = ids[start:start + 50]
        response = requests.get("https://www.googleapis.com/youtube/v3/videos", params={
            "id": ",".join(batch), "part": "snippet,contentDetails", "key": key,
        }, timeout=20)
        response.raise_for_status()
        found = response.json().get("items") or []
        if not args.apply:
            updated += sum(len(by_video[item["id"]]) for item in found if item.get("id") in by_video)
            continue
        with get_db_session() as db:
            for item in found:
                video_id = item.get("id")
                if video_id not in by_video:
                    continue
                snippet = item.get("snippet") or {}
                details = item.get("contentDetails") or {}
                duration = parse_youtube_duration(details.get("duration") or "")
                # Audio language is about the spoken content. Metadata language
                # alone may describe a translated title, so do not infer from it.
                language = snippet.get("defaultAudioLanguage")
                for content_id in by_video[video_id]:
                    db.execute(text("""
                        UPDATE content SET
                          language = COALESCE(NULLIF(TRIM(language), ''), :language),
                          published_at = COALESCE(NULLIF(TRIM(published_at), ''), :published_at),
                          duration_seconds = CASE WHEN duration_seconds IS NULL OR duration_seconds <= 0
                                                  THEN COALESCE(:duration, duration_seconds) ELSE duration_seconds END,
                          description = CASE WHEN LOWER(TRIM(COALESCE(description, ''))) = 'no description available'
                                             THEN NULL ELSE description END
                        WHERE id = :id
                    """), {"id": content_id, "language": language, "published_at": snippet.get("publishedAt"), "duration": duration})
                    updated += 1
        print(f"Processed {min(start + 50, len(ids))}/{len(ids)} videos")
    print(f"Matched content rows: {updated}")
    if args.apply:
        with get_db_session() as db:
            captions = db.execute(text("""
                UPDATE content AS c SET language = t.language
                FROM video_transcript AS t
                WHERE c.provider = 'youtube'
                  AND NULLIF(TRIM(c.language), '') IS NULL
                  AND c.metadata_json->>'video_id' = t.video_id
                  AND t.is_generated = TRUE AND t.cue_count > 0
                  AND t.language ~ '^[a-z]{2,3}(-[A-Za-z0-9]+)*$'
            """))
            print(f"Languages filled from generated captions: {captions.rowcount}")


if __name__ == "__main__":
    main()
