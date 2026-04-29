import uuid
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from sqlalchemy import text
from db.postgres_db import get_db_session, utc_now_iso


_CLUB_TELEGRAM_COLUMNS_CHECKED = False


def ensure_club_telegram_columns(session) -> None:
    """Best-effort runtime guard for deployments where Alembic has not run yet."""
    global _CLUB_TELEGRAM_COLUMNS_CHECKED
    if _CLUB_TELEGRAM_COLUMNS_CHECKED:
        return

    for ddl in (
        "ALTER TABLE clubs ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'",
        "ALTER TABLE clubs ADD COLUMN IF NOT EXISTS telegram_status TEXT NOT NULL DEFAULT 'not_connected'",
        "ALTER TABLE clubs ADD COLUMN IF NOT EXISTS telegram_invite_link TEXT",
        "ALTER TABLE clubs ADD COLUMN IF NOT EXISTS telegram_chat_id TEXT",
        "ALTER TABLE clubs ADD COLUMN IF NOT EXISTS telegram_requested_at_utc TEXT",
        "ALTER TABLE clubs ADD COLUMN IF NOT EXISTS telegram_last_admin_reminder_at_utc TEXT",
        "ALTER TABLE clubs ADD COLUMN IF NOT EXISTS telegram_ready_at_utc TEXT",
        "ALTER TABLE clubs ADD COLUMN IF NOT EXISTS telegram_setup_by_admin_id TEXT",
        "ALTER TABLE clubs ADD COLUMN IF NOT EXISTS reminder_time TEXT",
        "ALTER TABLE clubs ADD COLUMN IF NOT EXISTS language TEXT",
        "ALTER TABLE clubs ADD COLUMN IF NOT EXISTS vibe TEXT",
        "ALTER TABLE clubs ADD COLUMN IF NOT EXISTS checkin_what_counts TEXT",
        "ALTER TABLE clubs ADD COLUMN IF NOT EXISTS club_goal TEXT",
    ):
        session.execute(text(ddl))

    _CLUB_TELEGRAM_COLUMNS_CHECKED = True


def get_club_columns(session) -> set[str]:
    rows = session.execute(
        text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'clubs';
        """),
    ).fetchall()
    return {row[0] for row in rows}


class ClubsRepository:
    """Repository for managing clubs (groups) and memberships."""

    def __init__(self) -> None:
        pass

    def create_club(
        self,
        owner_user_id: int,
        name: str,
        description: Optional[str] = None,
        visibility: str = "private",
    ) -> str:
        """
        Create a new club.
        Returns the club_id.
        """
        owner = str(owner_user_id)
        club_id = str(uuid.uuid4())
        now = utc_now_iso()
        
        with get_db_session() as session:
            ensure_club_telegram_columns(session)
            club_columns = get_club_columns(session)

            has_telegram_columns = (
                "telegram_status" in club_columns
                and "telegram_requested_at_utc" in club_columns
            )

            if has_telegram_columns:
                session.execute(
                    text("""
                        INSERT INTO clubs(
                            club_id, owner_user_id, name, description,
                            visibility, telegram_status, telegram_requested_at_utc,
                            created_at_utc, updated_at_utc
                        ) VALUES (
                            :club_id, :owner_user_id, :name, :description,
                            :visibility, :telegram_status, :telegram_requested_at_utc,
                            :created_at_utc, :updated_at_utc
                        );
                    """),
                    {
                        "club_id": club_id,
                        "owner_user_id": owner,
                        "name": name,
                        "description": description,
                        "visibility": visibility,
                        "telegram_status": "pending_admin_setup",
                        "telegram_requested_at_utc": now,
                        "created_at_utc": now,
                        "updated_at_utc": now,
                    },
                )
            else:
                session.execute(
                    text("""
                        INSERT INTO clubs(
                            club_id, owner_user_id, name, description,
                            visibility, created_at_utc, updated_at_utc
                        ) VALUES (
                            :club_id, :owner_user_id, :name, :description,
                            :visibility, :created_at_utc, :updated_at_utc
                        );
                    """),
                    {
                        "club_id": club_id,
                        "owner_user_id": owner,
                        "name": name,
                        "description": description,
                        "visibility": visibility,
                        "created_at_utc": now,
                        "updated_at_utc": now,
                    },
                )
            
            # Add owner as member with 'owner' role
            session.execute(
                text("""
                    INSERT INTO club_members(
                        club_id, user_id, role, status, joined_at_utc
                    ) VALUES (:club_id, :user_id, 'owner', 'active', :joined_at_utc);
                """),
                {
                    "club_id": club_id,
                    "user_id": owner,
                    "joined_at_utc": now,
                },
            )
        
        return club_id

    def get_club(self, club_id: str) -> Optional[Dict]:
        """Get club by ID."""
        with get_db_session() as session:
            row = session.execute(
                text("SELECT * FROM clubs WHERE club_id = :club_id LIMIT 1;"),
                {"club_id": club_id},
            ).fetchone()
            
            if not row:
                return None
            return dict(row._mapping)

    def list_clubs(self, user_id: Optional[int] = None) -> List[Dict]:
        """List clubs (optionally filtered by user membership)."""
        with get_db_session() as session:
            if user_id:
                # Get clubs where user is a member
                rows = session.execute(
                    text("""
                        SELECT DISTINCT c.* FROM clubs c
                        INNER JOIN club_members cm ON c.club_id = cm.club_id
                        WHERE cm.user_id = :user_id AND cm.status = 'active'
                        ORDER BY c.created_at_utc DESC;
                    """),
                    {"user_id": str(user_id)},
                ).fetchall()
            else:
                # Get all public clubs
                rows = session.execute(
                    text("""
                        SELECT * FROM clubs
                        WHERE visibility = 'public'
                          AND COALESCE(status, 'active') = 'active'
                        ORDER BY created_at_utc DESC;
                    """),
                ).fetchall()
            
            return [dict(row._mapping) for row in rows]

    def add_member(
        self,
        club_id: str,
        user_id: int,
        role: str = "member",
        first_name: str = None,
        username: str = None,
    ) -> bool:
        """Add a user to a club.

        If the user has never started the bot they won't have a row in `users`.
        We upsert a stub row first so the FK constraint is satisfied; a real
        onboarding flow will fill in the remaining fields later.
        """
        user = str(user_id)
        now = utc_now_iso()

        with get_db_session() as session:
            # Ensure a users row exists (stub if never onboarded via bot)
            session.execute(
                text("""
                    INSERT INTO users (
                        user_id, first_name, username,
                        timezone, nightly_hh, nightly_mm, language,
                        created_at_utc, updated_at_utc
                    ) VALUES (
                        :user_id, :first_name, :username,
                        'UTC', 21, 0, 'en',
                        :now, :now
                    )
                    ON CONFLICT (user_id) DO UPDATE
                        SET first_name = COALESCE(EXCLUDED.first_name, users.first_name),
                            username   = COALESCE(EXCLUDED.username,   users.username),
                            updated_at_utc = EXCLUDED.updated_at_utc;
                """),
                {"user_id": user, "first_name": first_name, "username": username, "now": now},
            )

            # Check if already a member
            existing = session.execute(
                text("""
                    SELECT status FROM club_members
                    WHERE club_id = :club_id AND user_id = :user_id
                    LIMIT 1;
                """),
                {"club_id": club_id, "user_id": user},
            ).fetchone()

            if existing:
                if existing[0] == "active":
                    return False  # Already a member
                # Reactivate if previously left/banned
                session.execute(
                    text("""
                        UPDATE club_members
                        SET status = 'active', role = :role, joined_at_utc = :joined_at_utc, left_at_utc = NULL
                        WHERE club_id = :club_id AND user_id = :user_id;
                    """),
                    {"role": role, "joined_at_utc": now, "club_id": club_id, "user_id": user},
                )
                return True

            # Add new member
            session.execute(
                text("""
                    INSERT INTO club_members(
                        club_id, user_id, role, status, joined_at_utc
                    ) VALUES (:club_id, :user_id, :role, 'active', :joined_at_utc);
                """),
                {
                    "club_id": club_id,
                    "user_id": user,
                    "role": role,
                    "joined_at_utc": now,
                },
            )
            return True

    def remove_member(self, club_id: str, user_id: int) -> bool:
        """Remove a user from a club (soft delete)."""
        user = str(user_id)
        now = utc_now_iso()
        
        with get_db_session() as session:
            result = session.execute(
                text("""
                    UPDATE club_members
                    SET status = 'left', left_at_utc = :left_at_utc
                    WHERE club_id = :club_id AND user_id = :user_id AND status = 'active';
                """),
                {"left_at_utc": now, "club_id": club_id, "user_id": user},
            )
            return result.rowcount > 0

    def cancel_pending_club(self, club_id: str, owner_user_id: int) -> bool:
        """Cancel a pending owner-created club before it becomes active."""
        owner = str(owner_user_id)
        now = utc_now_iso()

        with get_db_session() as session:
            ensure_club_telegram_columns(session)
            result = session.execute(
                text("""
                    UPDATE clubs
                    SET status = 'cancelled',
                        telegram_status = 'cancelled',
                        updated_at_utc = :updated_at_utc
                    WHERE club_id = :club_id
                      AND owner_user_id = :owner_user_id
                      AND COALESCE(status, 'active') = 'active'
                      AND telegram_status = 'pending_admin_setup';
                """),
                {
                    "club_id": club_id,
                    "owner_user_id": owner,
                    "updated_at_utc": now,
                },
            )
            if result.rowcount <= 0:
                return False

            session.execute(
                text("""
                    UPDATE club_members
                    SET status = 'left',
                        left_at_utc = :left_at_utc
                    WHERE club_id = :club_id
                      AND status = 'active';
                """),
                {"club_id": club_id, "left_at_utc": now},
            )
            return True

    def mark_admin_reminded(self, club_id: str, owner_user_id: int) -> bool:
        """Record that the owner sent a reminder to admins for a pending club."""
        owner = str(owner_user_id)
        now = utc_now_iso()

        with get_db_session() as session:
            ensure_club_telegram_columns(session)
            result = session.execute(
                text("""
                    UPDATE clubs
                    SET telegram_last_admin_reminder_at_utc = :reminded_at,
                        updated_at_utc = :updated_at_utc
                    WHERE club_id = :club_id
                      AND owner_user_id = :owner_user_id
                      AND COALESCE(status, 'active') = 'active'
                      AND telegram_status = 'pending_admin_setup';
                """),
                {
                    "club_id": club_id,
                    "owner_user_id": owner,
                    "reminded_at": now,
                    "updated_at_utc": now,
                },
            )
            return result.rowcount > 0

    def get_members(self, club_id: str) -> List[Dict]:
        """Get all active members of a club."""
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT user_id, role, joined_at_utc
                    FROM club_members
                    WHERE club_id = :club_id AND status = 'active'
                    ORDER BY joined_at_utc ASC;
                """),
                {"club_id": club_id},
            ).fetchall()
            return [dict(row._mapping) for row in rows]

    def is_member(self, club_id: str, user_id: int) -> bool:
        """Check if user is an active member of the club."""
        user = str(user_id)
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT 1 FROM club_members
                    WHERE club_id = :club_id AND user_id = :user_id AND status = 'active'
                    LIMIT 1;
                """),
                {"club_id": club_id, "user_id": user},
            ).fetchone()
            return bool(row)

    def share_promise_to_club(self, promise_uuid: str, club_id: str) -> bool:
        """Share a promise to a club (for visibility='clubs')."""
        now = utc_now_iso()
        with get_db_session() as session:
            result = session.execute(
                text("""
                    INSERT INTO promise_club_shares(promise_uuid, club_id, created_at_utc)
                    VALUES (:promise_uuid, :club_id, :created_at_utc)
                    ON CONFLICT (promise_uuid, club_id) DO NOTHING;
                """),
                {"promise_uuid": promise_uuid, "club_id": club_id, "created_at_utc": now},
            )
            return result.rowcount > 0

    def get_active_clubs_with_telegram(self) -> List[Dict]:
        """
        Return all clubs that have a confirmed Telegram group connected.

        These are the clubs eligible to receive scheduled group reminders.
        """
        with get_db_session() as session:
            ensure_club_telegram_columns(session)
            rows = session.execute(
                text("""
                    SELECT
                        club_id,
                        owner_user_id,
                        name,
                        telegram_chat_id,
                        COALESCE(reminder_time, '21:00') AS reminder_time,
                        language
                    FROM clubs
                    WHERE telegram_status IN ('ready', 'connected')
                      AND NULLIF(trim(COALESCE(telegram_chat_id, '')), '') IS NOT NULL
                      AND COALESCE(status, 'active') = 'active'
                    ORDER BY created_at_utc ASC;
                """),
            ).mappings().fetchall()
            return [dict(row) for row in rows]

    def update_club_context(
        self,
        club_id: str,
        vibe: str = None,
        checkin_what_counts: str = None,
        description: str = None,
        club_goal: str = None,
    ) -> None:
        """Persist admin-provided context fields that the bot uses in group responses."""
        now = utc_now_iso()
        updates: dict = {"updated_at_utc": now, "club_id": club_id}
        parts: list[str] = ["updated_at_utc = :updated_at_utc"]
        if vibe is not None:
            updates["vibe"] = vibe
            parts.append("vibe = :vibe")
        if checkin_what_counts is not None:
            updates["checkin_what_counts"] = checkin_what_counts
            parts.append("checkin_what_counts = :checkin_what_counts")
        if description is not None:
            updates["description"] = description
            parts.append("description = :description")
        if club_goal is not None:
            updates["club_goal"] = club_goal
            parts.append("club_goal = :club_goal")
        if len(parts) == 1:
            return
        with get_db_session() as session:
            ensure_club_telegram_columns(session)
            session.execute(
                text(f"UPDATE clubs SET {', '.join(parts)} WHERE club_id = :club_id;"),
                updates,
            )

    def get_club_members_promises(self, club_id: str) -> List[Dict]:
        """
        Return each active club member paired with the promise they explicitly
        shared to this specific club via promise_club_shares.

        Privacy guarantee: the join through promise_club_shares with
        pcs.club_id = :club_id means only promises shared to THIS club are
        returned — a member's private promises are never exposed.

        Members who have not shared a promise to this club will appear with
        promise_text=None.
        """
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT DISTINCT ON (cm.user_id)
                        cm.user_id,
                        u.first_name,
                        u.username,
                        u.non_latin_name,
                        u.latin_name,
                        p.text AS promise_text,
                        p.promise_uuid
                    FROM club_members cm
                    JOIN users u ON u.user_id = cm.user_id
                    LEFT JOIN promise_club_shares pcs
                        ON pcs.club_id = cm.club_id
                    LEFT JOIN promises p
                        ON p.promise_uuid = pcs.promise_uuid
                       AND p.is_deleted = 0
                    WHERE cm.club_id = :club_id
                      AND cm.status = 'active'
                    ORDER BY cm.user_id, pcs.created_at_utc ASC;
                """),
                {"club_id": club_id},
            ).mappings().fetchall()
            return [dict(row) for row in rows]

    def get_recent_checkins(self, club_id: str, days: int = 7, limit: int = 120) -> List[Dict]:
        """
        Return recent club check-ins scoped strictly to this club.

        Privacy guarantee: rows must match all three boundaries:
        active club member, promise shared to this club, and action owned by that
        member. This prevents a group query from seeing private actions or
        promises that were not shared into the club.
        """
        try:
            safe_days = max(1, min(int(days or 7), 31))
        except (TypeError, ValueError):
            safe_days = 7
        try:
            safe_limit = max(1, min(int(limit or 120), 300))
        except (TypeError, ValueError):
            safe_limit = 120

        since_date = (datetime.utcnow().date() - timedelta(days=safe_days - 1)).isoformat()
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT
                        cm.user_id,
                        u.first_name,
                        u.username,
                        u.non_latin_name,
                        u.latin_name,
                        DATE(a.at_utc) AS checkin_date,
                        MAX(a.at_utc) AS last_at_utc,
                        COUNT(*) AS checkin_count
                    FROM club_members cm
                    JOIN users u
                        ON u.user_id = cm.user_id
                    JOIN promise_club_shares pcs
                        ON pcs.club_id = cm.club_id
                    JOIN actions a
                        ON a.user_id = cm.user_id
                       AND a.promise_uuid = pcs.promise_uuid
                       AND a.action_type = 'club_checkin'
                       AND DATE(a.at_utc) >= :since_date
                    WHERE cm.club_id = :club_id
                      AND cm.status = 'active'
                    GROUP BY
                        cm.user_id,
                        u.first_name,
                        u.username,
                        u.non_latin_name,
                        u.latin_name,
                        DATE(a.at_utc)
                    ORDER BY checkin_date DESC, last_at_utc DESC
                    LIMIT :limit;
                """),
                {"club_id": club_id, "since_date": since_date, "limit": safe_limit},
            ).mappings().fetchall()
            return [dict(row) for row in rows]

    def get_today_club_checkins(self, club_id: str) -> set[str]:
        """Return active member user_ids that checked in today for this club only."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT DISTINCT a.user_id
                    FROM club_members cm
                    JOIN promise_club_shares pcs
                        ON pcs.club_id = cm.club_id
                    JOIN actions a
                        ON a.user_id = cm.user_id
                       AND a.promise_uuid = pcs.promise_uuid
                       AND a.action_type = 'club_checkin'
                       AND DATE(a.at_utc) = :today
                    WHERE cm.club_id = :club_id
                      AND cm.status = 'active';
                """),
                {"club_id": club_id, "today": today},
            ).fetchall()
        return {str(row[0]) for row in rows}
