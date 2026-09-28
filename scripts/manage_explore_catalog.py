"""Export or update curated Explore content without deploying application code.

Export prints a content hash. Import requires that hash so an editor cannot
silently overwrite changes made since the export. YAML files are exchange files
and should be kept outside the source repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import yaml
from sqlalchemy import bindparam, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tm_bot"))

from db.postgres_db import get_db_session
from services.explore_config import ExploreCatalog

VIDEO_REF = re.compile(r"[?&]video_id=([A-Za-z0-9_-]{11})(?:[&#]|$)")


def digest(document: dict) -> str:
    encoded = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_catalog(session, *, for_update: bool = False) -> dict:
    query = "SELECT document FROM explore_catalog WHERE id='main'"
    if for_update:
        query += " FOR UPDATE"
    document = session.execute(text(query)).scalar_one_or_none()
    if not isinstance(document, dict):
        raise ValueError("Explore catalog has not been seeded")
    return document


def video_refs(document: dict) -> dict[str, str]:
    refs = {}
    for category in document["categories"]:
        for topic in category.get("topics", []):
            for item in topic.get("items", []):
                if item.get("type") != "video" or not item.get("published", True):
                    continue
                match = VIDEO_REF.search(item.get("native_ref") or "")
                if not match:
                    raise ValueError(f"Published video {item['id']} has no valid YouTube watch route")
                if item["id"] in refs:
                    raise ValueError(f"Duplicate Explore video item ID: {item['id']}")
                refs[item["id"]] = match[1]
    return refs


def validate_document(document: dict) -> None:
    if not isinstance(document, dict) or not isinstance(document.get("categories"), list) or not document["categories"]:
        raise ValueError("Explore document must contain at least one category")
    ExploreCatalog.model_validate(document)
    category_ids = set()
    item_ids = set()
    for category in document["categories"]:
        if category["id"] in category_ids:
            raise ValueError(f"Duplicate Explore category ID: {category['id']}")
        category_ids.add(category["id"])
        topic_ids = set()
        for topic in category.get("topics", []):
            if topic["id"] in topic_ids:
                raise ValueError(f"Duplicate Explore topic ID: {topic['id']}")
            topic_ids.add(topic["id"])
            for item in topic.get("items", []):
                if item["id"] in item_ids:
                    raise ValueError(f"Duplicate Explore item ID: {item['id']}")
                item_ids.add(item["id"])


def require_new_videos_public(session, previous: dict, updated: dict) -> None:
    before = video_refs(previous)
    after = video_refs(updated)
    ids = {video_id for item_id, video_id in after.items() if before.get(item_id) != video_id}
    if not ids:
        return
    urls = ["https://www.youtube.com/watch?v=" + video_id for video_id in ids]
    rows = session.execute(text("""
        SELECT canonical_url FROM content WHERE canonical_url IN :urls AND visibility='public'
    """).bindparams(bindparam("urls", expanding=True)), {"urls": urls}).scalars().all()
    if set(rows) != set(urls):
        raise ValueError("New video entries must have public content rows before publication")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--output", type=Path, required=True)
    publish = sub.add_parser("import")
    publish.add_argument("--file", type=Path, required=True)
    publish.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()

    if args.command == "export":
        with get_db_session() as session:
            document = read_catalog(session)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"Exported Explore catalog to {args.output}; SHA-256: {digest(document)}")
        return

    document = yaml.safe_load(args.file.read_text(encoding="utf-8"))
    validate_document(document)
    with get_db_session() as session:
        previous = read_catalog(session, for_update=True)
        if digest(previous) != args.expected_sha256:
            raise ValueError("Explore catalog changed since export; export and review the current version")
        require_new_videos_public(session, previous, document)
        session.execute(text("""
            UPDATE explore_catalog SET document=CAST(:document AS jsonb), updated_at=now()
            WHERE id='main'
        """), {"document": json.dumps(document, ensure_ascii=False)})
    print(f"Published Explore catalog to PostgreSQL; SHA-256: {digest(document)}")


if __name__ == "__main__":
    main()
