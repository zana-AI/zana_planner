"""Persistence for linking an OAuth identity (WorkOS subject) to a Zana user.

Two tables (see migration 026):
  - mcp_account_links: (oauth_issuer, oauth_subject) -> user_id
  - mcp_link_codes:    short-lived one-time codes minted from an authenticated
                       Zana surface (the Mini App), redeemed by the MCP client.

Flow: user gets a code in the Xaana app (POST /api/mcp/link-code), then in their
AI client calls the `link_account` tool with it; redeeming the code creates the
(issuer, subject) -> user_id link.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import text

from db.postgres_db import get_db_session

# Unambiguous alphabet (no O/0, I/1) for human-friendly codes.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _gen_code(n: int = 8) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(n))


def _now() -> datetime:
    return datetime.now(timezone.utc)


class McpLinksRepository:
    def get_user_id_for_subject(self, issuer: str, subject: str) -> Optional[str]:
        with get_db_session() as session:
            row = session.execute(
                text(
                    "SELECT user_id FROM mcp_account_links "
                    "WHERE oauth_issuer = :issuer AND oauth_subject = :subject LIMIT 1"
                ),
                {"issuer": issuer, "subject": subject},
            ).fetchone()
            return str(row[0]) if row else None

    def upsert_link(self, issuer: str, subject: str, user_id) -> None:
        with get_db_session() as session:
            session.execute(
                text(
                    "INSERT INTO mcp_account_links (oauth_issuer, oauth_subject, user_id, created_at_utc) "
                    "VALUES (:issuer, :subject, :user_id, :now) "
                    "ON CONFLICT (oauth_issuer, oauth_subject) DO UPDATE SET user_id = :user_id"
                ),
                {"issuer": issuer, "subject": subject, "user_id": str(user_id), "now": _now().isoformat()},
            )

    def create_link_code(self, user_id, ttl_seconds: int = 900) -> Tuple[str, str]:
        """Mint a one-time link code for an already-authenticated Zana user.

        Returns (code, expires_at_iso).
        """
        now = _now()
        expires_at = now + timedelta(seconds=ttl_seconds)
        code = _gen_code()
        with get_db_session() as session:
            session.execute(
                text(
                    "INSERT INTO mcp_link_codes (code, user_id, created_at_utc, expires_at_utc) "
                    "VALUES (:code, :user_id, :now, :expires)"
                ),
                {"code": code, "user_id": str(user_id), "now": now.isoformat(), "expires": expires_at.isoformat()},
            )
        return code, expires_at.isoformat()

    def redeem_link_code(self, code: str, issuer: str, subject: str) -> Optional[str]:
        """Redeem a code for the given OAuth identity. Returns the linked user_id,
        or None if the code is unknown, already used, or expired."""
        now = _now()
        with get_db_session() as session:
            row = session.execute(
                text(
                    "SELECT user_id, expires_at_utc, redeemed_at_utc "
                    "FROM mcp_link_codes WHERE code = :code LIMIT 1"
                ),
                {"code": code},
            ).fetchone()
            if not row:
                return None
            user_id, expires_at_utc, redeemed_at_utc = row[0], row[1], row[2]
            if redeemed_at_utc:
                return None
            try:
                if datetime.fromisoformat(expires_at_utc) < now:
                    return None
            except (TypeError, ValueError):
                return None

            session.execute(
                text(
                    "UPDATE mcp_link_codes SET redeemed_at_utc = :now, redeemed_subject = :subject "
                    "WHERE code = :code"
                ),
                {"now": now.isoformat(), "subject": subject, "code": code},
            )
            session.execute(
                text(
                    "INSERT INTO mcp_account_links (oauth_issuer, oauth_subject, user_id, created_at_utc) "
                    "VALUES (:issuer, :subject, :user_id, :now) "
                    "ON CONFLICT (oauth_issuer, oauth_subject) DO UPDATE SET user_id = :user_id"
                ),
                {"issuer": issuer, "subject": subject, "user_id": str(user_id), "now": now.isoformat()},
            )
            return str(user_id)
