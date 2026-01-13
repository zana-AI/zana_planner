import uuid
from typing import List, Optional, Dict
from datetime import datetime

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso


class ReactionsRepository:
    """Repository for managing feed item reactions."""

    def __init__(self, root_dir: str = None):
        # root_dir kept for backward compatibility but not used for PostgreSQL
        self.root_dir = root_dir

    def add_reaction(
        self,
        feed_item_uuid: str,
        actor_user_id: int,
        reaction_type: str,
    ) -> str:
        """
        Add a reaction to a feed item.
        Returns the reaction_uuid.
        If reaction already exists, reactivates it.
        """
        actor = str(actor_user_id)
        now = utc_now_iso()
        
        with get_db_session() as session:
            # Check if reaction already exists
            existing = session.execute(
                text("""
                    SELECT reaction_uuid, is_deleted FROM feed_reactions
                    WHERE feed_item_uuid = :feed_item_uuid AND actor_user_id = :actor_user_id AND reaction_type = :reaction_type
                    LIMIT 1;
                """),
                {"feed_item_uuid": feed_item_uuid, "actor_user_id": actor, "reaction_type": reaction_type},
            ).fetchone()
            
            if existing:
                if int(existing["is_deleted"]) == 0:
                    return str(existing["reaction_uuid"])  # Already exists
                # Reactivate if previously deleted
                session.execute(
                    text("""
                        UPDATE feed_reactions
                        SET is_deleted = 0, created_at_utc = :created_at_utc
                        WHERE reaction_uuid = :reaction_uuid;
                    """),
                    {"created_at_utc": now, "reaction_uuid": existing["reaction_uuid"]},
                )
                return str(existing["reaction_uuid"])
            
            # Create new reaction
            reaction_uuid = str(uuid.uuid4())
            session.execute(
                text("""
                    INSERT INTO feed_reactions(
                        reaction_uuid, feed_item_uuid, actor_user_id,
                        reaction_type, created_at_utc, is_deleted
                    ) VALUES (:reaction_uuid, :feed_item_uuid, :actor_user_id, :reaction_type, :created_at_utc, 0);
                """),
                {
                    "reaction_uuid": reaction_uuid,
                    "feed_item_uuid": feed_item_uuid,
                    "actor_user_id": actor,
                    "reaction_type": reaction_type,
                    "created_at_utc": now,
                },
            )
            return reaction_uuid

    def remove_reaction(
        self,
        feed_item_uuid: str,
        actor_user_id: int,
        reaction_type: str,
    ) -> bool:
        """Remove a reaction (soft delete)."""
        actor = str(actor_user_id)
        with get_db_session() as session:
            result = session.execute(
                text("""
                    UPDATE feed_reactions
                    SET is_deleted = 1
                    WHERE feed_item_uuid = :feed_item_uuid AND actor_user_id = :actor_user_id AND reaction_type = :reaction_type AND is_deleted = 0;
                """),
                {"feed_item_uuid": feed_item_uuid, "actor_user_id": actor, "reaction_type": reaction_type},
            )
            return result.rowcount > 0

    def get_reactions(self, feed_item_uuid: str) -> List[Dict]:
        """Get all active reactions for a feed item."""
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT actor_user_id, reaction_type, created_at_utc
                    FROM feed_reactions
                    WHERE feed_item_uuid = :feed_item_uuid AND is_deleted = 0
                    ORDER BY created_at_utc DESC;
                """),
                {"feed_item_uuid": feed_item_uuid},
            ).fetchall()
            
            return [dict(row._mapping) for row in rows]

    def get_reaction_counts(self, feed_item_uuid: str) -> Dict[str, int]:
        """Get reaction counts by type for a feed item."""
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT reaction_type, COUNT(*) as cnt
                    FROM feed_reactions
                    WHERE feed_item_uuid = :feed_item_uuid AND is_deleted = 0
                    GROUP BY reaction_type;
                """),
                {"feed_item_uuid": feed_item_uuid},
            ).fetchall()
            
            return {str(row[0]): int(row[1]) for row in rows}

    def has_reacted(
        self,
        feed_item_uuid: str,
        actor_user_id: int,
        reaction_type: Optional[str] = None,
    ) -> bool:
        """Check if user has reacted to a feed item (optionally with specific type)."""
        actor = str(actor_user_id)
        with get_db_session() as session:
            if reaction_type:
                row = session.execute(
                    text("""
                        SELECT 1 FROM feed_reactions
                        WHERE feed_item_uuid = :feed_item_uuid AND actor_user_id = :actor_user_id 
                        AND reaction_type = :reaction_type AND is_deleted = 0
                        LIMIT 1;
                    """),
                    {"feed_item_uuid": feed_item_uuid, "actor_user_id": actor, "reaction_type": reaction_type},
                ).fetchone()
            else:
                row = session.execute(
                    text("""
                        SELECT 1 FROM feed_reactions
                        WHERE feed_item_uuid = :feed_item_uuid AND actor_user_id = :actor_user_id AND is_deleted = 0
                        LIMIT 1;
                    """),
                    {"feed_item_uuid": feed_item_uuid, "actor_user_id": actor},
                ).fetchone()
            return bool(row)

