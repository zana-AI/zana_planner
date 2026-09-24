"""One-use browser sign-in links issued only by an authenticated private bot chat.

Reuse auth_sessions with a distinct method: these hashed, five-minute codes are
NOT bearer sessions. Redemption and creation of the real session are atomic.
"""
import hashlib
import secrets
import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy import text

from db.postgres_db import get_db_session
from repositories.auth_session_repo import _dt_to_iso

LOGIN_METHOD = "browser_login_code"


def _digest(code: str) -> str:
    return "login:" + hashlib.sha256(code.encode()).hexdigest()


class BrowserLoginRepository:
    def issue(self, user_id: int) -> str:
        code = secrets.token_urlsafe(32)
        now = datetime.utcnow()
        with get_db_session() as db:
            db.execute(text("""
                DELETE FROM auth_sessions
                WHERE auth_method = :method AND (user_id = :uid OR expires_at <= :now)
            """), {"method": LOGIN_METHOD, "uid": str(user_id), "now": _dt_to_iso(now)})
            db.execute(text("""
                INSERT INTO auth_sessions
                    (session_token, user_id, created_at, expires_at, telegram_auth_date, auth_method)
                VALUES (:token, :uid, :now, :expires, :auth_date, :method)
            """), {"token": _digest(code), "uid": str(user_id), "now": _dt_to_iso(now),
                   "expires": _dt_to_iso(now + timedelta(minutes=5)),
                   "auth_date": int(time.time()), "method": LOGIN_METHOD})
        return code

    def preview(self, code: str) -> dict | None:
        with get_db_session() as db:
            row = db.execute(text("""
                SELECT s.user_id, u.first_name, u.username
                FROM auth_sessions s LEFT JOIN users u ON u.user_id = s.user_id
                WHERE s.session_token = :token AND s.auth_method = :method
                  AND s.expires_at > :now
            """), {"token": _digest(code), "method": LOGIN_METHOD,
                   "now": _dt_to_iso(datetime.utcnow())}).mappings().fetchone()
            return dict(row) if row else None

    def redeem(self, code: str, expected_user_id: int) -> dict | None:
        now = datetime.utcnow()
        expires = now + timedelta(days=90)
        with get_db_session() as db:
            # DELETE RETURNING gives exactly one winner, even across processes.
            row = db.execute(text("""
                DELETE FROM auth_sessions
                WHERE session_token = :code AND auth_method = :method
                  AND expires_at > :now AND user_id = :uid
                RETURNING user_id, telegram_auth_date
            """), {"code": _digest(code), "method": LOGIN_METHOD,
                   "now": _dt_to_iso(now), "uid": str(expected_user_id)}).mappings().fetchone()
            if not row:
                return None
            token = str(uuid.uuid4())
            db.execute(text("""
                INSERT INTO auth_sessions
                    (session_token, user_id, created_at, expires_at, telegram_auth_date, auth_method)
                VALUES (:token, :uid, :now, :expires, :auth_date, 'bot_login')
            """), {"token": token, "uid": row["user_id"], "now": _dt_to_iso(now),
                   "expires": _dt_to_iso(expires), "auth_date": row["telegram_auth_date"]})
            return {"session_token": token, "user_id": int(row["user_id"]),
                    "expires_at": expires.isoformat()}
