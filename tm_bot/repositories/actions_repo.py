import uuid
from datetime import date, datetime
from typing import List, Optional

import pandas as pd
from sqlalchemy import text

from db.postgres_db import (
    get_db_session,
    dt_to_utc_iso,
    dt_utc_iso_to_local_naive,
    resolve_promise_uuid,
)
from models.models import Action


class ActionsRepository:
    """
    PostgreSQL-backed actions repository.

    Stores timestamps as UTC ISO strings, but returns naive local datetimes for
    backward compatibility with existing code comparisons.
    """

    def __init__(self) -> None:
        pass

    def append_action(self, action: Action) -> None:
        user = str(action.user_id)
        pid = (action.promise_id or "").strip().upper()
        at_utc = dt_to_utc_iso(action.at, assume_local_tz=True) or dt_to_utc_iso(datetime.now(), assume_local_tz=True)
        if not at_utc:
            return

        with get_db_session() as session:
            # Link promise_uuid even for old IDs
            p_uuid = resolve_promise_uuid(session, user, pid) if pid else None

            session.execute(
                text("""
                    INSERT INTO actions(
                        action_uuid, user_id, promise_uuid, promise_id_text,
                        action_type, time_spent_hours, at_utc, notes
                    ) VALUES (:action_uuid, :user_id, :p_uuid, :pid, :action_type, :time_spent, :at_utc, :notes);
                """),
                {
                    "action_uuid": str(uuid.uuid4()),
                    "user_id": user,
                    "p_uuid": p_uuid,
                    "pid": pid or "",
                    "action_type": str(action.action or "log_time"),
                    "time_spent": float(action.time_spent or 0.0),
                    "at_utc": at_utc,
                    "notes": action.notes if action.notes else None,
                },
            )

    def list_actions(self, user_id: int, since: Optional[datetime] = None) -> List[Action]:
        user = str(user_id)
        since_utc = dt_to_utc_iso(since, assume_local_tz=True) if since else None

        with get_db_session() as session:
            if since_utc:
                rows = session.execute(
                    text("""
                        SELECT
                            a.action_type, a.time_spent_hours, a.at_utc, a.notes,
                            COALESCE(p.current_id, a.promise_id_text) AS canonical_promise_id
                        FROM actions a
                        LEFT JOIN promises p ON p.promise_uuid = a.promise_uuid AND p.user_id = a.user_id
                        WHERE a.user_id = :user_id AND a.at_utc >= :since_utc
                        ORDER BY a.at_utc ASC;
                    """),
                    {"user_id": user, "since_utc": since_utc},
                ).mappings().fetchall()
            else:
                rows = session.execute(
                    text("""
                        SELECT
                            a.action_type, a.time_spent_hours, a.at_utc, a.notes,
                            COALESCE(p.current_id, a.promise_id_text) AS canonical_promise_id
                        FROM actions a
                        LEFT JOIN promises p ON p.promise_uuid = a.promise_uuid AND p.user_id = a.user_id
                        WHERE a.user_id = :user_id
                        ORDER BY a.at_utc ASC;
                    """),
                    {"user_id": user},
                ).mappings().fetchall()

        actions: List[Action] = []
        for r in rows:
            at = dt_utc_iso_to_local_naive(r["at_utc"])
            if not at:
                continue
            actions.append(
                Action(
                    user_id=user,
                    promise_id=str(r["canonical_promise_id"] or ""),
                    action=str(r["action_type"] or "log_time"),
                    time_spent=float(r["time_spent_hours"] or 0.0),
                    at=at,
                    notes=r.get("notes") if r.get("notes") else None,
                )
            )
        return actions

    def last_action_for_promise(self, user_id: int, promise_id: str) -> Optional[Action]:
        pid = (promise_id or "").strip().upper()
        if not pid:
            return None
        actions = self.list_actions(user_id)
        ps = [a for a in actions if (a.promise_id or "").strip().upper() == pid]
        return max(ps, key=lambda a: a.at) if ps else None

    def append_club_checkin(self, user_id: int, promise_uuid: str, notes: str | None = None) -> None:
        """Record a club check-in for today (idempotent — replaces any existing one)."""
        user = str(user_id)
        now_dt = datetime.utcnow()
        at_utc = now_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        today = now_dt.strftime("%Y-%m-%d")
        with get_db_session() as session:
            session.execute(
                text("""
                    DELETE FROM actions
                    WHERE user_id = :user_id
                      AND promise_uuid = :promise_uuid
                      AND action_type = 'club_checkin'
                      AND DATE(at_utc) = :today;
                """),
                {"user_id": user, "promise_uuid": promise_uuid, "today": today},
            )
            session.execute(
                text("""
                    INSERT INTO actions(
                        action_uuid, user_id, promise_uuid, promise_id_text,
                        action_type, time_spent_hours, at_utc, notes
                    ) VALUES (
                        :action_uuid, :user_id, :promise_uuid, '',
                        'club_checkin', 0.0, :at_utc, :notes
                    );
                """),
                {
                    "action_uuid": str(uuid.uuid4()),
                    "user_id": user,
                    "promise_uuid": promise_uuid,
                    "at_utc": at_utc,
                    "notes": notes,
                },
            )

    def delete_club_checkin(self, user_id: int, promise_uuid: str) -> None:
        """Remove today's club check-in action."""
        user = str(user_id)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        with get_db_session() as session:
            session.execute(
                text("""
                    DELETE FROM actions
                    WHERE user_id = :user_id
                      AND promise_uuid = :promise_uuid
                      AND action_type = 'club_checkin'
                      AND DATE(at_utc) = :today;
                """),
                {"user_id": user, "promise_uuid": promise_uuid, "today": today},
            )

    def get_today_checkins(self, promise_uuid: str) -> set[str]:
        """Return the set of user_ids (as str) who have a club_checkin action today."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT DISTINCT user_id FROM actions
                    WHERE promise_uuid = :promise_uuid
                      AND action_type = 'club_checkin'
                      AND DATE(at_utc) = :today;
                """),
                {"promise_uuid": promise_uuid, "today": today},
            ).fetchall()
        return {str(row[0]) for row in rows}

    def get_checkin_streak(
        self,
        user_id: int,
        promise_uuid: str,
        freeze_budget: int = 2,
        reference_date: date | datetime | str | None = None,
    ) -> int:
        """
        Count check-in days in the current streak, bridging up to freeze_budget missed days.

        Missed days preserve a streak but never increase it. Today is not treated as
        missed yet, so a streak ending yesterday still displays intact before today's
        member check-in happens.
        """
        user = str(user_id)
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT DISTINCT DATE(at_utc) AS check_date
                    FROM actions
                    WHERE user_id = :user_id
                      AND promise_uuid = :promise_uuid
                      AND action_type = 'club_checkin'
                    ORDER BY check_date DESC;
                """),
                {"user_id": user, "promise_uuid": promise_uuid},
            ).fetchall()

        if not rows:
            return 0

        if isinstance(reference_date, datetime):
            today = reference_date.date()
        elif isinstance(reference_date, date):
            today = reference_date
        elif isinstance(reference_date, str):
            today = date.fromisoformat(reference_date[:10])
        else:
            today = datetime.utcnow().date()

        dates = []
        for row in rows:
            d = row[0]
            if isinstance(d, datetime):
                d = d.date()
            if isinstance(d, str):
                d = date.fromisoformat(d)
            if d <= today:
                dates.append(d)

        dates = sorted(set(dates), reverse=True)
        if not dates:
            return 0

        try:
            freezes_remaining = max(0, int(freeze_budget))
        except (TypeError, ValueError):
            freezes_remaining = 2

        latest = dates[0]
        initial_missed_days = max(0, (today - latest).days - 1)
        if initial_missed_days > freezes_remaining:
            return 0

        freezes_remaining -= initial_missed_days
        streak = 1
        previous = latest
        for i in range(1, len(dates)):
            missed_days = max(0, (previous - dates[i]).days - 1)
            if missed_days > freezes_remaining:
                break
            freezes_remaining -= missed_days
            streak += 1
            previous = dates[i]
        return streak

    def get_actions_df(self, user_id: int) -> pd.DataFrame:
        """
        Return DataFrame with legacy columns: ['date','time','promise_id','time_spent'].
        If pandas is unavailable, returns a list-of-dicts compatible with .to_dict().
        """
        actions = self.list_actions(user_id)
        rows = [
            {
                "date": a.at.strftime("%Y-%m-%d"),
                "time": a.at.strftime("%H:%M"),
                "promise_id": a.promise_id,
                "time_spent": float(a.time_spent or 0.0),
            }
            for a in actions
        ]

        return pd.DataFrame(rows, columns=["date", "time", "promise_id", "time_spent"])
