from typing import List, Optional
from datetime import datetime
import json

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso


class BlocksRepository:
    """Repository for managing user block relationships."""

    def __init__(self) -> None:
        pass

    def block(self, blocker_user_id: int, blocked_user_id: int, reason: Optional[str] = None) -> bool:
        """
        Block a user.
        Returns True if block was created, False if already blocked.
        """
        blocker = str(blocker_user_id)
        blocked = str(blocked_user_id)
        
        if blocker == blocked:
            raise ValueError("Cannot block yourself")
        
        now = utc_now_iso()
        with get_db_session() as session:
            # Check if already blocked
            existing = session.execute(
                text("""
                    SELECT is_active FROM user_relationships
                    WHERE source_user_id = :source_user_id AND target_user_id = :target_user_id AND relationship_type = 'block'
                    LIMIT 1;
                """),
                {"source_user_id": blocker, "target_user_id": blocked},
            ).fetchone()
            
            metadata = {}
            if reason:
                metadata["reason"] = reason
            metadata_json = json.dumps(metadata) if metadata else None
            
            if existing:
                if int(existing[0]) == 1:
                    return False  # Already blocked
                # Reactivate if previously unblocked
                session.execute(
                    text("""
                        UPDATE user_relationships
                        SET is_active = 1, ended_at_utc = NULL, metadata = :metadata, created_at_utc = :created_at_utc, updated_at_utc = :updated_at_utc
                        WHERE source_user_id = :source_user_id AND target_user_id = :target_user_id AND relationship_type = 'block';
                    """),
                    {"metadata": metadata_json, "created_at_utc": now, "updated_at_utc": now, "source_user_id": blocker, "target_user_id": blocked},
                )
                return True
            
            # Create new block
            session.execute(
                text("""
                    INSERT INTO user_relationships(
                        source_user_id, target_user_id, relationship_type, is_active,
                        created_at_utc, updated_at_utc, metadata
                    ) VALUES (:source_user_id, :target_user_id, 'block', 1, :created_at_utc, :updated_at_utc, :metadata);
                """),
                {
                    "source_user_id": blocker,
                    "target_user_id": blocked,
                    "created_at_utc": now,
                    "updated_at_utc": now,
                    "metadata": metadata_json,
                },
            )
            return True

    def unblock(self, blocker_user_id: int, blocked_user_id: int) -> bool:
        """Remove a block (soft delete)."""
        blocker = str(blocker_user_id)
        blocked = str(blocked_user_id)
        
        now = utc_now_iso()
        with get_db_session() as session:
            result = session.execute(
                text("""
                    UPDATE user_relationships
                    SET is_active = 0, ended_at_utc = :ended_at_utc, updated_at_utc = :updated_at_utc
                    WHERE source_user_id = :source_user_id AND target_user_id = :target_user_id AND relationship_type = 'block' AND is_active = 1;
                """),
                {"ended_at_utc": now, "updated_at_utc": now, "source_user_id": blocker, "target_user_id": blocked},
            )
            return result.rowcount > 0

    def is_blocked(self, blocker_user_id: int, blocked_user_id: int) -> bool:
        """Check if blocker has blocked blocked user."""
        blocker = str(blocker_user_id)
        blocked = str(blocked_user_id)
        
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT 1 FROM user_relationships
                    WHERE source_user_id = :source_user_id AND target_user_id = :target_user_id AND relationship_type = 'block' AND is_active = 1
                    LIMIT 1;
                """),
                {"source_user_id": blocker, "target_user_id": blocked},
            ).fetchone()
            return bool(row)

    def are_blocked(self, user_id_1: int, user_id_2: int) -> bool:
        """Check if either user has blocked the other (bidirectional check)."""
        user1 = str(user_id_1)
        user2 = str(user_id_2)
        
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT 1 FROM user_relationships
                    WHERE ((source_user_id = :user1 AND target_user_id = :user2) OR
                           (source_user_id = :user2 AND target_user_id = :user1))
                    AND relationship_type = 'block' AND is_active = 1
                    LIMIT 1;
                """),
                {"user1": user1, "user2": user2},
            ).fetchone()
            return bool(row)

    def get_blocked_users(self, user_id: int) -> List[str]:
        """Get list of user IDs that this user has blocked."""
        user = str(user_id)
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT target_user_id FROM user_relationships
                    WHERE source_user_id = :source_user_id AND relationship_type = 'block' AND is_active = 1
                    ORDER BY created_at_utc DESC;
                """),
                {"source_user_id": user},
            ).fetchall()
            return [str(row[0]) for row in rows]

