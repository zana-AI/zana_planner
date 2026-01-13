from typing import List, Optional
from datetime import datetime
import json

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso


class MutesRepository:
    """Repository for managing user mute relationships."""

    def __init__(self, root_dir: str = None):
        # root_dir kept for backward compatibility but not used for PostgreSQL
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
        with get_db_session() as session:
            # Check if already muted
            existing = session.execute(
                text("""
                    SELECT is_active FROM user_relationships
                    WHERE source_user_id = :source_user_id AND target_user_id = :target_user_id AND relationship_type = 'mute'
                    LIMIT 1;
                """),
                {"source_user_id": muter, "target_user_id": muted},
            ).fetchone()
            
            metadata = {"scope": scope}
            metadata_json = json.dumps(metadata)
            
            if existing:
                if int(existing[0]) == 1:
                    return False  # Already muted
                # Reactivate if previously unmuted
                session.execute(
                    text("""
                        UPDATE user_relationships
                        SET is_active = 1, ended_at_utc = NULL, metadata = :metadata, created_at_utc = :created_at_utc, updated_at_utc = :updated_at_utc
                        WHERE source_user_id = :source_user_id AND target_user_id = :target_user_id AND relationship_type = 'mute';
                    """),
                    {"metadata": metadata_json, "created_at_utc": now, "updated_at_utc": now, "source_user_id": muter, "target_user_id": muted},
                )
                return True
            
            # Create new mute
            session.execute(
                text("""
                    INSERT INTO user_relationships(
                        source_user_id, target_user_id, relationship_type, is_active,
                        created_at_utc, updated_at_utc, metadata
                    ) VALUES (:source_user_id, :target_user_id, 'mute', 1, :created_at_utc, :updated_at_utc, :metadata);
                """),
                {
                    "source_user_id": muter,
                    "target_user_id": muted,
                    "created_at_utc": now,
                    "updated_at_utc": now,
                    "metadata": metadata_json,
                },
            )
            return True

    def unmute(self, muter_user_id: int, muted_user_id: int) -> bool:
        """Remove a mute (soft delete)."""
        muter = str(muter_user_id)
        muted = str(muted_user_id)
        
        now = utc_now_iso()
        with get_db_session() as session:
            result = session.execute(
                text("""
                    UPDATE user_relationships
                    SET is_active = 0, ended_at_utc = :ended_at_utc, updated_at_utc = :updated_at_utc
                    WHERE source_user_id = :source_user_id AND target_user_id = :target_user_id AND relationship_type = 'mute' AND is_active = 1;
                """),
                {"ended_at_utc": now, "updated_at_utc": now, "source_user_id": muter, "target_user_id": muted},
            )
            return result.rowcount > 0

    def is_muted(self, muter_user_id: int, muted_user_id: int) -> bool:
        """Check if muter has muted muted user."""
        muter = str(muter_user_id)
        muted = str(muted_user_id)
        
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT 1 FROM user_relationships
                    WHERE source_user_id = :source_user_id AND target_user_id = :target_user_id AND relationship_type = 'mute' AND is_active = 1
                    LIMIT 1;
                """),
                {"source_user_id": muter, "target_user_id": muted},
            ).fetchone()
            return bool(row)

    def get_muted_users(self, user_id: int) -> List[str]:
        """Get list of user IDs that this user has muted."""
        user = str(user_id)
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT target_user_id FROM user_relationships
                    WHERE source_user_id = :source_user_id AND relationship_type = 'mute' AND is_active = 1
                    ORDER BY created_at_utc DESC;
                """),
                {"source_user_id": user},
            ).fetchall()
            return [str(row[0]) for row in rows]

