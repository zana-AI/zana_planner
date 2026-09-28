"""Build a reproducible, metadata-only candidate batch for Explore.

No media downloads, database writes, or automatic publication. Source-specific
rules come from an external YAML file; exact selected records remain reviewable.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]


def eligible(entry, source):
    title = entry.get("title") or ""
    duration = entry.get("duration")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", entry.get("id") or ""):
        return False
    if not isinstance(duration, (int, float)) or not 480 <= duration <= 1440:
        return False
    if entry.get("live_status") in {"is_live", "is_upcoming", "post_live"}:
        return False
    if entry.get("availability") in {"private", "premium_only", "subscriber_only", "needs_auth"}:
        return False
    if source.get("include") and not re.search(source["include"], title, re.I):
        return False
    if source.get("exclude") and re.search(source["exclude"], title, re.I):
        return False
    return True


def collect(source, cache_dir, refresh=False):
    import yt_dlp
    cache = cache_dir / (source["id"] + ".json")
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    options = dict(quiet=True, no_warnings=True, skip_download=True,
                   extract_flat=True, playlistend=source.get("scan_limit", 250),
                   socket_timeout=15, retries=1, extractor_retries=1)
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(source["url"], download=False)
    fields = ("id", "title", "duration", "url", "live_status", "availability")
    result = {"source_id": source["id"], "channel": info.get("channel"),
              "channel_id": info.get("channel_id"),
              "channel_description": info.get("description"),
              "retrieved_at": datetime.now(timezone.utc).isoformat(),
              "entries": [{k: e.get(k) for k in fields}
                          for e in info.get("entries", []) if e]}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def verify_video(entry, source, channel_id, cache_dir, refresh=False):
    """Check individual public watch metadata; never download media/captions."""
    import yt_dlp
    from caption_relay.fetch import ytdlp_source_tracks
    cache = cache_dir / (entry["id"] + ".json")
    if cache.exists() and not refresh:
        info = json.loads(cache.read_text(encoding="utf-8"))
    else:
        try:
            with yt_dlp.YoutubeDL(dict(quiet=True, no_warnings=True, skip_download=True,
                                      socket_timeout=12, retries=0, extractor_retries=0)) as ydl:
                raw = ydl.extract_info("https://www.youtube.com/watch?v=" + entry["id"], download=False)
            tracks = ytdlp_source_tracks(raw)
            info = {k: raw.get(k) for k in ("id", "title", "duration", "language", "availability",
                                           "age_limit", "live_status", "playable_in_embed", "channel_id")}
            info["source_caption_tracks"] = [{"language": lang, "is_generated": generated}
                                             for lang, generated, _ in tracks]
            info["verified_at"] = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            info = {"error": type(exc).__name__}
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    tracks = [t for t in info.get("source_caption_tracks", [])
              if t["language"].split("-")[0] == source["language"]]
    if (info.get("error") or info.get("id") != entry["id"]
            or info.get("channel_id") != channel_id or not eligible(info, source)
            or info.get("availability") != "public" or info.get("age_limit") != 0
            or info.get("playable_in_embed") is not True or not tracks):
        return None
    return {"title": info["title"], "duration_seconds": info["duration"],
            "caption_status": "source_track_advertised_not_cached",
            "caption_language": tracks[0]["language"], "caption_is_generated": tracks[0]["is_generated"],
            "embedding_status": "allowed", "availability": "public", "age_limit": 0,
            "verified_at": info["verified_at"]}


def select(sources, collected, existing_ids, per_language=100, verify=None):
    pools = {}
    for source in sources:
        data = collected.get(source["id"], {})
        pools[source["id"]] = [e for e in data.get("entries", [])
                               if eligible(e, source) and e["id"] not in existing_ids]
    picked, seen, counts = [], set(existing_ids), Counter()
    # Round-robin gives each creator a turn; preserve source ordering on disk.
    for language in ("fr", "en"):
        matching = [s for s in sources if s["language"] == language]
        while sum(e["language"] == language for e in picked) < per_language:
            advanced = False
            for source in matching:
                if sum(e["language"] == language for e in picked) >= per_language:
                    break
                pool = pools[source["id"]]
                while pool and pool[0]["id"] in seen:
                    pool.pop(0)
                if not pool or counts[source["id"]] >= source.get("max_items", 30):
                    continue
                entry = pool.pop(0)
                seen.add(entry["id"])
                advanced = True
                verification = verify(entry, source, collected[source["id"]]["channel_id"]) if verify else {}
                if verification is None:
                    print(f"Rejected {source['id']}/{entry['id']}: verification gate", flush=True)
                    continue
                counts[source["id"]] += 1
                picked.append({
                    "video_id": entry["id"], "title": entry["title"],
                    "url": "https://www.youtube.com/watch?v=" + entry["id"],
                    "language": language, "duration_seconds": entry["duration"],
                    "creator": collected[source["id"]]["channel"],
                    "source_id": source["id"], "source_url": source["url"],
                    "channel_id": collected[source["id"]]["channel_id"],
                    "target_level": source["target_level"],
                    "level_evidence": "Source/title estimate; not individually CEFR assessed",
                    "selection_reason": source["reason"],
                    "retrieved_at": collected[source["id"]]["retrieved_at"],
                    "caption_status": "unchecked", "embedding_status": "unchecked",
                    **verification,
                })
                if verify and len(picked) % 10 == 0:
                    print(f"Verified {len(picked)}/200", flush=True)
            if not advanced:
                raise ValueError(f"Insufficient eligible {language} items: "
                                 f"{sum(e['language'] == language for e in picked)}/{per_language}")
    return picked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True, help="External source rules YAML")
    parser.add_argument("--catalog", type=Path, required=True, help="Exported current Explore catalog YAML")
    parser.add_argument("--cache", type=Path, default=ROOT / "exports/language-catalog-cache")
    parser.add_argument("--output", type=Path, default=ROOT / "exports/language-batch-200.yaml")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--verify", action="store_true", help="Require public, embeddable videos with source-language caption tracks")
    parser.add_argument("--exclude-video-id", action="append", default=[], help="Exclude a known conflict; may be repeated")
    args = parser.parse_args()
    sources = yaml.safe_load(args.sources.read_text(encoding="utf-8"))["sources"]
    collected = {}
    for source in sources:
        try:
            data = collect(source, args.cache, args.refresh)
            collected[source["id"]] = data
            eligible_count = sum(eligible(e, source) for e in data["entries"])
            print(f"{source['id']}: {len(data['entries'])} scanned, {eligible_count} eligible", flush=True)
        except Exception as exc:
            print(f"{source['id']}: collection failed ({type(exc).__name__})", flush=True)
    if args.collect_only:
        return
    existing = set(re.findall(r"video_id=([\w-]{11})", args.catalog.read_text(encoding="utf-8")))
    if any(not re.fullmatch(r"[A-Za-z0-9_-]{11}", v) for v in args.exclude_video_id):
        parser.error("--exclude-video-id requires an 11-character YouTube ID")
    existing.update(args.exclude_video_id)
    verify = (lambda e, s, c: verify_video(e, s, c, args.cache / "verified", args.refresh)) if args.verify else None
    items = select(sources, collected, existing, verify=verify)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump({
        "version": 1, "status": "metadata_verified" if args.verify else "candidate", "batch_id": "language-200-2026-09",
        "selection": {"fr": 100, "en": 100, "duration_seconds": [480, 1440]},
        "items": items,
    }, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
    print(f"Wrote {len(items)} candidates to {args.output}", flush=True)


if __name__ == "__main__":
    main()
