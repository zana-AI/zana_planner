import uuid
import json
from typing import List, Optional, Dict, Any
from datetime import datetime

from db.sqlite_db import connection_for_root, utc_now_iso, dt_from_utc_iso, json_compat


class FeedRepository:
    """Repository for managing feed items (actions, sessions, milestones)."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def create_feed_item(
        self,
        actor_user_id: int,
        visibility: str,
        title: Optional[str] = None,
        body: Optional[str] = None,
        action_uuid: Optional[str] = None,
        session_id: Optional[str] = None,
        milestone_uuid: Optional[str] = None,
        promise_uuid: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        dedupe_key: Optional[str] = None,
    ) -> str:
        """
        Create a feed item.
        Returns the feed_item_uuid.
        """
        actor = str(actor_user_id)
        now = utc_now_iso()
        feed_item_uuid = str(uuid.uuid4())
        
        context_json = json.dumps(context or {}, ensure_ascii=False)
        
        with connection_for_root(self.root_dir) as conn:
            conn.execute(
                """
                INSERT INTO feed_items(
                    feed_item_uuid, actor_user_id, created_at_utc, visibility,
                    title, body, action_uuid, session_id, milestone_uuid,
                    promise_uuid, context_json, dedupe_key, is_deleted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0);
                """,
                (
                    feed_item_uuid,
                    actor,
                    now,
                    visibility,
                    title,
                    body,
                    action_uuid,
                    session_id,
                    milestone_uuid,
                    promise_uuid,
                    context_json,
                    dedupe_key,
                ),
            )
        return feed_item_uuid

    def get_feed_item(self, feed_item_uuid: str) -> Optional[Dict[str, Any]]:
        """Get a feed item by UUID."""
        with connection_for_root(self.root_dir) as conn:
            row = conn.execute(
                """
                SELECT * FROM feed_items
                WHERE feed_item_uuid = ? AND is_deleted = 0
                LIMIT 1;
                """,
                (feed_item_uuid,),
            ).fetchone()
            
            if not row:
                return None
            
            result = dict(row)
            # Parse context_json
            try:
                result["context"] = json.loads(result.get("context_json") or "{}")
            except Exception:
                result["context"] = {}
            return result

    def list_feed_items(
        self,
        viewer_user_id: int,
        limit: int = 50,
        since: Optional[datetime] = None,
        actor_user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        List feed items visible to viewer.
        This is a simplified version - full implementation would check:
        - visibility rules (private/followers/clubs/public)
        - block relationships
        - mute relationships (for following feed)
        """
        viewer = str(viewer_user_id)
        since_utc = utc_now_iso() if since is None else utc_now_iso()
        
        with connection_for_root(self.root_dir) as conn:
            if actor_user_id:
                # Filter by specific actor
                rows = conn.execute(
                    """
                    SELECT * FROM feed_items
                    WHERE actor_user_id = ? AND created_at_utc >= ? AND is_deleted = 0
                    ORDER BY created_at_utc DESC
                    LIMIT ?;
                    """,
                    (str(actor_user_id), since_utc, limit),
                ).fetchall()
            else:
                # Get all visible items (simplified - would need visibility logic)
                rows = conn.execute(
                    """
                    SELECT * FROM feed_items
                    WHERE created_at_utc >= ? AND is_deleted = 0
                    ORDER BY created_at_utc DESC
                    LIMIT ?;
                    """,
                    (since_utc, limit),
                ).fetchall()
            
            results = []
            for row in rows:
                item = dict(row)
                try:
                    item["context"] = json.loads(item.get("context_json") or "{}")
                except Exception:
                    item["context"] = {}
                results.append(item)
            
            return results

    def delete_feed_item(self, feed_item_uuid: str, actor_user_id: int) -> bool:
        """Soft delete a feed item (only by the actor)."""
        actor = str(actor_user_id)
        with connection_for_root(self.root_dir) as conn:
            result = conn.execute(
                """
                UPDATE feed_items
                SET is_deleted = 1
                WHERE feed_item_uuid = ? AND actor_user_id = ?;
                """,
                (feed_item_uuid, actor),
            )
            return result.rowcount > 0

