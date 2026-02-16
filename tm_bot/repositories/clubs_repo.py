import uuid
from typing import List, Optional, Dict
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from db.postgres_db import get_db_session, utc_now_iso


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
            session.execute(
                text("""
                    INSERT INTO clubs(
                        club_id, owner_user_id, name, description,
                        visibility, created_at_utc, updated_at_utc
                    ) VALUES (:club_id, :owner_user_id, :name, :description, :visibility, :created_at_utc, :updated_at_utc);
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
                        ORDER BY created_at_utc DESC;
                    """),
                ).fetchall()
            
            return [dict(row._mapping) for row in rows]

    def add_member(
        self,
        club_id: str,
        user_id: int,
        role: str = "member",
    ) -> bool:
        """Add a user to a club."""
        user = str(user_id)
        now = utc_now_iso()
        
        with get_db_session() as session:
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
            try:
                session.execute(
                    text("""
                        INSERT INTO promise_club_shares(promise_uuid, club_id, created_at_utc)
                        VALUES (:promise_uuid, :club_id, :created_at_utc);
                    """),
                    {"promise_uuid": promise_uuid, "club_id": club_id, "created_at_utc": now},
                )
                return True
            except IntegrityError:
                return False  # Already shared

