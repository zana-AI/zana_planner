"""
Repository for distraction events (for budget templates).
"""
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime

from db.sqlite_db import connection_for_root, utc_now_iso, dt_to_utc_iso, dt_from_utc_iso


class DistractionsRepository:
    """SQLite-backed distractions repository."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def log_distraction(
        self, user_id: int, category: str, minutes: float, at: Optional[datetime] = None
    ) -> str:
        """Log a distraction event. Returns event_uuid."""
        user = str(user_id)
        event_uuid = str(uuid.uuid4())
        now = utc_now_iso()
        at_utc = dt_to_utc_iso(at, assume_local_tz=True) if at else now

        with connection_for_root(self.root_dir) as conn:
            conn.execute(
                """
                INSERT INTO distraction_events (
                    event_uuid, user_id, category, minutes, at_utc, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (event_uuid, user, category, minutes, at_utc, now),
            )

        return event_uuid

    def get_weekly_distractions(
        self, user_id: int, week_start: datetime, week_end: datetime, category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get total distraction minutes for a week, optionally filtered by category."""
        user = str(user_id)
        week_start_utc = dt_to_utc_iso(week_start)
        week_end_utc = dt_to_utc_iso(week_end)

        with connection_for_root(self.root_dir) as conn:
            if category:
                rows = conn.execute(
                    """
                    SELECT SUM(minutes) as total_minutes, COUNT(*) as event_count
                    FROM distraction_events
                    WHERE user_id = ? AND category = ? AND at_utc >= ? AND at_utc <= ?
                    """,
                    (user, category, week_start_utc, week_end_utc),
                ).fetchone()
            else:
                rows = conn.execute(
                    """
                    SELECT SUM(minutes) as total_minutes, COUNT(*) as event_count
                    FROM distraction_events
                    WHERE user_id = ? AND at_utc >= ? AND at_utc <= ?
                    """,
                    (user, week_start_utc, week_end_utc),
                ).fetchone()

        total_minutes = float(rows["total_minutes"] or 0) if rows else 0.0
        event_count = int(rows["event_count"] or 0) if rows else 0

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

        with connection_for_root(self.root_dir) as conn:
            if since_utc:
                rows = conn.execute(
                    """
                    SELECT event_uuid, user_id, category, minutes, at_utc, created_at_utc
                    FROM distraction_events
                    WHERE user_id = ? AND at_utc >= ?
                    ORDER BY at_utc DESC
                    LIMIT ?;
                    """,
                    (user, since_utc, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT event_uuid, user_id, category, minutes, at_utc, created_at_utc
                    FROM distraction_events
                    WHERE user_id = ?
                    ORDER BY at_utc DESC
                    LIMIT ?;
                    """,
                    (user, limit),
                ).fetchall()

        return [dict(row) for row in rows]

