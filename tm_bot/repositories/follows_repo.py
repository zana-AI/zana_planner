from typing import List, Optional
from datetime import datetime
import json

from db.sqlite_db import connection_for_root, utc_now_iso, dt_from_utc_iso, dt_to_utc_iso


class FollowsRepository:
    """Repository for managing user follow relationships."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def follow(self, follower_user_id: int, followee_user_id: int) -> bool:
        """
        Create a follow relationship (auto-accept model).
        Returns True if follow was created, False if already exists.
        """
        follower = str(follower_user_id)
        followee = str(followee_user_id)
        
        if follower == followee:
            raise ValueError("Cannot follow yourself")
        
        now = utc_now_iso()
        with connection_for_root(self.root_dir) as conn:
            # Check if already following
            existing = conn.execute(
                """
                SELECT is_active FROM user_relationships
                WHERE source_user_id = ? AND target_user_id = ? AND relationship_type = 'follow'
                LIMIT 1;
                """,
                (follower, followee),
            ).fetchone()
            
            metadata = json.dumps({"notifications_enabled": True})
            
            if existing:
                if int(existing["is_active"]) == 1:
                    return False  # Already following
                # Reactivate if previously unfollowed
                conn.execute(
                    """
                    UPDATE user_relationships
                    SET is_active = 1, updated_at_utc = ?, ended_at_utc = NULL, metadata = ?
                    WHERE source_user_id = ? AND target_user_id = ? AND relationship_type = 'follow';
                    """,
                    (now, metadata, follower, followee),
                )
                return True
            
            # Create new follow
            conn.execute(
                """
                INSERT INTO user_relationships(
                    source_user_id, target_user_id, relationship_type, is_active,
                    created_at_utc, updated_at_utc, metadata
                ) VALUES (?, ?, 'follow', 1, ?, ?, ?);
                """,
                (follower, followee, now, now, metadata),
            )
            return True

    def unfollow(self, follower_user_id: int, followee_user_id: int) -> bool:
        """Remove a follow relationship (soft delete)."""
        follower = str(follower_user_id)
        followee = str(followee_user_id)
        
        now = utc_now_iso()
        with connection_for_root(self.root_dir) as conn:
            result = conn.execute(
                """
                UPDATE user_relationships
                SET is_active = 0, updated_at_utc = ?, ended_at_utc = ?
                WHERE source_user_id = ? AND target_user_id = ? AND relationship_type = 'follow' AND is_active = 1;
                """,
                (now, now, follower, followee),
            )
            return result.rowcount > 0

    def is_following(self, follower_user_id: int, followee_user_id: int) -> bool:
        """Check if follower is following followee."""
        follower = str(follower_user_id)
        followee = str(followee_user_id)
        
        with connection_for_root(self.root_dir) as conn:
            row = conn.execute(
                """
                SELECT 1 FROM user_relationships
                WHERE source_user_id = ? AND target_user_id = ? AND relationship_type = 'follow' AND is_active = 1
                LIMIT 1;
                """,
                (follower, followee),
            ).fetchone()
            return bool(row)

    def get_followers(self, user_id: int) -> List[str]:
        """Get list of user IDs that follow this user."""
        user = str(user_id)
        with connection_for_root(self.root_dir) as conn:
            rows = conn.execute(
                """
                SELECT source_user_id FROM user_relationships
                WHERE target_user_id = ? AND relationship_type = 'follow' AND is_active = 1
                ORDER BY created_at_utc DESC;
                """,
                (user,),
            ).fetchall()
            return [str(row["source_user_id"]) for row in rows]

    def get_following(self, user_id: int) -> List[str]:
        """Get list of user IDs that this user follows."""
        user = str(user_id)
        with connection_for_root(self.root_dir) as conn:
            rows = conn.execute(
                """
                SELECT target_user_id FROM user_relationships
                WHERE source_user_id = ? AND relationship_type = 'follow' AND is_active = 1
                ORDER BY created_at_utc DESC;
                """,
                (user,),
            ).fetchall()
            return [str(row["target_user_id"]) for row in rows]

    def get_follower_count(self, user_id: int) -> int:
        """Get count of followers for a user."""
        user = str(user_id)
        with connection_for_root(self.root_dir) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM user_relationships
                WHERE target_user_id = ? AND relationship_type = 'follow' AND is_active = 1;
                """,
                (user,),
            ).fetchone()
            return int(row["cnt"] or 0)

    def get_following_count(self, user_id: int) -> int:
        """Get count of users this user follows."""
        user = str(user_id)
        with connection_for_root(self.root_dir) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM user_relationships
                WHERE source_user_id = ? AND relationship_type = 'follow' AND is_active = 1;
                """,
                (user,),
            ).fetchone()
            return int(row["cnt"] or 0)

