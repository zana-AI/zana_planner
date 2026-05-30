"""
Repository for plan_sessions and checklist_items tables.
Follows the existing raw-SQL + get_db_session() pattern.
"""
from typing import List, Optional

from sqlalchemy import text

from db.postgres_db import get_db_session, resolve_promise_uuid, utc_now_iso


PLAN_SESSION_SELECT = """
    id, promise_uuid, user_id, title, status, planned_start,
    planned_duration_min, notes, content_id, created_at, notified_at,
    reminder_enabled, reminder_offset_min
"""


def _row_to_dict(row) -> dict:
    data = dict(row)
    data["reminder_enabled"] = bool(data.get("reminder_enabled", True))
    if data.get("reminder_offset_min") is None:
        data["reminder_offset_min"] = 10
    return data


class PlanSessionsRepository:

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def list_for_promise(self, promise_uuid: str, user_id: int) -> List[dict]:
        user = str(user_id)
        with get_db_session() as session:
            rows = session.execute(
                text(f"""
                    SELECT {PLAN_SESSION_SELECT}
                    FROM plan_sessions
                    WHERE promise_uuid = :promise_uuid AND user_id = :user_id
                    ORDER BY planned_start NULLS LAST, created_at
                """),
                {"promise_uuid": promise_uuid, "user_id": user},
            ).mappings().fetchall()

            results = []
            for r in rows:
                checklist = self._get_checklist(session, r["id"])
                results.append({**_row_to_dict(r), "checklist": checklist})
            return results

    def create(self, promise_uuid: str, user_id: int, data: dict) -> dict:
        user = str(user_id)
        checklist_data = data.pop("checklist", [])
        reminder_enabled = data.get("reminder_enabled", True)
        reminder_offset_min = data.get("reminder_offset_min", 10)
        with get_db_session() as session:
            result = session.execute(
                text("""
                    INSERT INTO plan_sessions
                        (promise_uuid, user_id, title, status, planned_start,
                         planned_duration_min, notes, content_id, created_at,
                         reminder_enabled, reminder_offset_min)
                    VALUES
                        (:promise_uuid, :user_id, :title, 'planned', :planned_start,
                         :planned_duration_min, :notes, :content_id, :created_at,
                         :reminder_enabled, :reminder_offset_min)
                    RETURNING id, promise_uuid, user_id, title, status, planned_start,
                              planned_duration_min, notes, content_id, created_at,
                              notified_at, reminder_enabled, reminder_offset_min
                """),
                {
                    "promise_uuid": promise_uuid,
                    "user_id": user,
                    "title": data.get("title"),
                    "planned_start": data.get("planned_start"),
                    "planned_duration_min": data.get("planned_duration_min"),
                    "notes": data.get("notes"),
                    "content_id": data.get("content_id"),
                    "created_at": utc_now_iso(),
                    "reminder_enabled": 1 if reminder_enabled else 0,
                    "reminder_offset_min": int(reminder_offset_min),
                },
            ).mappings().fetchone()

            session_id = result["id"]
            for i, item in enumerate(checklist_data):
                session.execute(
                    text("""
                        INSERT INTO checklist_items (session_id, text, done, position)
                        VALUES (:session_id, :text, :done, :position)
                    """),
                    {
                        "session_id": session_id,
                        "text": item["text"],
                        "done": int(item.get("done", False)),
                        "position": i,
                    },
                )
            checklist = self._get_checklist(session, session_id)
            return {**_row_to_dict(result), "checklist": checklist}

    def find_for_content(self, promise_uuid: str, user_id: int, content_id: str) -> Optional[dict]:
        """Return an existing session linking this content to this promise, or None.

        Used to avoid creating duplicate watch/read sessions when content is
        re-assigned to the same promise.
        """
        user = str(user_id)
        with get_db_session() as session:
            row = session.execute(
                text(f"""
                    SELECT {PLAN_SESSION_SELECT}
                    FROM plan_sessions
                    WHERE promise_uuid = :promise_uuid
                      AND user_id = :user_id
                      AND content_id = :content_id
                    ORDER BY created_at
                    LIMIT 1
                """),
                {"promise_uuid": promise_uuid, "user_id": user, "content_id": content_id},
            ).mappings().fetchone()
            return _row_to_dict(row) if row else None

    def get(self, session_id: int, user_id: int) -> Optional[dict]:
        user = str(user_id)
        with get_db_session() as session:
            row = session.execute(
                text(f"""
                    SELECT {PLAN_SESSION_SELECT}
                    FROM plan_sessions
                    WHERE id = :session_id AND user_id = :user_id
                """),
                {"session_id": session_id, "user_id": user},
            ).mappings().fetchone()
            if not row:
                return None
            checklist = self._get_checklist(session, row["id"])
            return {**_row_to_dict(row), "checklist": checklist}

    def update_status(self, session_id: int, user_id: int, status: str) -> Optional[dict]:
        user = str(user_id)
        with get_db_session() as session:
            result = session.execute(
                text(f"""
                    UPDATE plan_sessions SET status = :status
                    WHERE id = :session_id AND user_id = :user_id
                    RETURNING {PLAN_SESSION_SELECT}
                """),
                {"status": status, "session_id": session_id, "user_id": user},
            ).mappings().fetchone()
            if not result:
                return None
            checklist = self._get_checklist(session, result["id"])
            return {**_row_to_dict(result), "checklist": checklist}

    def delete(self, session_id: int, user_id: int) -> bool:
        user = str(user_id)
        with get_db_session() as session:
            result = session.execute(
                text("DELETE FROM plan_sessions WHERE id = :session_id AND user_id = :user_id"),
                {"session_id": session_id, "user_id": user},
            )
            return result.rowcount > 0

    def update(self, session_id: int, user_id: int, data: dict) -> Optional[dict]:
        """Patch mutable fields for a planned session."""
        user = str(user_id)
        allowed = {
            "title",
            "planned_start",
            "planned_duration_min",
            "notes",
            "reminder_enabled",
            "reminder_offset_min",
        }
        fields = {k: v for k, v in data.items() if k in allowed}
        if not fields:
            return self.get(session_id, int(user_id))
        if "reminder_enabled" in fields:
            fields["reminder_enabled"] = 1 if fields["reminder_enabled"] else 0
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        if "planned_start" in fields or "reminder_offset_min" in fields or "reminder_enabled" in fields:
            set_clause += ", notified_at = NULL"
        params = {**fields, "session_id": session_id, "user_id": user}
        with get_db_session() as session:
            result = session.execute(
                text(f"""
                    UPDATE plan_sessions SET {set_clause}
                    WHERE id = :session_id AND user_id = :user_id
                    RETURNING {PLAN_SESSION_SELECT}
                """),
                params,
            ).mappings().fetchone()
            if not result:
                return None
            checklist = self._get_checklist(session, result["id"])
            return {**_row_to_dict(result), "checklist": checklist}

    # ------------------------------------------------------------------
    # Checklist items
    # ------------------------------------------------------------------

    def toggle_checklist_item(self, item_id: int, session_id: int, user_id: int, done: bool) -> Optional[dict]:
        user = str(user_id)
        with get_db_session() as session:
            # Verify the session belongs to this user
            owner = session.execute(
                text("SELECT id FROM plan_sessions WHERE id = :sid AND user_id = :uid"),
                {"sid": session_id, "uid": user},
            ).fetchone()
            if not owner:
                return None
            session.execute(
                text("""
                    UPDATE checklist_items SET done = :done
                    WHERE id = :item_id AND session_id = :session_id
                """),
                {"done": int(done), "item_id": item_id, "session_id": session_id},
            )
        # Re-fetch with a fresh session (get_db_session commits on exit)
        return self.get(session_id, user_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def list_sessions_needing_reminder(self, lookahead_minutes: int = 1) -> List[dict]:
        """Find planned sessions whose reminder window is due.

        The reminder time is planned_start minus reminder_offset_min. To avoid
        notifying for very stale sessions, ignore sessions whose planned_start is
        more than 30 minutes in the past.
        """
        from datetime import datetime, timedelta, timezone

        now_utc = datetime.now(timezone.utc).replace(microsecond=0)
        lower_bound = (now_utc - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
        max_upper_bound = (now_utc + timedelta(minutes=1440 + lookahead_minutes)).isoformat().replace("+00:00", "Z")

        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT ps.id, ps.promise_uuid, ps.user_id, ps.title, ps.status,
                           ps.planned_start, ps.planned_duration_min, ps.notes, ps.content_id,
                           ps.created_at, ps.notified_at, ps.reminder_enabled,
                           ps.reminder_offset_min,
                           p.current_id AS promise_id, p.text AS promise_text
                    FROM plan_sessions ps
                    LEFT JOIN promises p ON p.promise_uuid = ps.promise_uuid
                    WHERE ps.status = 'planned'
                      AND ps.reminder_enabled = 1
                      AND ps.planned_start IS NOT NULL
                      AND ps.planned_start >= :lower_bound
                      AND ps.planned_start <= :max_upper_bound
                      AND ps.notified_at IS NULL
                    ORDER BY ps.planned_start
                """),
                {"lower_bound": lower_bound, "max_upper_bound": max_upper_bound},
            ).mappings().fetchall()

            due = []
            for r in rows:
                data = _row_to_dict(r)
                try:
                    planned_start = datetime.fromisoformat(str(data["planned_start"]).replace("Z", "+00:00"))
                    offset = data.get("reminder_offset_min")
                    reminder_at = planned_start - timedelta(minutes=int(10 if offset is None else offset))
                    if reminder_at <= now_utc + timedelta(minutes=lookahead_minutes):
                        due.append(data)
                except Exception:
                    continue
            return due

    def mark_plan_session_notified(self, session_id: int) -> None:
        """Mark a planned session as notified by setting notified_at to now."""
        with get_db_session() as session:
            session.execute(
                text("""
                    UPDATE plan_sessions
                    SET notified_at = :notified_at
                    WHERE id = :session_id
                """),
                {"session_id": session_id, "notified_at": utc_now_iso()},
            )

    def clear_plan_session_notified(self, session_id: int) -> None:
        """Clear notified_at so a failed reminder can be retried."""
        with get_db_session() as session:
            session.execute(
                text("UPDATE plan_sessions SET notified_at = NULL WHERE id = :session_id"),
                {"session_id": session_id},
            )

    def snooze_plan_session(self, session_id: int, user_id: int, new_planned_start: str) -> Optional[dict]:
        """Update planned_start and reset notified_at so a new reminder will fire."""
        user = str(user_id)
        with get_db_session() as session:
            result = session.execute(
                text(f"""
                    UPDATE plan_sessions
                    SET planned_start = :planned_start, notified_at = NULL, reminder_offset_min = 0
                    WHERE id = :session_id AND user_id = :user_id
                    RETURNING {PLAN_SESSION_SELECT}
                """),
                {"session_id": session_id, "user_id": user, "planned_start": new_planned_start},
            ).mappings().fetchone()
            if not result:
                return None
            checklist = self._get_checklist(session, result["id"])
            return {**_row_to_dict(result), "checklist": checklist}

    def list_planned_by_promise_uuids(self, promise_uuids: List[str], user_id: int) -> dict:
        """Bulk-fetch all planned sessions for a list of promise_uuids, grouped by promise_uuid."""
        if not promise_uuids:
            return {}
        user = str(user_id)
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT id, promise_uuid, title, status,
                           planned_start, planned_duration_min, notes, content_id,
                           created_at, notified_at, reminder_enabled, reminder_offset_min
                    FROM plan_sessions
                    WHERE promise_uuid = ANY(:uuids) AND user_id = :user_id
                      AND status = 'planned'
                    ORDER BY planned_start NULLS LAST, created_at
                """),
                {"uuids": promise_uuids, "user_id": user},
            ).mappings().fetchall()

        result: dict = {}
        for r in rows:
            uuid = r["promise_uuid"]
            if uuid not in result:
                result[uuid] = []
            result[uuid].append(_row_to_dict(r))
        return result

    def list_upcoming_for_user(self, user_id: int, since_iso: str, until_iso: str) -> List[dict]:
        """List all planned sessions for a user between two ISO datetime strings.

        Joins with the promises table to include promise_id and promise_text.
        Only returns sessions with status='planned'.
        """
        user = str(user_id)
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT ps.id, ps.promise_uuid, ps.user_id, ps.title, ps.status,
                           ps.planned_start, ps.planned_duration_min, ps.notes, ps.content_id,
                           ps.created_at, ps.notified_at, ps.reminder_enabled,
                           ps.reminder_offset_min,
                           p.current_id AS promise_id, p.text AS promise_text
                    FROM plan_sessions ps
                    LEFT JOIN promises p ON p.promise_uuid = ps.promise_uuid
                    WHERE ps.user_id = :user_id
                      AND ps.status = 'planned'
                      AND ps.planned_start >= :since_iso
                      AND ps.planned_start <= :until_iso
                    ORDER BY ps.planned_start
                """),
                {"user_id": user, "since_iso": since_iso, "until_iso": until_iso},
            ).mappings().fetchall()
            return [_row_to_dict(r) for r in rows]

    @staticmethod
    def _get_checklist(session, plan_session_id: int) -> List[dict]:
        rows = session.execute(
            text("""
                SELECT id, session_id, text, done, position
                FROM checklist_items
                WHERE session_id = :sid
                ORDER BY position
            """),
            {"sid": plan_session_id},
        ).mappings().fetchall()
        return [
            {
                "id": r["id"],
                "text": r["text"],
                "done": bool(r["done"]),
                "position": r["position"],
            }
            for r in rows
        ]
