"""
Repository for distraction events (for budget templates).
"""
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso, dt_to_utc_iso, dt_from_utc_iso


class DistractionsRepository:
    """PostgreSQL-backed distractions repository."""

    def __init__(self, root_dir: str = None):
        # root_dir kept for backward compatibility but not used for PostgreSQL
        self.root_dir = root_dir

    def log_distraction(
        self, user_id: int, category: str, minutes: float, at: Optional[datetime] = None
    ) -> str:
        """Log a distraction event. Returns event_uuid."""
        user = str(user_id)
        event_uuid = str(uuid.uuid4())
        now = utc_now_iso()
        at_utc = dt_to_utc_iso(at, assume_local_tz=True) if at else now

        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO distraction_events (
                        event_uuid, user_id, category, minutes, at_utc, created_at_utc
                    ) VALUES (:event_uuid, :user_id, :category, :minutes, :at_utc, :created_at_utc);
                """),
                {
                    "event_uuid": event_uuid,
                    "user_id": user,
                    "category": category,
                    "minutes": minutes,
                    "at_utc": at_utc,
                    "created_at_utc": now,
                },
            )

        return event_uuid

    def get_weekly_distractions(
        self, user_id: int, week_start: datetime, week_end: datetime, category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get total distraction minutes for a week, optionally filtered by category."""
        user = str(user_id)
        week_start_utc = dt_to_utc_iso(week_start)
        week_end_utc = dt_to_utc_iso(week_end)

        with get_db_session() as session:
            if category:
                row = session.execute(
                    text("""
                        SELECT SUM(minutes) as total_minutes, COUNT(*) as event_count
                        FROM distraction_events
                        WHERE user_id = :user_id AND category = :category AND at_utc >= :week_start_utc AND at_utc <= :week_end_utc
                    """),
                    {"user_id": user, "category": category, "week_start_utc": week_start_utc, "week_end_utc": week_end_utc},
                ).fetchone()
            else:
                row = session.execute(
                    text("""
                        SELECT SUM(minutes) as total_minutes, COUNT(*) as event_count
                        FROM distraction_events
                        WHERE user_id = :user_id AND at_utc >= :week_start_utc AND at_utc <= :week_end_utc
                    """),
                    {"user_id": user, "week_start_utc": week_start_utc, "week_end_utc": week_end_utc},
                ).fetchone()

        total_minutes = float(row[0] or 0) if row and row[0] else 0.0
        event_count = int(row[1] or 0) if row and row[1] else 0

        return {
            "total_minutes": total_minutes,
            "total_hours": total_minutes / 60.0,
            "event_count": event_count,
        }

    def list_distractions(
        self, user_id: int, since: Optional[datetime] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List recent distraction events."""
        user = str(user_id)
        since_utc = dt_to_utc_iso(since, assume_local_tz=True) if since else None

        with get_db_session() as session:
            if since_utc:
                rows = session.execute(
                    text("""
                        SELECT event_uuid, user_id, category, minutes, at_utc, created_at_utc
                        FROM distraction_events
                        WHERE user_id = :user_id AND at_utc >= :since_utc
                        ORDER BY at_utc DESC
                        LIMIT :limit;
                    """),
                    {"user_id": user, "since_utc": since_utc, "limit": limit},
                ).fetchall()
            else:
                rows = session.execute(
                    text("""
                        SELECT event_uuid, user_id, category, minutes, at_utc, created_at_utc
                        FROM distraction_events
                        WHERE user_id = :user_id
                        ORDER BY at_utc DESC
                        LIMIT :limit;
                    """),
                    {"user_id": user, "limit": limit},
                ).fetchall()

        return [dict(row._mapping) for row in rows]

