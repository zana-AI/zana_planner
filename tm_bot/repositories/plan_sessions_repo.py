"""
Repository for plan_sessions and checklist_items tables.
Follows the existing raw-SQL + get_db_session() pattern.
"""
from typing import List, Optional

from sqlalchemy import text

from db.postgres_db import get_db_session, resolve_promise_uuid, utc_now_iso


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
                text("""
                    SELECT id, promise_uuid, user_id, title, status,
                           planned_start, planned_duration_min, notes, created_at
                    FROM plan_sessions
                    WHERE promise_uuid = :promise_uuid AND user_id = :user_id
                    ORDER BY planned_start NULLS LAST, created_at
                """),
                {"promise_uuid": promise_uuid, "user_id": user},
            ).mappings().fetchall()

            results = []
            for r in rows:
                checklist = self._get_checklist(session, r["id"])
                results.append({**dict(r), "checklist": checklist})
            return results

    def create(self, promise_uuid: str, user_id: int, data: dict) -> dict:
        user = str(user_id)
        checklist_data = data.pop("checklist", [])
        with get_db_session() as session:
            result = session.execute(
                text("""
                    INSERT INTO plan_sessions
                        (promise_uuid, user_id, title, status, planned_start, planned_duration_min, notes, created_at)
                    VALUES
                        (:promise_uuid, :user_id, :title, 'planned', :planned_start, :planned_duration_min, :notes, :created_at)
                    RETURNING id, promise_uuid, user_id, title, status, planned_start, planned_duration_min, notes, created_at
                """),
                {
                    "promise_uuid": promise_uuid,
                    "user_id": user,
                    "title": data.get("title"),
                    "planned_start": data.get("planned_start"),
                    "planned_duration_min": data.get("planned_duration_min"),
                    "notes": data.get("notes"),
                    "created_at": utc_now_iso(),
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
            return {**dict(result), "checklist": checklist}

    def get(self, session_id: int, user_id: int) -> Optional[dict]:
        user = str(user_id)
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT id, promise_uuid, user_id, title, status,
                           planned_start, planned_duration_min, notes, created_at
                    FROM plan_sessions
                    WHERE id = :session_id AND user_id = :user_id
                """),
                {"session_id": session_id, "user_id": user},
            ).mappings().fetchone()
            if not row:
                return None
            checklist = self._get_checklist(session, row["id"])
            return {**dict(row), "checklist": checklist}

    def update_status(self, session_id: int, user_id: int, status: str) -> Optional[dict]:
        user = str(user_id)
        with get_db_session() as session:
            result = session.execute(
                text("""
                    UPDATE plan_sessions SET status = :status
                    WHERE id = :session_id AND user_id = :user_id
                    RETURNING id, promise_uuid, user_id, title, status, planned_start, planned_duration_min, notes, created_at
                """),
                {"status": status, "session_id": session_id, "user_id": user},
            ).mappings().fetchone()
            if not result:
                return None
            checklist = self._get_checklist(session, result["id"])
            return {**dict(result), "checklist": checklist}

    def delete(self, session_id: int, user_id: int) -> bool:
        user = str(user_id)
        with get_db_session() as session:
            result = session.execute(
                text("DELETE FROM plan_sessions WHERE id = :session_id AND user_id = :user_id"),
                {"session_id": session_id, "user_id": user},
            )
            return result.rowcount > 0

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
