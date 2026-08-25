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
                            a.action_type, a.time_spent_hours, a.at_utc, a.notes, a.credits_minutes,
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
                            a.action_type, a.time_spent_hours, a.at_utc, a.notes, a.credits_minutes,
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
                    credits_minutes=float(r["credits_minutes"] or 0.0),
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

    def append_club_checkin(
        self, user_id: int, promise_uuid: str, notes: str | None = None, today: date | None = None
    ) -> None:
        """Record a club check-in for today (idempotent — replaces any existing one).

        `today` lets a caller pass a club-local date (see
        `club_reminder_service.resolve_club_timezone`) instead of the raw
        UTC day; defaults to UTC-now when omitted, preserving old behavior.
        """
        user = str(user_id)
        now_dt = datetime.utcnow()
        at_utc = now_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        today = (today or now_dt.date()).strftime("%Y-%m-%d")
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

    def accumulate_credit(
        self,
        user_id: int | str,
        promise_uuid: str,
        credits_minutes: float,
        source: str = "review",
    ) -> float:
        """Add credit to today's running total for this promise, and return it.

        One row per promise per day per source, incremented — not one row per
        rated card. A review session is dozens of cards; a row each would bury
        the action history under noise and make the weekly report scan hundreds
        of rows to compute one number.

        The day counts as checked once the total passes the threshold in
        services/credits.py, which is why `action_type` is only promoted to
        'club_checkin' at that point: below it the credit is banked but the
        streak has not been earned.
        """
        from services import credits as credit_rules

        user = str(user_id)
        now_dt = datetime.utcnow()
        at_utc = now_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        today = now_dt.strftime("%Y-%m-%d")
        note = f"credit:{source}"

        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT action_uuid, credits_minutes FROM actions
                    WHERE user_id = :user_id
                      AND promise_uuid = :promise_uuid
                      AND DATE(at_utc) = :today
                      AND notes = :note
                    LIMIT 1;
                """),
                {"user_id": user, "promise_uuid": promise_uuid, "today": today, "note": note},
            ).mappings().fetchone()

            total = float(credits_minutes) + (float(row["credits_minutes"]) if row else 0.0)
            action_type = "club_checkin" if credit_rules.counts_as_checkin(total) else "credit"

            if row:
                session.execute(
                    text("""
                        UPDATE actions
                        SET credits_minutes = :total, action_type = :atype, at_utc = :at_utc
                        WHERE action_uuid = :aid;
                    """),
                    {"total": total, "atype": action_type, "at_utc": at_utc,
                     "aid": row["action_uuid"]},
                )
            else:
                session.execute(
                    text("""
                        INSERT INTO actions(
                            action_uuid, user_id, promise_uuid, promise_id_text,
                            action_type, time_spent_hours, at_utc, notes, credits_minutes
                        ) VALUES (
                            :action_uuid, :user_id, :promise_uuid, '',
                            :atype, 0.0, :at_utc, :note, :total
                        );
                    """),
                    {"action_uuid": str(uuid.uuid4()), "user_id": user,
                     "promise_uuid": promise_uuid, "atype": action_type,
                     "at_utc": at_utc, "note": note, "total": total},
                )
        return total

    def append_scored_checkin(
        self,
        user_id: int,
        promise_uuid: str,
        score: float,
        notes: str | None = None,
        challenge_id: str | None = None,
        time_spent_hours: float = 0.0,
        credits_minutes: float = 0.0,
    ) -> None:
        """Record a non-binary scored check-in for today (idempotent — replaces any existing one).

        Used by challenge daily quizzes: one check-in per day carries the day's score (0..100),
        which drives both the streak (activity) and the leaderboard (how well). Stored as a
        'club_checkin' action so the existing streak/leaderboard paths pick it up.

        Idempotency is per **challenge** per day, not per promise per day. One
        promise can back several challenges — a single "Learn French" promise
        owning both a course quiz and a naturalisation quiz — and scoping the
        replace by promise alone made the second quiz of the day delete the
        first one's check-in.

        `time_spent_hours` is the measured time actually spent answering — the
        true duration, kept for the record. `credits_minutes` is what the work is
        *worth* (see services/credits.py); that is what drives progress, because
        a quiz that genuinely took 52 seconds is not a meaningful share of a
        weekly hours target.
        """
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
                      AND DATE(at_utc) = :today
                      AND (
                            (:challenge_id IS NULL AND challenge_id IS NULL)
                         OR challenge_id = :challenge_id
                      );
                """),
                {
                    "user_id": user,
                    "promise_uuid": promise_uuid,
                    "today": today,
                    "challenge_id": challenge_id,
                },
            )
            session.execute(
                text("""
                    INSERT INTO actions(
                        action_uuid, user_id, promise_uuid, promise_id_text,
                        action_type, time_spent_hours, score, at_utc, notes,
                        challenge_id, credits_minutes
                    ) VALUES (
                        :action_uuid, :user_id, :promise_uuid, '',
                        'club_checkin', :hours, :score, :at_utc, :notes,
                        :challenge_id, :credits
                    );
                """),
                {
                    "action_uuid": str(uuid.uuid4()),
                    "user_id": user,
                    "promise_uuid": promise_uuid,
                    "score": float(score),
                    "hours": float(time_spent_hours),
                    "credits": float(credits_minutes),
                    "at_utc": at_utc,
                    "notes": notes,
                    "challenge_id": challenge_id,
                },
            )

    def delete_club_checkin(self, user_id: int, promise_uuid: str, today: date | None = None) -> None:
        """Remove today's club check-in action. See `append_club_checkin` for `today`."""
        user = str(user_id)
        today = (today or datetime.utcnow().date()).strftime("%Y-%m-%d")
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

    def get_today_checkins(self, promise_uuid: str, today: date | None = None) -> set[str]:
        """Return the set of user_ids (as str) who have a club_checkin action today.
        See `append_club_checkin` for `today`.
        """
        today = (today or datetime.utcnow().date()).strftime("%Y-%m-%d")
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
