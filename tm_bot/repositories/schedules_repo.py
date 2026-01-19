"""
Repository for promise schedule weekly slots.
"""
import uuid
from typing import List, Optional, Dict, Any
from datetime import date, time

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso, date_from_iso, date_to_iso


class SchedulesRepository:
    """PostgreSQL-backed schedules repository."""

    def __init__(self, root_dir: str = None):
        self.root_dir = root_dir

    def list_slots(self, promise_uuid: str, is_active: Optional[bool] = True) -> List[Dict[str, Any]]:
        """List schedule slots for a promise."""
        with get_db_session() as session:
            conditions = ["promise_uuid = :promise_uuid"]
            params = {"promise_uuid": promise_uuid}
            
            if is_active is not None:
                conditions.append("is_active = :is_active")
                params["is_active"] = 1 if is_active else 0

            where_clause = " AND ".join(conditions)
            rows = session.execute(
                text(f"""
                    SELECT slot_id, promise_uuid, weekday, start_local_time, end_local_time,
                           tz, start_date, end_date, is_active, created_at_utc, updated_at_utc
                    FROM promise_schedule_weekly_slots
                    WHERE {where_clause}
                    ORDER BY weekday, start_local_time;
                """),
                params,
            ).fetchall()

        return [dict(row._mapping) for row in rows]

    def get_slot(self, slot_id: str) -> Optional[Dict[str, Any]]:
        """Get a single slot by ID."""
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT slot_id, promise_uuid, weekday, start_local_time, end_local_time,
                           tz, start_date, end_date, is_active, created_at_utc, updated_at_utc
                    FROM promise_schedule_weekly_slots
                    WHERE slot_id = :slot_id
                    LIMIT 1;
                """),
                {"slot_id": slot_id},
            ).fetchone()

        return dict(row._mapping) if row else None

    def create_slot(self, slot_data: Dict[str, Any]) -> str:
        """Create a new schedule slot. Returns the slot_id."""
        slot_id = slot_data.get("slot_id") or str(uuid.uuid4())
        now = utc_now_iso()
        
        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO promise_schedule_weekly_slots (
                        slot_id, promise_uuid, weekday, start_local_time, end_local_time,
                        tz, start_date, end_date, is_active, created_at_utc, updated_at_utc
                    ) VALUES (
                        :slot_id, :promise_uuid, :weekday, :start_local_time, :end_local_time,
                        :tz, :start_date, :end_date, :is_active, :created_at_utc, :updated_at_utc
                    )
                """),
                {
                    "slot_id": slot_id,
                    "promise_uuid": slot_data["promise_uuid"],
                    "weekday": slot_data["weekday"],
                    "start_local_time": slot_data["start_local_time"].isoformat() if isinstance(slot_data["start_local_time"], time) else slot_data["start_local_time"],
                    "end_local_time": slot_data["end_local_time"].isoformat() if slot_data.get("end_local_time") and isinstance(slot_data["end_local_time"], time) else (date_to_iso(slot_data["end_local_time"]) if slot_data.get("end_local_time") else None),
                    "tz": slot_data.get("tz"),
                    "start_date": date_to_iso(slot_data["start_date"]) if slot_data.get("start_date") else None,
                    "end_date": date_to_iso(slot_data["end_date"]) if slot_data.get("end_date") else None,
                    "is_active": 1 if slot_data.get("is_active", True) else 0,
                    "created_at_utc": now,
                    "updated_at_utc": now,
                },
            )
        
        return slot_id

    def update_slot(self, slot_id: str, slot_data: Dict[str, Any]) -> bool:
        """Update an existing slot. Returns True if updated."""
        now = utc_now_iso()
        
        with get_db_session() as session:
            updates = []
            params = {}
            
            allowed_fields = ["weekday", "start_local_time", "end_local_time", "tz", "start_date", "end_date", "is_active"]
            
            for field in allowed_fields:
                if field in slot_data:
                    if field in ["start_local_time", "end_local_time"] and isinstance(slot_data[field], time):
                        updates.append(f"{field} = :{field}")
                        params[field] = slot_data[field].isoformat()
                    elif field in ["start_date", "end_date"] and slot_data[field]:
                        updates.append(f"{field} = :{field}")
                        params[field] = date_to_iso(slot_data[field])
                    else:
                        updates.append(f"{field} = :{field}")
                        params[field] = slot_data[field]
            
            if not updates:
                return False
            
            updates.append("updated_at_utc = :updated_at_utc")
            params["updated_at_utc"] = now
            params["slot_id"] = slot_id
            
            result = session.execute(
                text(f"""
                    UPDATE promise_schedule_weekly_slots
                    SET {", ".join(updates)}
                    WHERE slot_id = :slot_id
                """),
                params,
            )
            
            return result.rowcount > 0

    def delete_slot(self, slot_id: str) -> bool:
        """Delete a schedule slot. Returns True if deleted."""
        with get_db_session() as session:
            result = session.execute(
                text("DELETE FROM promise_schedule_weekly_slots WHERE slot_id = :slot_id"),
                {"slot_id": slot_id},
            )
            return result.rowcount > 0

    def replace_slots(self, promise_uuid: str, slots: List[Dict[str, Any]]) -> None:
        """Replace all slots for a promise (delete existing, create new)."""
        with get_db_session() as session:
            # Delete existing slots
            session.execute(
                text("DELETE FROM promise_schedule_weekly_slots WHERE promise_uuid = :promise_uuid"),
                {"promise_uuid": promise_uuid},
            )
            
            # Create new slots
            now = utc_now_iso()
            for slot_data in slots:
                slot_id = slot_data.get("slot_id") or str(uuid.uuid4())
                session.execute(
                    text("""
                        INSERT INTO promise_schedule_weekly_slots (
                            slot_id, promise_uuid, weekday, start_local_time, end_local_time,
                            tz, start_date, end_date, is_active, created_at_utc, updated_at_utc
                        ) VALUES (
                            :slot_id, :promise_uuid, :weekday, :start_local_time, :end_local_time,
                            :tz, :start_date, :end_date, :is_active, :created_at_utc, :updated_at_utc
                        )
                    """),
                    {
                        "slot_id": slot_id,
                        "promise_uuid": promise_uuid,
                        "weekday": slot_data["weekday"],
                        "start_local_time": slot_data["start_local_time"].isoformat() if isinstance(slot_data["start_local_time"], time) else slot_data["start_local_time"],
                        "end_local_time": slot_data["end_local_time"].isoformat() if slot_data.get("end_local_time") and isinstance(slot_data["end_local_time"], time) else None,
                        "tz": slot_data.get("tz"),
                        "start_date": date_to_iso(slot_data["start_date"]) if slot_data.get("start_date") else None,
                        "end_date": date_to_iso(slot_data["end_date"]) if slot_data.get("end_date") else None,
                        "is_active": 1 if slot_data.get("is_active", True) else 0,
                        "created_at_utc": now,
                        "updated_at_utc": now,
                    },
                )
