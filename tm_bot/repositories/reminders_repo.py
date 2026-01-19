"""
Repository for promise reminders.
"""
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime, time, timedelta

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso, dt_to_utc_iso


class RemindersRepository:
    """PostgreSQL-backed reminders repository."""

    def __init__(self, root_dir: str = None):
        self.root_dir = root_dir

    def list_reminders(self, promise_uuid: str, enabled: Optional[bool] = None) -> List[Dict[str, Any]]:
        """List reminders for a promise."""
        with get_db_session() as session:
            conditions = ["promise_uuid = :promise_uuid"]
            params = {"promise_uuid": promise_uuid}
            
            if enabled is not None:
                conditions.append("enabled = :enabled")
                params["enabled"] = 1 if enabled else 0

            where_clause = " AND ".join(conditions)
            rows = session.execute(
                text(f"""
                    SELECT reminder_id, promise_uuid, slot_id, kind, offset_minutes,
                           weekday, time_local, tz, enabled, last_sent_at_utc,
                           next_run_at_utc, created_at_utc, updated_at_utc
                    FROM promise_reminders
                    WHERE {where_clause}
                    ORDER BY kind, weekday, time_local;
                """),
                params,
            ).fetchall()

        return [dict(row._mapping) for row in rows]

    def get_reminder(self, reminder_id: str) -> Optional[Dict[str, Any]]:
        """Get a single reminder by ID."""
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT reminder_id, promise_uuid, slot_id, kind, offset_minutes,
                           weekday, time_local, tz, enabled, last_sent_at_utc,
                           next_run_at_utc, created_at_utc, updated_at_utc
                    FROM promise_reminders
                    WHERE reminder_id = :reminder_id
                    LIMIT 1;
                """),
                {"reminder_id": reminder_id},
            ).fetchone()

        return dict(row._mapping) if row else None

    def create_reminder(self, reminder_data: Dict[str, Any]) -> str:
        """Create a new reminder. Returns the reminder_id."""
        reminder_id = reminder_data.get("reminder_id") or str(uuid.uuid4())
        now = utc_now_iso()
        
        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO promise_reminders (
                        reminder_id, promise_uuid, slot_id, kind, offset_minutes,
                        weekday, time_local, tz, enabled, last_sent_at_utc,
                        next_run_at_utc, created_at_utc, updated_at_utc
                    ) VALUES (
                        :reminder_id, :promise_uuid, :slot_id, :kind, :offset_minutes,
                        :weekday, :time_local, :tz, :enabled, :last_sent_at_utc,
                        :next_run_at_utc, :created_at_utc, :updated_at_utc
                    )
                """),
                {
                    "reminder_id": reminder_id,
                    "promise_uuid": reminder_data["promise_uuid"],
                    "slot_id": reminder_data.get("slot_id"),
                    "kind": reminder_data["kind"],
                    "offset_minutes": reminder_data.get("offset_minutes"),
                    "weekday": reminder_data.get("weekday"),
                    "time_local": reminder_data["time_local"].isoformat() if reminder_data.get("time_local") and isinstance(reminder_data["time_local"], time) else reminder_data.get("time_local"),
                    "tz": reminder_data.get("tz"),
                    "enabled": 1 if reminder_data.get("enabled", True) else 0,
                    "last_sent_at_utc": reminder_data.get("last_sent_at_utc"),
                    "next_run_at_utc": reminder_data.get("next_run_at_utc"),
                    "created_at_utc": now,
                    "updated_at_utc": now,
                },
            )
        
        return reminder_id

    def update_reminder(self, reminder_id: str, reminder_data: Dict[str, Any]) -> bool:
        """Update an existing reminder. Returns True if updated."""
        now = utc_now_iso()
        
        with get_db_session() as session:
            updates = []
            params = {}
            
            allowed_fields = ["slot_id", "kind", "offset_minutes", "weekday", "time_local", "tz", "enabled", "last_sent_at_utc", "next_run_at_utc"]
            
            for field in allowed_fields:
                if field in reminder_data:
                    if field == "time_local" and isinstance(reminder_data[field], time):
                        updates.append(f"{field} = :{field}")
                        params[field] = reminder_data[field].isoformat()
                    else:
                        updates.append(f"{field} = :{field}")
                        params[field] = reminder_data[field]
            
            if not updates:
                return False
            
            updates.append("updated_at_utc = :updated_at_utc")
            params["updated_at_utc"] = now
            params["reminder_id"] = reminder_id
            
            result = session.execute(
                text(f"""
                    UPDATE promise_reminders
                    SET {", ".join(updates)}
                    WHERE reminder_id = :reminder_id
                """),
                params,
            )
            
            return result.rowcount > 0

    def delete_reminder(self, reminder_id: str) -> bool:
        """Delete a reminder. Returns True if deleted."""
        with get_db_session() as session:
            result = session.execute(
                text("DELETE FROM promise_reminders WHERE reminder_id = :reminder_id"),
                {"reminder_id": reminder_id},
            )
            return result.rowcount > 0

    def replace_reminders(self, promise_uuid: str, reminders: List[Dict[str, Any]]) -> None:
        """Replace all reminders for a promise (delete existing, create new)."""
        with get_db_session() as session:
            # Delete existing reminders
            session.execute(
                text("DELETE FROM promise_reminders WHERE promise_uuid = :promise_uuid"),
                {"promise_uuid": promise_uuid},
            )
            
            # Create new reminders
            now = utc_now_iso()
            for reminder_data in reminders:
                reminder_id = reminder_data.get("reminder_id") or str(uuid.uuid4())
                session.execute(
                    text("""
                        INSERT INTO promise_reminders (
                            reminder_id, promise_uuid, slot_id, kind, offset_minutes,
                            weekday, time_local, tz, enabled, last_sent_at_utc,
                            next_run_at_utc, created_at_utc, updated_at_utc
                        ) VALUES (
                            :reminder_id, :promise_uuid, :slot_id, :kind, :offset_minutes,
                            :weekday, :time_local, :tz, :enabled, :last_sent_at_utc,
                            :next_run_at_utc, :created_at_utc, :updated_at_utc
                        )
                    """),
                    {
                        "reminder_id": reminder_id,
                        "promise_uuid": promise_uuid,
                        "slot_id": reminder_data.get("slot_id"),
                        "kind": reminder_data["kind"],
                        "offset_minutes": reminder_data.get("offset_minutes"),
                        "weekday": reminder_data.get("weekday"),
                        "time_local": reminder_data["time_local"].isoformat() if reminder_data.get("time_local") and isinstance(reminder_data["time_local"], time) else reminder_data.get("time_local"),
                        "tz": reminder_data.get("tz"),
                        "enabled": 1 if reminder_data.get("enabled", True) else 0,
                        "last_sent_at_utc": reminder_data.get("last_sent_at_utc"),
                        "next_run_at_utc": reminder_data.get("next_run_at_utc"),
                        "created_at_utc": now,
                        "updated_at_utc": now,
                    },
                )

    def get_due_reminders(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get reminders that are due (next_run_at_utc <= now)."""
        now = utc_now_iso()
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT reminder_id, promise_uuid, slot_id, kind, offset_minutes,
                           weekday, time_local, tz, enabled, last_sent_at_utc,
                           next_run_at_utc, created_at_utc, updated_at_utc
                    FROM promise_reminders
                    WHERE enabled = 1
                      AND next_run_at_utc IS NOT NULL
                      AND next_run_at_utc <= :now
                    ORDER BY next_run_at_utc ASC
                    LIMIT :limit
                """),
                {"now": now, "limit": limit},
            ).fetchall()

        return [dict(row._mapping) for row in rows]
