"""
Conversation repository for storing user-bot conversation history.
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta

from db.sqlite_db import connection_for_root, utc_now_iso, dt_from_utc_iso
from utils.logger import get_logger

logger = get_logger(__name__)


class ConversationRepository:
    """Repository for managing conversation history."""
    
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
    
    def save_message(
        self,
        user_id: int,
        message_type: str,  # 'user' or 'bot'
        content: str,
        message_id: Optional[int] = None,
        chat_id: Optional[int] = None,
    ) -> None:
        """
        Save a message to conversation history.
        
        Args:
            user_id: User ID
            message_type: 'user' or 'bot'
            content: Message content
            message_id: Telegram message ID (optional)
            chat_id: Telegram chat ID (optional)
        """
        try:
            with connection_for_root(self.root_dir) as conn:
                conn.execute(
                    """
                    INSERT INTO conversations (
                        user_id, chat_id, message_id, message_type, content, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(user_id),
                        str(chat_id) if chat_id else None,
                        message_id,
                        message_type,
                        content,
                        utc_now_iso(),
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to save conversation message for user {user_id}: {e}")
    
    def update_message_id(
        self,
        user_id: int,
        message_id: int,
    ) -> None:
        """
        Update the message_id for the most recent conversation entry for a user.
        Used when message_id is not available at save time.
        
        Args:
            user_id: User ID
            message_id: Telegram message ID
        """
        try:
            with connection_for_root(self.root_dir) as conn:
                conn.execute(
                    """
                    UPDATE conversations 
                    SET message_id = ? 
                    WHERE user_id = ? AND message_id IS NULL 
                    ORDER BY created_at_utc DESC LIMIT 1
                    """,
                    (message_id, str(user_id)),
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to update message_id for user {user_id}: {e}")
    
    def get_recent_history(
        self,
        user_id: int,
        limit: int = 50,
        message_type: Optional[str] = None,
    ) -> List[Dict[str, any]]:
        """
        Get recent conversation history for a user.
        
        Args:
            user_id: User ID
            limit: Maximum number of messages to return
            message_type: Filter by message type ('user' or 'bot'), or None for all
        
        Returns:
            List of conversation messages as dictionaries
        """
        try:
            with connection_for_root(self.root_dir) as conn:
                if message_type:
                    rows = conn.execute(
                        """
                        SELECT id, user_id, chat_id, message_id, message_type, content, created_at_utc
                        FROM conversations
                        WHERE user_id = ? AND message_type = ?
                        ORDER BY created_at_utc DESC
                        LIMIT ?
                        """,
                        (str(user_id), message_type, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT id, user_id, chat_id, message_id, message_type, content, created_at_utc
                        FROM conversations
                        WHERE user_id = ?
                        ORDER BY created_at_utc DESC
                        LIMIT ?
                        """,
                        (str(user_id), limit),
                    ).fetchall()
                
                return [
                    {
                        "id": row["id"],
                        "user_id": row["user_id"],
                        "chat_id": row["chat_id"],
                        "message_id": row["message_id"],
                        "message_type": row["message_type"],
                        "content": row["content"],
                        "created_at_utc": row["created_at_utc"],
                        "created_at": dt_from_utc_iso(row["created_at_utc"]),
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.warning(f"Failed to get conversation history for user {user_id}: {e}")
            return []
    
    def cleanup_old_messages(self, days: int = 30) -> int:
        """
        Delete conversation messages older than specified days.
        
        Args:
            days: Number of days to keep messages
        
        Returns:
            Number of messages deleted
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            cutoff_iso = cutoff_date.isoformat().replace("+00:00", "Z")
            
            with connection_for_root(self.root_dir) as conn:
                cursor = conn.execute(
                    """
                    DELETE FROM conversations
                    WHERE created_at_utc < ?
                    """,
                    (cutoff_iso,),
                )
                deleted_count = cursor.rowcount
                conn.commit()
                logger.info(f"Cleaned up {deleted_count} conversation messages older than {days} days")
                return deleted_count
        except Exception as e:
            logger.warning(f"Failed to cleanup old conversation messages: {e}")
            return 0

