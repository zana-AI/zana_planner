from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .sqlite_db import get_db_filename


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_data_dir() -> str:
    return os.getenv("USERS_DATA_DIR") or os.getenv("ROOT_DIR") or os.path.join(os.getcwd(), "USERS_DATA_DIR")


def _db_path(data_dir: str) -> str:
    return os.path.join(data_dir, get_db_filename())


def _connect_ro(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _list_users(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        """
        SELECT user_id FROM (
            SELECT user_id FROM promises
            UNION
            SELECT user_id FROM actions
            UNION
            SELECT user_id FROM sessions
            UNION
            SELECT user_id FROM users
        ) u
        ORDER BY user_id ASC;
        """
    ).fetchall()
    return [str(r["user_id"]) for r in rows if r["user_id"] is not None]


def _rows(conn: sqlite3.Connection, sql: str, params: tuple) -> List[Dict[str, Any]]:
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def export_user(conn: sqlite3.Connection, user_id: str) -> Dict[str, Any]:
    settings = conn.execute(
        "SELECT * FROM users WHERE user_id = ? LIMIT 1;",
        (user_id,),
    ).fetchone()

    promises = _rows(
        conn,
        "SELECT * FROM promises WHERE user_id = ? ORDER BY current_id ASC;",
        (user_id,),
    )
    aliases = _rows(
        conn,
        "SELECT * FROM promise_aliases WHERE user_id = ? ORDER BY alias_id ASC;",
        (user_id,),
    )
    promise_events = _rows(
        conn,
        "SELECT * FROM promise_events WHERE user_id = ? ORDER BY at_utc ASC;",
        (user_id,),
    )
    # Parse snapshot_json into structured objects when possible
    for ev in promise_events:
        try:
            ev["snapshot"] = json.loads(ev.get("snapshot_json") or "{}")
        except Exception:
            ev["snapshot"] = None

    actions = _rows(
        conn,
        "SELECT * FROM actions WHERE user_id = ? ORDER BY at_utc ASC;",
        (user_id,),
    )
    sessions = _rows(
        conn,
        "SELECT * FROM sessions WHERE user_id = ? ORDER BY started_at_utc ASC;",
        (user_id,),
    )

    return {
        "user_id": user_id,
        "settings": dict(settings) if settings else None,
        "promises": promises,
        "promise_aliases": aliases,
        "promise_events": promise_events,
        "actions": actions,
        "sessions": sessions,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Export Xaana SQLite data to JSON.")
    parser.add_argument("--data-dir", default=_default_data_dir(), help="Path to USERS_DATA_DIR (default: env USERS_DATA_DIR/ROOT_DIR).")
    parser.add_argument("--out", required=True, help="Output directory.")
    parser.add_argument("--user", default=None, help="Export a single user_id (TEXT). If omitted, exports all users.")
    parser.add_argument("--include-media", action="store_true", default=True, help="Include media files (avatars) in backup (default: True).")
    parser.add_argument("--no-media", dest="include_media", action="store_false", help="Exclude media files from backup.")
    args = parser.parse_args(argv)

    data_dir = os.path.abspath(args.data_dir)
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)

    db_path = _db_path(data_dir)
    if not os.path.exists(db_path):
        raise SystemExit(f"SQLite DB not found: {db_path}")

    with _connect_ro(db_path) as conn:
        if args.user:
            users = [str(args.user)]
        else:
            users = _list_users(conn)

        exported_at = _utc_now_iso()
        
        # Copy media files if requested
        media_count = 0
        if args.include_media:
            media_dir = os.path.join(data_dir, "media", "avatars")
            out_media_dir = os.path.join(out_dir, "media", "avatars")
            if os.path.exists(media_dir):
                import shutil
                os.makedirs(out_media_dir, exist_ok=True)
                for filename in os.listdir(media_dir):
                    if filename.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        src = os.path.join(media_dir, filename)
                        dst = os.path.join(out_media_dir, filename)
                        shutil.copy2(src, dst)
                        media_count += 1
        
        manifest = {
            "data_dir": data_dir,
            "db_path": db_path,
            "exported_at_utc": exported_at,
            "users": users,
            "media_files_count": media_count,
            "include_media": args.include_media,
        }

        with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        for uid in users:
            payload = export_user(conn, uid)
            payload["_meta"] = {"exported_at_utc": exported_at}
            with open(os.path.join(out_dir, f"user_{uid}.json"), "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

