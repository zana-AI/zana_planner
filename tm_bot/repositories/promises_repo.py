import json
import uuid
from typing import List, Optional

from db.legacy_importer import ensure_imported
from db.sqlite_db import (
    date_from_iso,
    date_to_iso,
    json_compat,
    resolve_promise_uuid,
    utc_now_iso,
    connection_for_root,
)
from models.models import Promise


class PromisesRepository:
    """
    SQLite-backed promises repository.

    - One global DB file: <root_dir>/zana.db
    - Keeps promise history in `promise_events`
    - Supports promise ID renames via `promise_aliases`
    """

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def list_promises(self, user_id: int) -> List[Promise]:
        user = str(user_id)
        with connection_for_root(self.root_dir) as conn:
            ensure_imported(conn, self.root_dir, user, "promises")
            rows = conn.execute(
                """
                SELECT current_id, text, hours_per_week, recurring, start_date, end_date, angle_deg, radius, visibility
                FROM promises
                WHERE user_id = ? AND is_deleted = 0
                ORDER BY current_id ASC;
                """,
                (user,),
            ).fetchall()

        promises: List[Promise] = []
        for r in rows:
            promises.append(
                Promise(
                    user_id=user,
                    id=str(r["current_id"]),
                    text=str(r["text"]),
                    hours_per_week=float(r["hours_per_week"]),
                    recurring=bool(int(r["recurring"])),
                    start_date=date_from_iso(r["start_date"]),
                    end_date=date_from_iso(r["end_date"]),
                    angle_deg=int(r["angle_deg"]),
                    radius=int(r["radius"]),
                    visibility=str(r.get("visibility") or "private"),
                )
            )
        return promises

    def get_promise(self, user_id: int, promise_id: str) -> Optional[Promise]:
        user = str(user_id)
        pid = (promise_id or "").strip().upper()
        if not pid:
            return None

        with connection_for_root(self.root_dir) as conn:
            ensure_imported(conn, self.root_dir, user, "promises")
            p_uuid = resolve_promise_uuid(conn, user, pid)
            if not p_uuid:
                return None

            row = conn.execute(
                """
                SELECT current_id, text, hours_per_week, recurring, start_date, end_date, angle_deg, radius, is_deleted, visibility
                FROM promises
                WHERE user_id = ? AND promise_uuid = ?
                LIMIT 1;
                """,
                (user, p_uuid),
            ).fetchone()

        if not row or int(row["is_deleted"]) == 1:
            return None

        return Promise(
            user_id=user,
            id=str(row["current_id"]),
            text=str(row["text"]),
            hours_per_week=float(row["hours_per_week"]),
            recurring=bool(int(row["recurring"])),
            start_date=date_from_iso(row["start_date"]),
            end_date=date_from_iso(row["end_date"]),
            angle_deg=int(row["angle_deg"]),
            radius=int(row["radius"]),
            visibility=str(row.get("visibility") or "private"),
        )

    def upsert_promise(self, user_id: int, promise: Promise) -> None:
        user = str(user_id)
        pid = (promise.id or "").strip().upper()
        if not pid:
            raise ValueError("Promise.id is required")

        now = utc_now_iso()
        with connection_for_root(self.root_dir) as conn:
            ensure_imported(conn, self.root_dir, user, "promises")

            p_uuid = resolve_promise_uuid(conn, user, pid)
            # Optional explicit rename support: callers may set `promise.old_id`
            # to indicate this upsert should target an existing promise.
            if not p_uuid:
                old_id = getattr(promise, "old_id", None)
                old_id = (old_id or "").strip().upper()
                if old_id and old_id != pid:
                    p_uuid = resolve_promise_uuid(conn, user, old_id)
            existing = None
            if p_uuid:
                existing = conn.execute(
                    "SELECT current_id, is_deleted FROM promises WHERE user_id = ? AND promise_uuid = ? LIMIT 1;",
                    (user, p_uuid),
                ).fetchone()
            is_new = not bool(existing)
            if is_new:
                p_uuid = str(uuid.uuid4())

            # If renaming current_id, ensure uniqueness and keep old id as alias
            event_type = "create" if is_new else "update"
            if existing and str(existing["current_id"]) != pid:
                # Ensure no other promise already uses the new current_id
                clash = conn.execute(
                    """
                    SELECT promise_uuid FROM promises
                    WHERE user_id = ? AND current_id = ? AND promise_uuid <> ?
                    LIMIT 1;
                    """,
                    (user, pid, p_uuid),
                ).fetchone()
                if clash:
                    raise ValueError(f"Promise ID '{pid}' is already in use.")

                # Keep old ID as an alias indefinitely
                old_id = str(existing["current_id"])
                conn.execute(
                    """
                    INSERT OR IGNORE INTO promise_aliases(user_id, alias_id, promise_uuid, created_at_utc)
                    VALUES (?, ?, ?, ?);
                    """,
                    (user, old_id, p_uuid, now),
                )
                # Also ensure the new ID is registered as an alias
                conn.execute(
                    """
                    INSERT OR IGNORE INTO promise_aliases(user_id, alias_id, promise_uuid, created_at_utc)
                    VALUES (?, ?, ?, ?);
                    """,
                    (user, pid, p_uuid, now),
                )
                event_type = "rename"

            conn.execute(
                """
                INSERT OR REPLACE INTO promises(
                    promise_uuid, user_id, current_id, text, hours_per_week, recurring,
                    start_date, end_date, angle_deg, radius, is_deleted, visibility,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    p_uuid,
                    user,
                    pid,
                    promise.text or "",
                    float(promise.hours_per_week or 0.0),
                    1 if bool(promise.recurring) else 0,
                    date_to_iso(promise.start_date),
                    date_to_iso(promise.end_date),
                    int(promise.angle_deg or 0),
                    int(promise.radius or 0),
                    0,
                    str(promise.visibility or "private"),
                    now if is_new else (now),  # best-effort timestamps per plan
                    now,
                ),
            )

            # Ensure current id is an alias too
            conn.execute(
                """
                INSERT OR IGNORE INTO promise_aliases(user_id, alias_id, promise_uuid, created_at_utc)
                VALUES (?, ?, ?, ?);
                """,
                (user, pid, p_uuid, now),
            )

            snapshot = json.dumps(
                {
                    **json_compat(promise),
                    "id": pid,
                    "is_deleted": False,
                },
                ensure_ascii=False,
            )
            conn.execute(
                """
                INSERT INTO promise_events(event_uuid, promise_uuid, user_id, event_type, at_utc, snapshot_json)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (str(uuid.uuid4()), p_uuid, user, event_type, now, snapshot),
            )

    def delete_promise(self, user_id: int, promise_id: str) -> bool:
        user = str(user_id)
        pid = (promise_id or "").strip().upper()
        if not pid:
            return False

        now = utc_now_iso()
        with connection_for_root(self.root_dir) as conn:
            ensure_imported(conn, self.root_dir, user, "promises")
            p_uuid = resolve_promise_uuid(conn, user, pid)
            if not p_uuid:
                return False

            row = conn.execute(
                "SELECT current_id, text, hours_per_week, recurring, start_date, end_date, angle_deg, radius, is_deleted "
                "FROM promises WHERE user_id = ? AND promise_uuid = ? LIMIT 1;",
                (user, p_uuid),
            ).fetchone()
            if not row or int(row["is_deleted"]) == 1:
                return False

            conn.execute(
                "UPDATE promises SET is_deleted = 1, updated_at_utc = ? WHERE user_id = ? AND promise_uuid = ?;",
                (now, user, p_uuid),
            )

            snapshot = json.dumps(
                {
                    "id": str(row["current_id"]),
                    "text": str(row["text"]),
                    "hours_per_week": float(row["hours_per_week"]),
                    "recurring": bool(int(row["recurring"])),
                    "start_date": str(row["start_date"] or ""),
                    "end_date": str(row["end_date"] or ""),
                    "angle_deg": int(row["angle_deg"]),
                    "radius": int(row["radius"]),
                    "is_deleted": True,
                },
                ensure_ascii=False,
            )
            conn.execute(
                """
                INSERT INTO promise_events(event_uuid, promise_uuid, user_id, event_type, at_utc, snapshot_json)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (str(uuid.uuid4()), p_uuid, user, "delete", now, snapshot),
            )

        return True
