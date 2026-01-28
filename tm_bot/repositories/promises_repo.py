import json
import uuid
from typing import List, Optional

from sqlalchemy import text

from db.postgres_db import (
    date_from_iso,
    date_to_iso,
    json_compat,
    resolve_promise_uuid,
    utc_now_iso,
    get_db_session,
)
from models.models import Promise


class PromisesRepository:
    """
    PostgreSQL-backed promises repository.

    - Uses environment-based database connection (DATABASE_URL_PROD or DATABASE_URL_STAGING)
    - Keeps promise history in `promise_events`
    - Supports promise ID renames via `promise_aliases`
    """

    def __init__(self, root_dir: str = None):
        # root_dir kept for backward compatibility but not used for PostgreSQL
        self.root_dir = root_dir

    def list_promises(self, user_id: int) -> List[Promise]:
        user = str(user_id)
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT current_id, text, hours_per_week, recurring, start_date, end_date, visibility, description
                    FROM promises
                    WHERE user_id = :user_id AND is_deleted = 0
                    ORDER BY current_id ASC;
                """),
                {"user_id": user},
            ).mappings().fetchall()

        promises: List[Promise] = []
        for r in rows:
            # Handle visibility column - may not exist in older schemas
            visibility = "private"
            if "visibility" in r.keys():
                visibility = str(r["visibility"] or "private")
            
            # Handle description column - may not exist in older schemas
            description = None
            if "description" in r.keys():
                description = str(r["description"]) if r["description"] else None
            
            promises.append(
                Promise(
                    user_id=user,
                    id=str(r["current_id"]),
                    text=str(r["text"]),
                    hours_per_week=float(r["hours_per_week"]),
                    recurring=bool(int(r["recurring"])),
                    start_date=date_from_iso(r["start_date"]),
                    end_date=date_from_iso(r["end_date"]),
                    visibility=visibility,
                    description=description,
                )
            )
        return promises

    def get_promise(self, user_id: int, promise_id: str) -> Optional[Promise]:
        user = str(user_id)
        pid = (promise_id or "").strip().upper()
        if not pid:
            return None

        with get_db_session() as session:
            p_uuid = resolve_promise_uuid(session, user, pid)
            if not p_uuid:
                return None

            row = session.execute(
                text("""
                    SELECT current_id, text, hours_per_week, recurring, start_date, end_date, is_deleted, visibility, description
                    FROM promises
                    WHERE user_id = :user_id AND promise_uuid = :p_uuid
                    LIMIT 1;
                """),
                {"user_id": user, "p_uuid": p_uuid},
            ).mappings().fetchone()

        if not row or int(row["is_deleted"]) == 1:
            return None

        # Handle visibility column - may not exist in older schemas
        visibility = "private"
        if "visibility" in row.keys():
            visibility = str(row["visibility"] or "private")

        # Handle description column - may not exist in older schemas
        description = None
        if "description" in row.keys():
            description = str(row["description"]) if row["description"] else None

        return Promise(
            user_id=user,
            id=str(row["current_id"]),
            text=str(row["text"]),
            hours_per_week=float(row["hours_per_week"]),
            recurring=bool(int(row["recurring"])),
            start_date=date_from_iso(row["start_date"]),
            end_date=date_from_iso(row["end_date"]),
            visibility=visibility,
            description=description,
        )

    def upsert_promise(self, user_id: int, promise: Promise) -> None:
        user = str(user_id)
        pid = (promise.id or "").strip().upper()
        if not pid:
            raise ValueError("Promise.id is required")

        now = utc_now_iso()
        with get_db_session() as session:
            p_uuid = resolve_promise_uuid(session, user, pid)
            # Optional explicit rename support: callers may set `promise.old_id`
            # to indicate this upsert should target an existing promise.
            if not p_uuid:
                old_id = getattr(promise, "old_id", None)
                old_id = (old_id or "").strip().upper()
                if old_id and old_id != pid:
                    p_uuid = resolve_promise_uuid(session, user, old_id)
            existing = None
            if p_uuid:
                existing = session.execute(
                    text("SELECT current_id, is_deleted FROM promises WHERE user_id = :user_id AND promise_uuid = :p_uuid LIMIT 1;"),
                    {"user_id": user, "p_uuid": p_uuid},
                ).mappings().fetchone()
            is_new = not bool(existing)
            if is_new:
                p_uuid = str(uuid.uuid4())

            # If renaming current_id, ensure uniqueness and keep old id as alias
            event_type = "create" if is_new else "update"
            if existing and str(existing["current_id"]) != pid:
                # Ensure no other promise already uses the new current_id
                clash = session.execute(
                    text("""
                        SELECT promise_uuid FROM promises
                        WHERE user_id = :user_id AND current_id = :pid AND promise_uuid <> :p_uuid
                        LIMIT 1;
                    """),
                    {"user_id": user, "pid": pid, "p_uuid": p_uuid},
                ).fetchone()
                if clash:
                    raise ValueError(f"Promise ID '{pid}' is already in use.")

                # Keep old ID as an alias indefinitely
                old_id = str(existing["current_id"])
                session.execute(
                    text("""
                        INSERT INTO promise_aliases(user_id, alias_id, promise_uuid, created_at_utc)
                        VALUES (:user_id, :old_id, :p_uuid, :now)
                        ON CONFLICT (user_id, alias_id) DO NOTHING;
                    """),
                    {"user_id": user, "old_id": old_id, "p_uuid": p_uuid, "now": now},
                )
                # Also ensure the new ID is registered as an alias
                session.execute(
                    text("""
                        INSERT INTO promise_aliases(user_id, alias_id, promise_uuid, created_at_utc)
                        VALUES (:user_id, :pid, :p_uuid, :now)
                        ON CONFLICT (user_id, alias_id) DO NOTHING;
                    """),
                    {"user_id": user, "pid": pid, "p_uuid": p_uuid, "now": now},
                )
                event_type = "rename"

            session.execute(
                text("""
                    INSERT INTO promises(
                        promise_uuid, user_id, current_id, text, hours_per_week, recurring,
                        start_date, end_date, is_deleted, visibility, description,
                        created_at_utc, updated_at_utc
                    ) VALUES (
                        :p_uuid, :user_id, :pid, :text, :hours_per_week, :recurring,
                        :start_date, :end_date, :is_deleted, :visibility, :description,
                        :created_at_utc, :updated_at_utc
                    )
                    ON CONFLICT (promise_uuid) DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        current_id = EXCLUDED.current_id,
                        text = EXCLUDED.text,
                        hours_per_week = EXCLUDED.hours_per_week,
                        recurring = EXCLUDED.recurring,
                        start_date = EXCLUDED.start_date,
                        end_date = EXCLUDED.end_date,
                        is_deleted = EXCLUDED.is_deleted,
                        visibility = EXCLUDED.visibility,
                        description = EXCLUDED.description,
                        updated_at_utc = EXCLUDED.updated_at_utc;
                """),
                {
                    "p_uuid": p_uuid,
                    "user_id": user,
                    "pid": pid,
                    "text": promise.text or "",
                    "hours_per_week": float(promise.hours_per_week or 0.0),
                    "recurring": 1 if bool(promise.recurring) else 0,
                    "start_date": date_to_iso(promise.start_date),
                    "end_date": date_to_iso(promise.end_date),
                    "is_deleted": 0,
                    "visibility": str(promise.visibility or "private"),
                    "description": promise.description or None,
                    "created_at_utc": now if is_new else now,
                    "updated_at_utc": now,
                },
            )

            # Ensure current id is an alias too
            session.execute(
                text("""
                    INSERT INTO promise_aliases(user_id, alias_id, promise_uuid, created_at_utc)
                    VALUES (:user_id, :pid, :p_uuid, :now)
                    ON CONFLICT (user_id, alias_id) DO NOTHING;
                """),
                {"user_id": user, "pid": pid, "p_uuid": p_uuid, "now": now},
            )

            # Create snapshot without angle_deg and radius
            promise_dict = {
                "user_id": promise.user_id,
                "id": pid,
                "text": promise.text,
                "hours_per_week": promise.hours_per_week,
                "recurring": promise.recurring,
                "start_date": date_to_iso(promise.start_date) if promise.start_date else None,
                "end_date": date_to_iso(promise.end_date) if promise.end_date else None,
                "visibility": promise.visibility,
                "description": promise.description,
                "is_deleted": False,
            }
            snapshot = json.dumps(promise_dict, ensure_ascii=False)
            session.execute(
                text("""
                    INSERT INTO promise_events(event_uuid, promise_uuid, user_id, event_type, at_utc, snapshot_json)
                    VALUES (:event_uuid, :p_uuid, :user_id, :event_type, :now, :snapshot);
                """),
                {
                    "event_uuid": str(uuid.uuid4()),
                    "p_uuid": p_uuid,
                    "user_id": user,
                    "event_type": event_type,
                    "now": now,
                    "snapshot": snapshot,
                },
            )

    def delete_promise(self, user_id: int, promise_id: str) -> bool:
        user = str(user_id)
        pid = (promise_id or "").strip().upper()
        if not pid:
            return False

        now = utc_now_iso()
        with get_db_session() as session:
            p_uuid = resolve_promise_uuid(session, user, pid)
            if not p_uuid:
                return False

            row = session.execute(
                text("""
                    SELECT current_id, text, hours_per_week, recurring, start_date, end_date, is_deleted
                    FROM promises WHERE user_id = :user_id AND promise_uuid = :p_uuid LIMIT 1;
                """),
                {"user_id": user, "p_uuid": p_uuid},
            ).mappings().fetchone()
            if not row or int(row["is_deleted"]) == 1:
                return False

            session.execute(
                text("UPDATE promises SET is_deleted = 1, updated_at_utc = :now WHERE user_id = :user_id AND promise_uuid = :p_uuid;"),
                {"now": now, "user_id": user, "p_uuid": p_uuid},
            )

            snapshot = json.dumps(
                {
                    "id": str(row["current_id"]),
                    "text": str(row["text"]),
                    "hours_per_week": float(row["hours_per_week"]),
                    "recurring": bool(int(row["recurring"])),
                    "start_date": str(row["start_date"] or ""),
                    "end_date": str(row["end_date"] or ""),
                    "is_deleted": True,
                },
                ensure_ascii=False,
            )
            session.execute(
                text("""
                    INSERT INTO promise_events(event_uuid, promise_uuid, user_id, event_type, at_utc, snapshot_json)
                    VALUES (:event_uuid, :p_uuid, :user_id, :event_type, :now, :snapshot);
                """),
                {
                    "event_uuid": str(uuid.uuid4()),
                    "p_uuid": p_uuid,
                    "user_id": user,
                    "event_type": "delete",
                    "now": now,
                    "snapshot": snapshot,
                },
            )

        return True
