"""
Conversation repository for storing user-bot conversation history.
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso, dt_from_utc_iso
from utils.logger import get_logger

logger = get_logger(__name__)


class ConversationRepository:
    """Repository for managing conversation history."""
    
    def __init__(self, root_dir: str = None):
        # root_dir kept for backward compatibility but not used for PostgreSQL
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
            with get_db_session() as session:
                # Try to insert the message
                try:
                    session.execute(
                        text("""
                            INSERT INTO conversations (
                                user_id, chat_id, message_id, message_type, content, created_at_utc
                            ) VALUES (:user_id, :chat_id, :message_id, :message_type, :content, :created_at_utc)
                        """),
                        {
                            "user_id": str(user_id),
                            "chat_id": str(chat_id) if chat_id else None,
                            "message_id": message_id,
                            "message_type": message_type,
                            "content": content,
                            "created_at_utc": utc_now_iso(),
                        },
                    )
                except Exception as insert_error:
                    # Check if it's a duplicate key error (sequence out of sync)
                    error_str = str(insert_error).lower()
                    if "uniqueviolation" in error_str or "duplicate key" in error_str or "conversations_pkey" in error_str:
                        # Fix the sequence and retry
                        logger.warning(f"Sequence out of sync for conversations table, fixing...")
                        try:
                            # Fix sequence (this will be committed by the context manager)
                            session.execute(
                                text("""
                                    SELECT setval('conversations_id_seq', 
                                        GREATEST((SELECT COALESCE(MAX(id), 0) FROM conversations), 1), 
                                        false)
                                """)
                            )
                            # Force commit the sequence fix before retrying
                            session.commit()
                            logger.info("Fixed conversations sequence, retrying insert...")
                            
                            # Retry the insert
                            session.execute(
                                text("""
                                    INSERT INTO conversations (
                                        user_id, chat_id, message_id, message_type, content, created_at_utc
                                    ) VALUES (:user_id, :chat_id, :message_id, :message_type, :content, :created_at_utc)
                                """),
                                {
                                    "user_id": str(user_id),
                                    "chat_id": str(chat_id) if chat_id else None,
                                    "message_id": message_id,
                                    "message_type": message_type,
                                    "content": content,
                                    "created_at_utc": utc_now_iso(),
                                },
                            )
                        except Exception as retry_error:
                            logger.warning(f"Failed to save conversation message after sequence fix for user {user_id}: {retry_error}")
                            # Rollback to avoid committing partial state
                            session.rollback()
                    else:
                        # Re-raise if it's a different error
                        raise
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
            with get_db_session() as session:
                session.execute(
                    text("""
                        WITH target AS (
                            SELECT id
                            FROM conversations
                            WHERE user_id = :user_id AND message_id IS NULL
                            ORDER BY created_at_utc DESC
                            LIMIT 1
                        )
                        UPDATE conversations
                        SET message_id = :message_id
                        WHERE id IN (SELECT id FROM target)
                    """),
                    {"message_id": message_id, "user_id": str(user_id)},
                )
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
            with get_db_session() as session:
                if message_type:
                    rows = session.execute(
                        text("""
                            SELECT id, user_id, chat_id, message_id, message_type, content, created_at_utc
                            FROM conversations
                            WHERE user_id = :user_id AND message_type = :message_type
                            ORDER BY created_at_utc DESC
                            LIMIT :limit
                        """),
                        {"user_id": str(user_id), "message_type": message_type, "limit": limit},
                    ).mappings().fetchall()
                else:
                    rows = session.execute(
                        text("""
                            SELECT id, user_id, chat_id, message_id, message_type, content, created_at_utc
                            FROM conversations
                            WHERE user_id = :user_id
                            ORDER BY created_at_utc DESC
                            LIMIT :limit
                        """),
                        {"user_id": str(user_id), "limit": limit},
                    ).mappings().fetchall()
                
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
    
    def get_recent_conversation_summary(self, user_id: int, limit: int = 3) -> str:
        """
        Get recent conversation summary for context injection.
        Returns formatted string with last N exchanges (user + bot pairs).
        
        Args:
            user_id: User ID
            limit: Number of exchanges to return (default: 3)
        
        Returns:
            Formatted conversation summary string
        """
        try:
            # Get last 2*limit messages (limit exchanges = limit user + limit bot messages)
            messages = self.get_recent_history(user_id, limit=limit * 2)
            
            if not messages:
                return ""
            
            # Group into exchanges (user message followed by bot response)
            exchanges = []
            i = 0
            while i < len(messages):
                if messages[i]["message_type"] == "user":
                    user_msg = messages[i]["content"]
                    # Look for bot response after this
                    bot_msg = None
                    if i + 1 < len(messages) and messages[i + 1]["message_type"] == "bot":
                        bot_msg = messages[i + 1]["content"]
                        i += 2
                    else:
                        i += 1
                    
                    exchanges.append({"user": user_msg, "bot": bot_msg})
                else:
                    i += 1
            
            # Format as conversation summary
            if not exchanges:
                return ""
            
            # Take last N exchanges
            recent_exchanges = exchanges[-limit:] if len(exchanges) > limit else exchanges
            
            lines = []
            for exchange in recent_exchanges:
                lines.append(f"User: {exchange['user']}")
                if exchange['bot']:
                    lines.append(f"Bot: {exchange['bot']}")
            
            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"Failed to get conversation summary for user {user_id}: {e}")
            return ""
    
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
            
            with get_db_session() as session:
                result = session.execute(
                    text("""
                        DELETE FROM conversations
                        WHERE created_at_utc < :cutoff_iso
                    """),
                    {"cutoff_iso": cutoff_iso},
                )
                deleted_count = result.rowcount
                logger.info(f"Cleaned up {deleted_count} conversation messages older than {days} days")
                return deleted_count
        except Exception as e:
            logger.warning(f"Failed to cleanup old conversation messages: {e}")
            return 0

