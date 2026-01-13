from datetime import datetime
from typing import List, Optional

from sqlalchemy import text

from db.postgres_db import (
    get_db_session,
    dt_to_utc_iso,
    dt_utc_iso_to_local_naive,
    resolve_promise_uuid,
    utc_now_iso,
)
from models.models import Session


class SessionsRepository:
    """PostgreSQL-backed sessions repository."""

    def __init__(self, root_dir: str = None):
        # root_dir kept for backward compatibility but not used for PostgreSQL
        self.root_dir = root_dir

    def create_session(self, session: Session) -> None:
        user = str(session.user_id)
        pid = (session.promise_id or "").strip().upper()

        with get_db_session() as session_db:
            p_uuid = resolve_promise_uuid(session_db, user, pid)
            if not p_uuid:
                # Cannot create a session without linking to a promise
                return

            session_db.execute(
                text("""
                    INSERT INTO sessions(
                        session_id, user_id, promise_uuid, status,
                        started_at_utc, ended_at_utc, paused_seconds_total,
                        last_state_change_at_utc, message_id, chat_id
                    ) VALUES (
                        :session_id, :user_id, :p_uuid, :status,
                        :started_at_utc, :ended_at_utc, :paused_seconds_total,
                        :last_state_change_at_utc, :message_id, :chat_id
                    )
                    ON CONFLICT (session_id) DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        promise_uuid = EXCLUDED.promise_uuid,
                        status = EXCLUDED.status,
                        started_at_utc = EXCLUDED.started_at_utc,
                        ended_at_utc = EXCLUDED.ended_at_utc,
                        paused_seconds_total = EXCLUDED.paused_seconds_total,
                        last_state_change_at_utc = EXCLUDED.last_state_change_at_utc,
                        message_id = EXCLUDED.message_id,
                        chat_id = EXCLUDED.chat_id;
                """),
                {
                    "session_id": str(session.session_id),
                    "user_id": user,
                    "p_uuid": p_uuid,
                    "status": str(session.status or "running"),
                    "started_at_utc": dt_to_utc_iso(session.started_at, assume_local_tz=True) or utc_now_iso(),
                    "ended_at_utc": dt_to_utc_iso(session.ended_at, assume_local_tz=True),
                    "paused_seconds_total": int(session.paused_seconds_total or 0),
                    "last_state_change_at_utc": dt_to_utc_iso(session.last_state_change_at, assume_local_tz=True),
                    "message_id": session.message_id,
                    "chat_id": session.chat_id,
                },
            )

    def update_session(self, session: Session) -> None:
        user = str(session.user_id)
        pid = (session.promise_id or "").strip().upper()

        with get_db_session() as session_db:
            p_uuid = resolve_promise_uuid(session_db, user, pid)
            if not p_uuid:
                return

            session_db.execute(
                text("""
                    INSERT INTO sessions(
                        session_id, user_id, promise_uuid, status,
                        started_at_utc, ended_at_utc, paused_seconds_total,
                        last_state_change_at_utc, message_id, chat_id
                    ) VALUES (
                        :session_id, :user_id, :p_uuid, :status,
                        :started_at_utc, :ended_at_utc, :paused_seconds_total,
                        :last_state_change_at_utc, :message_id, :chat_id
                    )
                    ON CONFLICT (session_id) DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        promise_uuid = EXCLUDED.promise_uuid,
                        status = EXCLUDED.status,
                        started_at_utc = EXCLUDED.started_at_utc,
                        ended_at_utc = EXCLUDED.ended_at_utc,
                        paused_seconds_total = EXCLUDED.paused_seconds_total,
                        last_state_change_at_utc = EXCLUDED.last_state_change_at_utc,
                        message_id = EXCLUDED.message_id,
                        chat_id = EXCLUDED.chat_id;
                """),
                {
                    "session_id": str(session.session_id),
                    "user_id": user,
                    "p_uuid": p_uuid,
                    "status": str(session.status or "running"),
                    "started_at_utc": dt_to_utc_iso(session.started_at, assume_local_tz=True) or utc_now_iso(),
                    "ended_at_utc": dt_to_utc_iso(session.ended_at, assume_local_tz=True),
                    "paused_seconds_total": int(session.paused_seconds_total or 0),
                    "last_state_change_at_utc": dt_to_utc_iso(session.last_state_change_at, assume_local_tz=True),
                    "message_id": session.message_id,
                    "chat_id": session.chat_id,
                },
            )

    def get_session(self, user_id: int, session_id: str) -> Optional[Session]:
        user = str(user_id)
        sessions = self.list_sessions(user_id)
        for s in sessions:
            if s.session_id == session_id:
                return s
        return None

    def list_sessions(self, user_id: int) -> List[Session]:
        user = str(user_id)
        with get_db_session() as session_db:
            rows = session_db.execute(
                text("""
                    SELECT
                        s.session_id,
                        COALESCE(p.current_id, '') AS promise_id,
                        s.status,
                        s.started_at_utc,
                        s.ended_at_utc,
                        s.paused_seconds_total,
                        s.last_state_change_at_utc,
                        s.message_id,
                        s.chat_id
                    FROM sessions s
                    LEFT JOIN promises p ON p.promise_uuid = s.promise_uuid AND p.user_id = s.user_id
                    WHERE s.user_id = :user_id
                    ORDER BY s.started_at_utc ASC;
                """),
                {"user_id": user},
            ).fetchall()

        result: List[Session] = []
        for r in rows:
            started_at = dt_utc_iso_to_local_naive(r["started_at_utc"])
            if not started_at:
                continue
            result.append(
                Session(
                    session_id=str(r["session_id"]),
                    user_id=user,
                    promise_id=str(r["promise_id"] or ""),
                    status=str(r["status"] or ""),
                    started_at=started_at,
                    ended_at=dt_utc_iso_to_local_naive(r["ended_at_utc"]),
                    paused_seconds_total=int(r["paused_seconds_total"] or 0),
                    last_state_change_at=dt_utc_iso_to_local_naive(r["last_state_change_at_utc"]),
                    message_id=int(r["message_id"]) if r["message_id"] is not None else None,
                    chat_id=int(r["chat_id"]) if r["chat_id"] is not None else None,
                )
            )
        return result

    def list_active_sessions(self, user_id: int) -> List[Session]:
        all_sessions = self.list_sessions(user_id)
        return [s for s in all_sessions if s.status in ["running", "paused"]]
