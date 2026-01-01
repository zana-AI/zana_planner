from typing import List, Optional
from datetime import datetime
import json

from db.sqlite_db import connection_for_root, utc_now_iso


class BlocksRepository:
    """Repository for managing user block relationships."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

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
        with connection_for_root(self.root_dir) as conn:
            # Check if already blocked
            existing = conn.execute(
                """
                SELECT is_active FROM user_relationships
                WHERE source_user_id = ? AND target_user_id = ? AND relationship_type = 'block'
                LIMIT 1;
                """,
                (blocker, blocked),
            ).fetchone()
            
            metadata = {}
            if reason:
                metadata["reason"] = reason
            metadata_json = json.dumps(metadata) if metadata else None
            
            if existing:
                if int(existing["is_active"]) == 1:
                    return False  # Already blocked
                # Reactivate if previously unblocked
                conn.execute(
                    """
                    UPDATE user_relationships
                    SET is_active = 1, ended_at_utc = NULL, metadata = ?, created_at_utc = ?, updated_at_utc = ?
                    WHERE source_user_id = ? AND target_user_id = ? AND relationship_type = 'block';
                    """,
                    (metadata_json, now, now, blocker, blocked),
                )
                return True
            
            # Create new block
            conn.execute(
                """
                INSERT INTO user_relationships(
                    source_user_id, target_user_id, relationship_type, is_active,
                    created_at_utc, updated_at_utc, metadata
                ) VALUES (?, ?, 'block', 1, ?, ?, ?);
                """,
                (blocker, blocked, now, now, metadata_json),
            )
            return True

    def unblock(self, blocker_user_id: int, blocked_user_id: int) -> bool:
        """Remove a block (soft delete)."""
        blocker = str(blocker_user_id)
        blocked = str(blocked_user_id)
        
        now = utc_now_iso()
        with connection_for_root(self.root_dir) as conn:
            result = conn.execute(
                """
                UPDATE user_relationships
                SET is_active = 0, ended_at_utc = ?, updated_at_utc = ?
                WHERE source_user_id = ? AND target_user_id = ? AND relationship_type = 'block' AND is_active = 1;
                """,
                (now, now, blocker, blocked),
            )
            return result.rowcount > 0

    def is_blocked(self, blocker_user_id: int, blocked_user_id: int) -> bool:
        """Check if blocker has blocked blocked user."""
        blocker = str(blocker_user_id)
        blocked = str(blocked_user_id)
        
        with connection_for_root(self.root_dir) as conn:
            row = conn.execute(
                """
                SELECT 1 FROM user_relationships
                WHERE source_user_id = ? AND target_user_id = ? AND relationship_type = 'block' AND is_active = 1
                LIMIT 1;
                """,
                (blocker, blocked),
            ).fetchone()
            return bool(row)

    def are_blocked(self, user_id_1: int, user_id_2: int) -> bool:
        """Check if either user has blocked the other (bidirectional check)."""
        user1 = str(user_id_1)
        user2 = str(user_id_2)
        
        with connection_for_root(self.root_dir) as conn:
            row = conn.execute(
                """
                SELECT 1 FROM user_relationships
                WHERE ((source_user_id = ? AND target_user_id = ?) OR
                       (source_user_id = ? AND target_user_id = ?))
                AND relationship_type = 'block' AND is_active = 1
                LIMIT 1;
                """,
                (user1, user2, user2, user1),
            ).fetchone()
            return bool(row)

    def get_blocked_users(self, user_id: int) -> List[str]:
        """Get list of user IDs that this user has blocked."""
        user = str(user_id)
        with connection_for_root(self.root_dir) as conn:
            rows = conn.execute(
                """
                SELECT target_user_id FROM user_relationships
                WHERE source_user_id = ? AND relationship_type = 'block' AND is_active = 1
                ORDER BY created_at_utc DESC;
                """,
                (user,),
            ).fetchall()
            return [str(row["target_user_id"]) for row in rows]

