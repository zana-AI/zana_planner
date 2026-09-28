"""One-time import of a live Explore YAML file into the database catalog.

Only inserts when the catalog is empty. This preserves the currently published
document while deploying a database-backed loader for the first time.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tm_bot"))

from db.postgres_db import get_db_session
from services.explore_config import ExploreCatalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True, help="Current live Explore YAML")
    parser.add_argument("--apply", action="store_true", help="Insert into PostgreSQL")
    args = parser.parse_args()

    if args.file.suffix.lower() == ".json":
        document = json.loads(args.file.read_text(encoding="utf-8"))
    else:
        import yaml

        document = yaml.safe_load(args.file.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("categories"), list) or not document["categories"]:
        raise ValueError("Explore document must contain at least one category")
    catalog = ExploreCatalog.model_validate(document)
    item_count = sum(len(topic.items) for category in catalog.categories for topic in category.topics)
    if not args.apply:
        print(f"Validated {len(catalog.categories)} categories and {item_count} items; no database changes")
        return

    with get_db_session() as session:
        existing = session.execute(text("SELECT document FROM explore_catalog WHERE id='main' FOR UPDATE")).scalar_one_or_none()
        if existing is not None:
            if existing != document:
                raise ValueError("Explore catalog already exists with different content; refusing to overwrite it")
            print("Explore catalog already contains the same document")
            return
        session.execute(
            text("INSERT INTO explore_catalog (id, document) VALUES ('main', CAST(:document AS jsonb))"),
            {"document": json.dumps(document, ensure_ascii=False)},
        )
    print(f"Seeded Explore catalog with {len(catalog.categories)} categories and {item_count} items")


if __name__ == "__main__":
    main()
