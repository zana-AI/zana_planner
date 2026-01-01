from typing import List, Optional
from datetime import datetime
import json

from db.sqlite_db import connection_for_root, utc_now_iso


class MutesRepository:
    """Repository for managing user mute relationships."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def mute(self, muter_user_id: int, muted_user_id: int, scope: str = "all") -> bool:
        """
        Mute a user.
        Returns True if mute was created, False if already muted.
        scope: 'all' | 'reactions' | 'feed' (future use)
        """
        muter = str(muter_user_id)
        muted = str(muted_user_id)
        
        if muter == muted:
            raise ValueError("Cannot mute yourself")
        
        now = utc_now_iso()
        with connection_for_root(self.root_dir) as conn:
            # Check if already muted
            existing = conn.execute(
                """
                SELECT is_active FROM user_relationships
                WHERE source_user_id = ? AND target_user_id = ? AND relationship_type = 'mute'
                LIMIT 1;
                """,
                (muter, muted),
            ).fetchone()
            
            metadata = {"scope": scope}
            metadata_json = json.dumps(metadata)
            
            if existing:
                if int(existing["is_active"]) == 1:
                    return False  # Already muted
                # Reactivate if previously unmuted
                conn.execute(
                    """
                    UPDATE user_relationships
                    SET is_active = 1, ended_at_utc = NULL, metadata = ?, created_at_utc = ?, updated_at_utc = ?
                    WHERE source_user_id = ? AND target_user_id = ? AND relationship_type = 'mute';
                    """,
                    (metadata_json, now, now, muter, muted),
                )
                return True
            
            # Create new mute
            conn.execute(
                """
                INSERT INTO user_relationships(
                    source_user_id, target_user_id, relationship_type, is_active,
                    created_at_utc, updated_at_utc, metadata
                ) VALUES (?, ?, 'mute', 1, ?, ?, ?);
                """,
                (muter, muted, now, now, metadata_json),
            )
            return True

    def unmute(self, muter_user_id: int, muted_user_id: int) -> bool:
        """Remove a mute (soft delete)."""
        muter = str(muter_user_id)
        muted = str(muted_user_id)
        
        now = utc_now_iso()
        with connection_for_root(self.root_dir) as conn:
            result = conn.execute(
                """
                UPDATE user_relationships
                SET is_active = 0, ended_at_utc = ?, updated_at_utc = ?
                WHERE source_user_id = ? AND target_user_id = ? AND relationship_type = 'mute' AND is_active = 1;
                """,
                (now, now, muter, muted),
            )
            return result.rowcount > 0

    def is_muted(self, muter_user_id: int, muted_user_id: int) -> bool:
        """Check if muter has muted muted user."""
        muter = str(muter_user_id)
        muted = str(muted_user_id)
        
        with connection_for_root(self.root_dir) as conn:
            row = conn.execute(
                """
                SELECT 1 FROM user_relationships
                WHERE source_user_id = ? AND target_user_id = ? AND relationship_type = 'mute' AND is_active = 1
                LIMIT 1;
                """,
                (muter, muted),
            ).fetchone()
            return bool(row)

    def get_muted_users(self, user_id: int) -> List[str]:
        """Get list of user IDs that this user has muted."""
        user = str(user_id)
        with connection_for_root(self.root_dir) as conn:
            rows = conn.execute(
                """
                SELECT target_user_id FROM user_relationships
                WHERE source_user_id = ? AND relationship_type = 'mute' AND is_active = 1
                ORDER BY created_at_utc DESC;
                """,
                (user,),
            ).fetchall()
            return [str(row["target_user_id"]) for row in rows]

