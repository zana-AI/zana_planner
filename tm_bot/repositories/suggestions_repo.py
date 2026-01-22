"""Repository for promise suggestions between users."""
import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy import text
from db.postgres_db import get_db_session, utc_now_iso


class SuggestionsRepository:
    """Repository for promise suggestions."""

    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def create_suggestion(
        self,
        from_user_id: str,
        to_user_id: str,
        template_id: Optional[str] = None,
        freeform_text: Optional[str] = None,
        message: Optional[str] = None
    ) -> str:
        """Create a new promise suggestion.
        
        Returns the suggestion_id.
        """
        import json
        suggestion_id = str(uuid.uuid4())
        now = utc_now_iso()
        
        # Store freeform_text as draft_json (matching the DB schema)
        draft_json = None
        if freeform_text:
            draft_json = json.dumps({"freeform_text": freeform_text})
        
        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO promise_suggestions (
                        suggestion_id, from_user_id, to_user_id, status,
                        template_id, draft_json, message, created_at_utc
                    ) VALUES (
                        :suggestion_id, :from_user_id, :to_user_id, 'pending',
                        :template_id, :draft_json, :message, :created_at_utc
                    )
                """),
                {
                    "suggestion_id": suggestion_id,
                    "from_user_id": str(from_user_id),
                    "to_user_id": str(to_user_id),
                    "template_id": template_id,
                    "draft_json": draft_json,
                    "message": message,
                    "created_at_utc": now,
                }
            )
        
        return suggestion_id

    def get_suggestion(self, suggestion_id: str) -> Optional[Dict[str, Any]]:
        """Get a suggestion by ID."""
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT suggestion_id, from_user_id, to_user_id, status,
                           template_id, draft_json, message, created_at_utc, responded_at_utc
                    FROM promise_suggestions
                    WHERE suggestion_id = :suggestion_id
                """),
                {"suggestion_id": suggestion_id}
            ).fetchone()
        
        if not row:
            return None
        
        return dict(row._mapping)

    def get_pending_suggestions_for_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get pending suggestions sent to a user."""
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT s.suggestion_id, s.from_user_id, s.to_user_id, s.status,
                           s.template_id, s.draft_json, s.message, s.created_at_utc,
                           u.first_name, u.last_name, u.username,
                           t.title as template_title, t.emoji as template_emoji
                    FROM promise_suggestions s
                    LEFT JOIN users u ON s.from_user_id = u.user_id
                    LEFT JOIN promise_templates t ON s.template_id = t.template_id
                    WHERE s.to_user_id = :user_id AND s.status = 'pending'
                    ORDER BY s.created_at_utc DESC
                    LIMIT :limit
                """),
                {"user_id": str(user_id), "limit": limit}
            ).fetchall()
        
        return [dict(row._mapping) for row in rows]

    def get_suggestions_sent_by_user(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get suggestions sent by a user."""
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT s.suggestion_id, s.from_user_id, s.to_user_id, s.status,
                           s.template_id, s.draft_json, s.message, s.created_at_utc,
                           s.responded_at_utc,
                           u.first_name, u.last_name, u.username,
                           t.title as template_title, t.emoji as template_emoji
                    FROM promise_suggestions s
                    LEFT JOIN users u ON s.to_user_id = u.user_id
                    LEFT JOIN promise_templates t ON s.template_id = t.template_id
                    WHERE s.from_user_id = :user_id
                    ORDER BY s.created_at_utc DESC
                    LIMIT :limit
                """),
                {"user_id": str(user_id), "limit": limit}
            ).fetchall()
        
        return [dict(row._mapping) for row in rows]

    def update_suggestion_status(
        self,
        suggestion_id: str,
        new_status: str,
        user_id: str
    ) -> bool:
        """Update suggestion status. User must be the recipient.
        
        Returns True if updated, False if not found or not authorized.
        """
        now = utc_now_iso()
        
        with get_db_session() as session:
            result = session.execute(
                text("""
                    UPDATE promise_suggestions
                    SET status = :new_status, responded_at_utc = :responded_at
                    WHERE suggestion_id = :suggestion_id
                      AND to_user_id = :user_id
                      AND status = 'pending'
                """),
                {
                    "suggestion_id": suggestion_id,
                    "new_status": new_status,
                    "responded_at": now,
                    "user_id": str(user_id),
                }
            )
            return result.rowcount > 0

    def cancel_suggestion(self, suggestion_id: str, user_id: str) -> bool:
        """Cancel a suggestion. User must be the sender.
        
        Returns True if cancelled, False if not found or not authorized.
        """
        now = utc_now_iso()
        
        with get_db_session() as session:
            result = session.execute(
                text("""
                    UPDATE promise_suggestions
                    SET status = 'cancelled', responded_at_utc = :responded_at
                    WHERE suggestion_id = :suggestion_id
                      AND from_user_id = :user_id
                      AND status = 'pending'
                """),
                {
                    "suggestion_id": suggestion_id,
                    "responded_at": now,
                    "user_id": str(user_id),
                }
            )
            return result.rowcount > 0
