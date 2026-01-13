from typing import List, Optional
from datetime import datetime
import json

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso, dt_from_utc_iso, dt_to_utc_iso


class FollowsRepository:
    """Repository for managing user follow relationships."""

    def __init__(self, root_dir: str = None):
        # root_dir kept for backward compatibility but not used for PostgreSQL
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
        with get_db_session() as session:
            # Check if already following
            existing = session.execute(
                text("""
                    SELECT is_active FROM user_relationships
                    WHERE source_user_id = :source_user_id AND target_user_id = :target_user_id AND relationship_type = 'follow'
                    LIMIT 1;
                """),
                {"source_user_id": follower, "target_user_id": followee},
            ).fetchone()
            
            metadata = json.dumps({"notifications_enabled": True})
            
            if existing:
                if int(existing[0]) == 1:
                    return False  # Already following
                # Reactivate if previously unfollowed
                session.execute(
                    text("""
                        UPDATE user_relationships
                        SET is_active = 1, updated_at_utc = :updated_at_utc, ended_at_utc = NULL, metadata = :metadata
                        WHERE source_user_id = :source_user_id AND target_user_id = :target_user_id AND relationship_type = 'follow';
                    """),
                    {"updated_at_utc": now, "metadata": metadata, "source_user_id": follower, "target_user_id": followee},
                )
                return True
            
            # Create new follow
            session.execute(
                text("""
                    INSERT INTO user_relationships(
                        source_user_id, target_user_id, relationship_type, is_active,
                        created_at_utc, updated_at_utc, metadata
                    ) VALUES (:source_user_id, :target_user_id, 'follow', 1, :created_at_utc, :updated_at_utc, :metadata);
                """),
                {
                    "source_user_id": follower,
                    "target_user_id": followee,
                    "created_at_utc": now,
                    "updated_at_utc": now,
                    "metadata": metadata,
                },
            )
            return True

    def unfollow(self, follower_user_id: int, followee_user_id: int) -> bool:
        """Remove a follow relationship (soft delete)."""
        follower = str(follower_user_id)
        followee = str(followee_user_id)
        
        now = utc_now_iso()
        with get_db_session() as session:
            result = session.execute(
                text("""
                    UPDATE user_relationships
                    SET is_active = 0, updated_at_utc = :updated_at_utc, ended_at_utc = :ended_at_utc
                    WHERE source_user_id = :source_user_id AND target_user_id = :target_user_id AND relationship_type = 'follow' AND is_active = 1;
                """),
                {"updated_at_utc": now, "ended_at_utc": now, "source_user_id": follower, "target_user_id": followee},
            )
            return result.rowcount > 0

    def is_following(self, follower_user_id: int, followee_user_id: int) -> bool:
        """Check if follower is following followee."""
        follower = str(follower_user_id)
        followee = str(followee_user_id)
        
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT 1 FROM user_relationships
                    WHERE source_user_id = :source_user_id AND target_user_id = :target_user_id AND relationship_type = 'follow' AND is_active = 1
                    LIMIT 1;
                """),
                {"source_user_id": follower, "target_user_id": followee},
            ).fetchone()
            return bool(row)

    def get_followers(self, user_id: int) -> List[str]:
        """Get list of user IDs that follow this user."""
        user = str(user_id)
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT source_user_id FROM user_relationships
                    WHERE target_user_id = :target_user_id AND relationship_type = 'follow' AND is_active = 1
                    ORDER BY created_at_utc DESC;
                """),
                {"target_user_id": user},
            ).fetchall()
            return [str(row[0]) for row in rows]

    def get_following(self, user_id: int) -> List[str]:
        """Get list of user IDs that this user follows."""
        user = str(user_id)
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT target_user_id FROM user_relationships
                    WHERE source_user_id = :source_user_id AND relationship_type = 'follow' AND is_active = 1
                    ORDER BY created_at_utc DESC;
                """),
                {"source_user_id": user},
            ).fetchall()
            return [str(row[0]) for row in rows]

    def get_follower_count(self, user_id: int) -> int:
        """Get count of followers for a user."""
        user = str(user_id)
        with get_db_session() as session:
            count = session.execute(
                text("""
                    SELECT COUNT(*) FROM user_relationships
                    WHERE target_user_id = :target_user_id AND relationship_type = 'follow' AND is_active = 1;
                """),
                {"target_user_id": user},
            ).scalar()
            return int(count or 0)

    def get_following_count(self, user_id: int) -> int:
        """Get count of users this user follows."""
        user = str(user_id)
        with get_db_session() as session:
            count = session.execute(
                text("""
                    SELECT COUNT(*) FROM user_relationships
                    WHERE source_user_id = :source_user_id AND relationship_type = 'follow' AND is_active = 1;
                """),
                {"source_user_id": user},
            ).scalar()
            return int(count or 0)

