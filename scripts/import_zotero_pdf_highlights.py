"""Copy annotations from a Zotero PDF attachment into Xaana.

First export from a copy of Zotero's SQLite database. It converts Zotero's
bottom-origin PDF coordinates into Xaana's normalised top-origin rectangles.
Then publish the JSON from within zana-webapp. Published rows are idempotent
by their Zotero item ID, kept in content_highlight.migration_status.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any


def normalise_rect(rect: list[float], width: float, height: float) -> dict[str, float]:
    """Translate a Zotero PDF rectangle to the web reader's CSS coordinate space."""
    if len(rect) != 4:
        raise ValueError(f"Expected four coordinates, got {rect!r}")
    x1, y1, x2, y2 = map(float, rect)
    left, right = sorted((x1, x2))
    bottom, top = sorted((y1, y2))
    return {
        "x": max(0.0, min(1.0, left / width)),
        "y": max(0.0, min(1.0, (height - top) / height)),
        "width": max(0.0, min(1.0, (right - left) / width)),
        "height": max(0.0, min(1.0, (top - bottom) / height)),
    }


def export_annotations(args: argparse.Namespace) -> None:
    from pypdf import PdfReader

    db_path, pdf_path = Path(args.zotero_db).resolve(), Path(args.pdf).resolve()
    if not db_path.is_file() or not pdf_path.is_file():
        raise SystemExit("Both --zotero-db and --pdf must be readable files")
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        attachment = connection.execute(
            "SELECT itemID FROM itemAttachments WHERE path = ?", (args.attachment_path,)
        ).fetchone()
        if not attachment:
            raise SystemExit("No Zotero attachment matches --attachment-path")
        attachment_id = int(attachment[0])
        rows = connection.execute(
            """
            SELECT itemID, type, text, comment, color, pageLabel, position
            FROM itemAnnotations WHERE parentItemID = ? ORDER BY itemID
            """,
            (attachment_id,),
        ).fetchall()
    finally:
        connection.close()

    reader = PdfReader(str(pdf_path))
    highlights: list[dict[str, Any]] = []
    skipped = 0
    for item_id, kind, selected_text, note, color, page_label, raw_position in rows:
        try:
            position = json.loads(raw_position)
            page_index = int(position["pageIndex"])
            page = reader.pages[page_index]
            rects = [
                normalise_rect(rect, float(page.mediabox.width), float(page.mediabox.height))
                for rect in position.get("rects", [])
            ]
            if not rects:
                skipped += 1
                continue
        except (KeyError, ValueError, TypeError, IndexError, json.JSONDecodeError):
            skipped += 1
            continue
        highlights.append({
            "zotero_item_id": int(item_id), "zotero_type": int(kind),
            "page_index": page_index, "page_label": page_label, "rects": rects,
            "selected_text": selected_text or None, "note": note or None,
            "color": color or "#ffe066",
        })
    Path(args.out).write_text(json.dumps({
        "source": "zotero", "attachment_path": args.attachment_path,
        "attachment_id": attachment_id, "pdf_pages": len(reader.pages),
        "highlights": highlights,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"exported={len(highlights)} skipped={skipped} attachment_id={attachment_id}")


def publish_annotations(args: argparse.Namespace) -> None:
    from db.postgres_db import get_db_session, utc_now_iso
    from sqlalchemy import text

    highlights = json.loads(Path(args.input).read_text(encoding="utf-8")).get("highlights", [])
    inserted = existing = 0
    now = utc_now_iso()
    with get_db_session() as session:
        for highlight in highlights:
            marker = f"zotero:{highlight['zotero_item_id']}"
            found = session.execute(text(
                "SELECT 1 FROM content_highlight WHERE user_id = :user_id "
                "AND content_id = :content_id AND migration_status = :marker"
            ), {"user_id": str(args.user_id), "content_id": str(args.content_id), "marker": marker}).scalar()
            if found:
                existing += 1
                continue
            session.execute(text("""
                INSERT INTO content_highlight (
                    id, user_id, content_id, asset_id, page_index, rects_json,
                    selected_text, note, color, created_at, updated_at, migration_status
                ) VALUES (
                    :id, :user_id, :content_id, :asset_id, :page_index, CAST(:rects AS jsonb),
                    :selected_text, :note, :color, :now, :now, :marker
                )
            """), {
                "id": str(uuid.uuid4()), "user_id": str(args.user_id),
                "content_id": str(args.content_id), "asset_id": str(args.asset_id),
                "page_index": int(highlight["page_index"]), "rects": json.dumps(highlight["rects"]),
                "selected_text": highlight.get("selected_text"), "note": highlight.get("note"),
                "color": highlight.get("color"), "now": now, "marker": marker,
            })
            inserted += 1
    print(f"inserted={inserted} already_present={existing} total={len(highlights)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("--zotero-db", required=True)
    export.add_argument("--pdf", required=True)
    export.add_argument("--attachment-path", required=True)
    export.add_argument("--out", required=True)
    publish = commands.add_parser("publish")
    publish.add_argument("--input", required=True)
    publish.add_argument("--user-id", required=True)
    publish.add_argument("--content-id", required=True)
    publish.add_argument("--asset-id", required=True)
    args = parser.parse_args()
    if args.command == "export":
        export_annotations(args)
    else:
        publish_annotations(args)


if __name__ == "__main__":
    main()
