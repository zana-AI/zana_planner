"""Preview or atomically publish a verified language batch in PostgreSQL.

Supply an external batch YAML with --batch. The catalog and public content rows
commit together; no content file is written into the application image.
Existing private/club content is never made public by this script.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import html
import json
import math
from pathlib import Path
import re
import sys
import uuid

import yaml
from sqlalchemy import bindparam, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tm_bot"))


def validate_batch(batch):
    items = batch.get("items", [])
    if batch.get("status") != "metadata_verified":
        raise ValueError("Run build_language_catalog.py --verify before publishing")
    if Counter(i.get("language") for i in items) != {"fr": 100, "en": 100}:
        raise ValueError("Expected exactly 100 French and 100 English videos")
    ids = [i.get("video_id", "") for i in items]
    if len(set(ids)) != 200 or not all(re.fullmatch(r"[A-Za-z0-9_-]{11}", v) for v in ids):
        raise ValueError("Video IDs must be unique, valid YouTube IDs")
    for item in items:
        if item.get("url") != "https://www.youtube.com/watch?v=" + item["video_id"]:
            raise ValueError("Only canonical YouTube URLs are accepted")
        duration = item.get("duration_seconds")
        if not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 480 <= duration <= 1440:
            raise ValueError("Every video must be 8-24 minutes")
        if (item.get("availability") != "public" or item.get("embedding_status") != "allowed"
                or item.get("age_limit") != 0
                or item.get("caption_status") != "source_track_advertised_not_cached"
                or item.get("caption_language", "").split("-")[0] != item["language"]):
            raise ValueError("Missing public/embed/original-language caption verification")
        for field in ("title", "creator", "target_level", "selection_reason", "channel_id", "verified_at"):
            if not item.get(field):
                raise ValueError(f"Missing {field}")
    return items


def description(item):
    return f"{item['target_level']} estimate. {item['selection_reason']}"


def merge_catalog(catalog, batch):
    result = deepcopy(catalog)
    # Reject video references in a different subject rather than duplicating them.
    existing = {}
    existing_item_ids = set()
    for category in result["categories"]:
        for topic in category.get("topics", []):
            for item in topic.get("items", []):
                existing_item_ids.add(item["id"])
                match = re.search(r"[?&]video_id=([\w-]{11})(?:[&#]|$)", item.get("native_ref", ""))
                if match:
                    existing[match[1]] = (category.get("language"), topic["id"])
    for language in ("fr", "en"):
        category = next(c for c in result["categories"] if c.get("language") == language)
        topic = next(t for t in category["topics"] if t["id"] == "watch")
        order = max((i.get("order", 0) for i in topic["items"]), default=0)
        for item in batch["items"]:
            if item["language"] != language:
                continue
            video_id = item["video_id"]
            if video_id in existing:
                if existing[video_id] != (language, "watch"):
                    raise ValueError(f"Existing video {video_id} belongs to another category/topic")
                continue
            item_id = "language-200-" + video_id
            if item_id in existing_item_ids:
                raise ValueError(f"Catalog item ID collision: {item_id}")
            order += 1
            topic["items"].append({
                "id": item_id, "title": item["title"], "creator": item["creator"],
                "type": "video", "order": order, "published": True,
                "description": description(item), "duration_seconds": item["duration_seconds"],
                "image": f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                "native_ref": "/youtube-watch?video_id=" + video_id,
            })
    return result


def insert_public_content(batch, session):
    urls = [item["url"] for item in batch["items"]]
    # This runs inside the same transaction as the catalog update. The unique
    # URL constraint also handles concurrent creation by app requests.
    session.execute(text("SELECT pg_advisory_xact_lock(210927200)"))
    rows = session.execute(text(
        "SELECT canonical_url, visibility FROM content WHERE canonical_url IN :urls"
    ).bindparams(bindparam("urls", expanding=True)), {"urls": urls}).mappings().all()
    private = [r["canonical_url"] for r in rows if r["visibility"] != "public"]
    if private:
        raise ValueError("Existing non-public rows require replacement candidates: " + ", ".join(private))
    for item in batch["items"]:
        session.execute(text("""
            INSERT INTO content (id, canonical_url, original_url, provider, content_type,
                title, description, author_channel, language, duration_seconds,
                thumbnail_url, metadata_json, visibility, created_at, updated_at)
            VALUES (:id, :url, :url, 'youtube', 'video', :title, :description,
                :creator, :language, :duration_seconds, :thumbnail, CAST(:metadata AS jsonb),
                'public', now(), now())
            ON CONFLICT (canonical_url) DO NOTHING
        """), {**item, "id": str(uuid.uuid4()), "description": description(item),
               "thumbnail": f"https://img.youtube.com/vi/{item['video_id']}/mqdefault.jpg",
               "metadata": json.dumps({"video_id": item["video_id"], "channel": item["creator"],
                   "language": item["language"], "catalog_batch": batch["batch_id"],
                   "level_estimate": item["target_level"], "level_evidence": item["level_evidence"]})})
    public_count = session.execute(text(
        "SELECT count(*) FROM content WHERE canonical_url IN :urls AND visibility = 'public'"
    ).bindparams(bindparam("urls", expanding=True)), {"urls": urls}).scalar_one()
    if public_count != 200:
        raise ValueError("Public content precondition failed; rolling back batch")


def write_review(batch, path):
    counts = Counter(i["creator"] for i in batch["items"])
    total = sum(i["duration_seconds"] for i in batch["items"]) / 3600
    rows = []
    for item in batch["items"]:
        e = html.escape
        duration = int(item["duration_seconds"])
        search = " ".join(str(item[k]) for k in ("title", "creator", "language", "target_level"))
        rows.append(f'<tr data-lang="{item["language"]}" data-search="{e(search.lower(), quote=True)}">'
                    f'<td>{item["language"].upper()}</td><td><a href="{e(item["url"], quote=True)}" '
                    f'target="_blank" rel="noopener noreferrer">{e(item["title"])}</a>'
                    f'<small>{e(item["creator"])}</small></td><td>{duration//60}:{duration%60:02d}</td>'
                    f'<td>{e(item["target_level"])}</td>'
                    f'<td>{"Automatic" if item["caption_is_generated"] else "Creator uploaded"}</td></tr>')
    source_list = " · ".join(f"{html.escape(name)}: {count}" for name, count in counts.items())
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Xaana · 200 language videos</title><style>
body{font:16px/1.6 system-ui;margin:40px auto;padding:0 24px;max-width:1180px;background:#faf9f5;color:#17252a}
h1{font-size:38px;line-height:1.15}p{max-width:950px;color:#43545a}small{display:block;color:#64767b}
.stats{font-size:22px;font-weight:650;color:#126d6a}.controls{display:flex;gap:12px;position:sticky;top:0;background:#faf9f5;padding:16px 0}
input,select{font:inherit;padding:10px;border:1px solid #bdccca;border-radius:8px}input{flex:1;min-width:80px}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:14px 10px;border-bottom:1px solid #dce4df;vertical-align:top}
th{font-size:13px;text-transform:uppercase;color:#64767b}a{color:#116e72;text-decoration:none}a:hover{text-decoration:underline}
td:nth-child(2){width:60%}[hidden]{display:none}@media(max-width:650px){body{padding:0 12px}th:last-child,td:last-child{display:none}h1{font-size:28px}}
</style><body><small>XAANA · CONTENT BATCH · SEPTEMBER 2026</small><h1>Something worth watching.<br>In French and English.</h1>
<p class="stats">100 French · 100 English · 8–24 minutes · TOTAL_HOURS hours</p>
<p>Prepared locally. Individual watch metadata verifies public availability, embedding permission and an original-language caption track.
Levels are source/title estimates, not individual CEFR assessments. Caption tracks have not been downloaded into Xaana.</p>
<details><summary>Creator mix</summary><p>SOURCE_LIST</p></details>
<div class="controls"><select id="language" aria-label="Language"><option value="">Both languages</option><option value="fr">French</option><option value="en">English</option></select>
<input id="search" placeholder="Search title, creator or level…" aria-label="Search"><span id="count">200 videos</span></div>
<table><thead><tr><th>Language</th><th>Video / creator</th><th>Length</th><th>Level estimate</th><th>YouTube captions</th></tr></thead><tbody>ROWS</tbody></table>
<script>const rows=[...document.querySelectorAll('tbody tr')],language=document.querySelector('#language'),search=document.querySelector('#search');
function filter(){let n=0;for(const row of rows){row.hidden=!!((language.value&&row.dataset.lang!==language.value)||!row.dataset.search.includes(search.value.toLowerCase()));if(!row.hidden)n++}document.querySelector('#count').textContent=n+' videos'}
language.addEventListener('change',filter);search.addEventListener('input',filter);</script></body></html>'''
    path.write_text(page.replace("TOTAL_HOURS", f"{total:.1f}").replace("SOURCE_LIST", source_list)
                    .replace("ROWS", "\n".join(rows)), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "exports/language-catalog-preview.yaml")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    batch = yaml.safe_load(args.batch.read_text(encoding="utf-8"))
    validate_batch(batch)
    from services.explore_config import ExploreCatalog
    from db.postgres_db import get_db_session

    if args.apply:
        now = datetime.now(timezone.utc)
        for item in batch["items"]:
            age = (now - datetime.fromisoformat(item["verified_at"])).total_seconds()
            if not 0 <= age <= 7 * 86400:
                raise ValueError("Verification is older than seven days; refresh before publishing")

    with get_db_session() as session:
        statement = "SELECT document FROM explore_catalog WHERE id='main'"
        if args.apply:
            statement += " FOR UPDATE"
        original = session.execute(text(statement)).scalar_one_or_none()
        if not isinstance(original, dict):
            raise ValueError("Explore catalog has not been seeded")
        catalog = merge_catalog(original, batch)
        ExploreCatalog.model_validate(catalog)
        if args.apply:
            insert_public_content(batch, session)
            session.execute(text("""
                UPDATE explore_catalog SET document=CAST(:document AS jsonb), updated_at=now()
                WHERE id='main'
            """), {"document": json.dumps(catalog, ensure_ascii=False)})

    if args.apply:
        print("Published 200-item batch to PostgreSQL in one transaction")
    else:
        rendered = yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False, width=110)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        write_review(batch, args.output.with_suffix(".html"))
        print(f"Prepared 200-item merged catalog and HTML review at {args.output}; no database changes")


if __name__ == "__main__":
    main()
