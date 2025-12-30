import sqlite3
import uuid
from typing import List, Optional, Dict
from datetime import datetime

from db.sqlite_db import connection_for_root, utc_now_iso


class ClubsRepository:
    """Repository for managing clubs (groups) and memberships."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

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
        
        with connection_for_root(self.root_dir) as conn:
            conn.execute(
                """
                INSERT INTO clubs(
                    club_id, owner_user_id, name, description,
                    visibility, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (club_id, owner, name, description, visibility, now, now),
            )
            
            # Add owner as member with 'owner' role
            conn.execute(
                """
                INSERT INTO club_members(
                    club_id, user_id, role, status, joined_at_utc
                ) VALUES (?, ?, 'owner', 'active', ?);
                """,
                (club_id, owner, now),
            )
        
        return club_id

    def get_club(self, club_id: str) -> Optional[Dict]:
        """Get club by ID."""
        with connection_for_root(self.root_dir) as conn:
            row = conn.execute(
                """
                SELECT * FROM clubs WHERE club_id = ? LIMIT 1;
                """,
                (club_id,),
            ).fetchone()
            
            if not row:
                return None
            return dict(row)

    def list_clubs(self, user_id: Optional[int] = None) -> List[Dict]:
        """List clubs (optionally filtered by user membership)."""
        with connection_for_root(self.root_dir) as conn:
            if user_id:
                # Get clubs where user is a member
                rows = conn.execute(
                    """
                    SELECT DISTINCT c.* FROM clubs c
                    INNER JOIN club_members cm ON c.club_id = cm.club_id
                    WHERE cm.user_id = ? AND cm.status = 'active'
                    ORDER BY c.created_at_utc DESC;
                    """,
                    (str(user_id),),
                ).fetchall()
            else:
                # Get all public clubs
                rows = conn.execute(
                    """
                    SELECT * FROM clubs
                    WHERE visibility = 'public'
                    ORDER BY created_at_utc DESC;
                    """,
                ).fetchall()
            
            return [dict(row) for row in rows]

    def add_member(
        self,
        club_id: str,
        user_id: int,
        role: str = "member",
    ) -> bool:
        """Add a user to a club."""
        user = str(user_id)
        now = utc_now_iso()
        
        with connection_for_root(self.root_dir) as conn:
            # Check if already a member
            existing = conn.execute(
                """
                SELECT status FROM club_members
                WHERE club_id = ? AND user_id = ?
                LIMIT 1;
                """,
                (club_id, user),
            ).fetchone()
            
            if existing:
                if existing["status"] == "active":
                    return False  # Already a member
                # Reactivate if previously left/banned
                conn.execute(
                    """
                    UPDATE club_members
                    SET status = 'active', role = ?, joined_at_utc = ?, left_at_utc = NULL
                    WHERE club_id = ? AND user_id = ?;
                    """,
                    (role, now, club_id, user),
                )
                return True
            
            # Add new member
            conn.execute(
                """
                INSERT INTO club_members(
                    club_id, user_id, role, status, joined_at_utc
                ) VALUES (?, ?, ?, 'active', ?);
                """,
                (club_id, user, role, now),
            )
            return True

    def remove_member(self, club_id: str, user_id: int) -> bool:
        """Remove a user from a club (soft delete)."""
        user = str(user_id)
        now = utc_now_iso()
        
        with connection_for_root(self.root_dir) as conn:
            result = conn.execute(
                """
                UPDATE club_members
                SET status = 'left', left_at_utc = ?
                WHERE club_id = ? AND user_id = ? AND status = 'active';
                """,
                (now, club_id, user),
            )
            return result.rowcount > 0

    def get_members(self, club_id: str) -> List[Dict]:
        """Get all active members of a club."""
        with connection_for_root(self.root_dir) as conn:
            rows = conn.execute(
                """
                SELECT user_id, role, joined_at_utc
                FROM club_members
                WHERE club_id = ? AND status = 'active'
                ORDER BY joined_at_utc ASC;
                """,
                (club_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def is_member(self, club_id: str, user_id: int) -> bool:
        """Check if user is an active member of the club."""
        user = str(user_id)
        with connection_for_root(self.root_dir) as conn:
            row = conn.execute(
                """
                SELECT 1 FROM club_members
                WHERE club_id = ? AND user_id = ? AND status = 'active'
                LIMIT 1;
                """,
                (club_id, user),
            ).fetchone()
            return bool(row)

    def share_promise_to_club(self, promise_uuid: str, club_id: str) -> bool:
        """Share a promise to a club (for visibility='clubs')."""
        now = utc_now_iso()
        with connection_for_root(self.root_dir) as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO promise_club_shares(promise_uuid, club_id, created_at_utc)
                    VALUES (?, ?, ?);
                    """,
                    (promise_uuid, club_id, now),
                )
                return True
            except sqlite3.IntegrityError:
                return False  # Already shared

