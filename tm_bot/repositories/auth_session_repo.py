"""
DB-backed authentication session repository.

Sessions are stored in the `auth_sessions` PostgreSQL table so they survive
server restarts. The previous in-memory implementation lost all sessions on
every deployment, breaking PWA / home-screen web app logins.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso, dt_from_utc_iso
from models.models import AuthSession
from utils.logger import get_logger

logger = get_logger(__name__)

_ISO_FMT = "%Y-%m-%dT%H:%M:%S.%f"


def _dt_to_iso(dt: datetime) -> str:
    return dt.strftime(_ISO_FMT)


def _iso_to_dt(s: str) -> datetime:
    return dt_from_utc_iso(s) or datetime.utcnow()


class AuthSessionRepository:
    """PostgreSQL-backed repository for browser authentication sessions."""

    def create_session(
        self,
        user_id: int,
        telegram_auth_date: int,
        expires_in_days: int = 90,
        auth_method: str = "widget",
    ) -> AuthSession:
        session_token = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + timedelta(days=expires_in_days)

        with get_db_session() as db:
            db.execute(
                text("""
                    INSERT INTO auth_sessions
                        (session_token, user_id, created_at, expires_at,
                         telegram_auth_date, auth_method)
                    VALUES
                        (:token, :user_id, :created_at, :expires_at,
                         :tg_auth_date, :auth_method)
                    ON CONFLICT (session_token) DO NOTHING;
                """),
                {
                    "token": session_token,
                    "user_id": str(user_id),
                    "created_at": _dt_to_iso(now),
                    "expires_at": _dt_to_iso(expires_at),
                    "tg_auth_date": telegram_auth_date,
                    "auth_method": auth_method,
                },
            )

        logger.debug("Created auth session for user %s, expires %s", user_id, expires_at.date())
        return AuthSession(
            session_token=session_token,
            user_id=user_id,
            created_at=now,
            expires_at=expires_at,
            telegram_auth_date=telegram_auth_date,
        )

    def get_session(self, session_token: str) -> Optional[AuthSession]:
        if not session_token:
            return None
        now_iso = utc_now_iso()
        with get_db_session() as db:
            row = db.execute(
                text("""
                    SELECT user_id, created_at, expires_at, telegram_auth_date
                    FROM auth_sessions
                    WHERE session_token = :token
                      AND expires_at > :now
                    LIMIT 1;
                """),
                {"token": session_token, "now": now_iso},
            ).mappings().fetchone()

        if not row:
            return None

        return AuthSession(
            session_token=session_token,
            user_id=int(row["user_id"]),
            created_at=_iso_to_dt(row["created_at"]),
            expires_at=_iso_to_dt(row["expires_at"]),
            telegram_auth_date=int(row["telegram_auth_date"] or 0),
        )

    def delete_session(self, session_token: str) -> bool:
        if not session_token:
            return False
        with get_db_session() as db:
            result = db.execute(
                text("DELETE FROM auth_sessions WHERE session_token = :token;"),
                {"token": session_token},
            )
        deleted = (result.rowcount or 0) > 0
        if deleted:
            logger.debug("Deleted auth session %s…", session_token[:8])
        return deleted

    def cleanup_expired(self) -> int:
        now_iso = utc_now_iso()
        with get_db_session() as db:
            result = db.execute(
                text("DELETE FROM auth_sessions WHERE expires_at <= :now;"),
                {"now": now_iso},
            )
        count = result.rowcount or 0
        if count:
            logger.info("Cleaned up %d expired auth session(s)", count)
        return count

    def get_user_sessions(self, user_id: int) -> list[AuthSession]:
        now_iso = utc_now_iso()
        with get_db_session() as db:
            rows = db.execute(
                text("""
                    SELECT session_token, created_at, expires_at, telegram_auth_date
                    FROM auth_sessions
                    WHERE user_id = :user_id AND expires_at > :now;
                """),
                {"user_id": str(user_id), "now": now_iso},
            ).mappings().fetchall()

        return [
            AuthSession(
                session_token=row["session_token"],
                user_id=user_id,
                created_at=_iso_to_dt(row["created_at"]),
                expires_at=_iso_to_dt(row["expires_at"]),
                telegram_auth_date=int(row["telegram_auth_date"] or 0),
            )
            for row in rows
        ]
