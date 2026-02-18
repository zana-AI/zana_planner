"""
Conversation repository for storing user-bot conversation history.
"""

import re
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso, dt_from_utc_iso
from utils.logger import get_logger

logger = get_logger(__name__)


class ConversationRepository:
    """Repository for managing conversation history."""

    SESSION_GAP_MINUTES = 30
    _SESSION_ID_RE = re.compile(r"^s-(\d{8}T\d{6}Z)-[0-9a-f]{8}$")

    def __init__(self) -> None:
        self._session_column_available: Optional[bool] = None

    @staticmethod
    def _is_duplicate_insert_error(error_str: str) -> bool:
        return (
            "uniqueviolation" in error_str
            or "duplicate key" in error_str
            or "conversations_pkey" in error_str
        )

    @staticmethod
    def _is_missing_session_column_error(error_str: str) -> bool:
        return (
            "conversation_session_id" in error_str
            and ("undefinedcolumn" in error_str or "does not exist" in error_str)
        )

    @staticmethod
    def _ensure_utc(ts: Optional[datetime]) -> datetime:
        if ts is None:
            return datetime.now(timezone.utc)
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)

    @classmethod
    def _build_time_tagged_session_id(cls, session_start: Optional[datetime]) -> str:
        ts = cls._ensure_utc(session_start)
        return f"s-{ts.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"

    @classmethod
    def _extract_session_time_tag_utc(cls, session_id: Optional[str]) -> Optional[str]:
        if not session_id:
            return None
        match = cls._SESSION_ID_RE.match(str(session_id).strip())
        if not match:
            return None
        raw = match.group(1)  # YYYYMMDDTHHMMSSZ
        try:
            dt = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except Exception:
            return None

    @staticmethod
    def _compact_summary_text(content: str) -> str:
        return " ".join((content or "").split())

    def _has_conversation_session_column(self, session) -> bool:
        """Cache whether conversations.conversation_session_id exists."""
        if self._session_column_available is not None:
            return self._session_column_available
        try:
            exists = bool(
                session.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'conversations'
                              AND column_name = 'conversation_session_id'
                        )
                        """
                    )
                ).scalar()
            )
            self._session_column_available = exists
            return exists
        except Exception as e:
            logger.warning(f"Could not inspect conversation session column: {e}")
            self._session_column_available = False
            return False

    def _resolve_session_id_for_message(
        self,
        session,
        user_id: int,
        message_timestamp: datetime,
    ) -> Optional[str]:
        """
        Resolve session_id for a new message using time-gap logic.
        If previous message had no session_id, opportunistically backfill it.
        """
        if not self._has_conversation_session_column(session):
            return None
        try:
            row = session.execute(
                text(
                    """
                    SELECT id, conversation_session_id, created_at_utc
                    FROM conversations
                    WHERE user_id = :user_id
                    ORDER BY created_at_utc DESC
                    LIMIT 1
                    """
                ),
                {"user_id": str(user_id)},
            ).fetchone()
            if not row:
                return self._build_time_tagged_session_id(message_timestamp)

            last_id, last_session_id, last_created_at_utc = row[0], row[1], row[2]
            last_dt = dt_from_utc_iso(last_created_at_utc)
            if not last_dt:
                return self._build_time_tagged_session_id(message_timestamp)

            current_ts = self._ensure_utc(message_timestamp)
            last_ts = self._ensure_utc(last_dt)
            gap_minutes = (current_ts - last_ts).total_seconds() / 60
            if gap_minutes > self.SESSION_GAP_MINUTES:
                return self._build_time_tagged_session_id(current_ts)

            if last_session_id:
                return str(last_session_id)

            # Backfill previous message for continuity if possible.
            generated_session_id = self._build_time_tagged_session_id(last_ts)
            try:
                session.execute(
                    text(
                        """
                        UPDATE conversations
                        SET conversation_session_id = :session_id
                        WHERE id = :id
                          AND conversation_session_id IS NULL
                        """
                    ),
                    {"session_id": generated_session_id, "id": last_id},
                )
            except Exception as backfill_error:
                logger.debug(
                    "Failed to backfill conversation_session_id for id "
                    f"{last_id}: {backfill_error}"
                )
            return generated_session_id
        except Exception as e:
            logger.warning(f"Failed to resolve conversation session for user {user_id}: {e}")
            return self._build_time_tagged_session_id(message_timestamp)

    @staticmethod
    def _insert_message_row(session, payload: Dict[str, Any], include_session_column: bool) -> None:
        if include_session_column:
            session.execute(
                text(
                    """
                    INSERT INTO conversations (
                        user_id, chat_id, message_id, message_type, content, created_at_utc, conversation_session_id
                    ) VALUES (
                        :user_id, :chat_id, :message_id, :message_type, :content, :created_at_utc, :conversation_session_id
                    )
                    """
                ),
                payload,
            )
            return
        session.execute(
            text(
                """
                INSERT INTO conversations (
                    user_id, chat_id, message_id, message_type, content, created_at_utc
                ) VALUES (
                    :user_id, :chat_id, :message_id, :message_type, :content, :created_at_utc
                )
                """
            ),
            payload,
        )

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
                created_at_utc = utc_now_iso()
                created_at_dt = dt_from_utc_iso(created_at_utc) or datetime.now(timezone.utc)
                include_session_column = self._has_conversation_session_column(session)
                session_id = None
                if include_session_column:
                    session_id = self._resolve_session_id_for_message(
                        session=session,
                        user_id=user_id,
                        message_timestamp=created_at_dt,
                    )

                payload: Dict[str, Any] = {
                    "user_id": str(user_id),
                    "chat_id": str(chat_id) if chat_id else None,
                    "message_id": message_id,
                    "message_type": message_type,
                    "content": content,
                    "created_at_utc": created_at_utc,
                    "conversation_session_id": session_id,
                }

                sequence_fix_attempted = False
                while True:
                    try:
                        self._insert_message_row(
                            session=session,
                            payload=payload,
                            include_session_column=include_session_column,
                        )
                        break
                    except Exception as insert_error:
                        error_str = str(insert_error).lower()

                        if include_session_column and self._is_missing_session_column_error(error_str):
                            # Handle stale schema gracefully.
                            self._session_column_available = False
                            include_session_column = False
                            continue

                        if self._is_duplicate_insert_error(error_str):
                            if sequence_fix_attempted:
                                logger.warning(
                                    f"Failed to save conversation message after sequence fix for user {user_id}: "
                                    f"{insert_error}"
                                )
                                session.rollback()
                                break
                            sequence_fix_attempted = True
                            logger.warning("Sequence out of sync for conversations table, fixing...")
                            try:
                                session.execute(
                                    text(
                                        """
                                        SELECT setval(
                                            'conversations_id_seq',
                                            GREATEST((SELECT COALESCE(MAX(id), 0) FROM conversations), 1),
                                            false
                                        )
                                        """
                                    )
                                )
                                # Force commit the sequence fix before retrying insert.
                                session.commit()
                            except Exception as seq_fix_error:
                                logger.warning(
                                    "Failed to fix conversations sequence for user "
                                    f"{user_id}: {seq_fix_error}"
                                )
                                session.rollback()
                                break
                            continue

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
    ) -> List[Dict[str, Any]]:
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
                include_session_column = self._has_conversation_session_column(session)
                select_fields = (
                    "id, user_id, chat_id, message_id, message_type, content, created_at_utc, conversation_session_id"
                    if include_session_column
                    else "id, user_id, chat_id, message_id, message_type, content, created_at_utc"
                )
                if message_type:
                    rows = session.execute(
                        text(
                            f"""
                            SELECT {select_fields}
                            FROM conversations
                            WHERE user_id = :user_id AND message_type = :message_type
                            ORDER BY created_at_utc DESC
                            LIMIT :limit
                            """
                        ),
                        {"user_id": str(user_id), "message_type": message_type, "limit": limit},
                    ).mappings().fetchall()
                else:
                    rows = session.execute(
                        text(
                            f"""
                            SELECT {select_fields}
                            FROM conversations
                            WHERE user_id = :user_id
                            ORDER BY created_at_utc DESC
                            LIMIT :limit
                            """
                        ),
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
                        "conversation_session_id": row.get("conversation_session_id"),
                        "conversation_session_time_tag_utc": self._extract_session_time_tag_utc(
                            row.get("conversation_session_id")
                        ),
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
            # Pull enough messages to reconstruct exchanges and preserve session boundaries.
            messages_desc = self.get_recent_history(user_id, limit=max(limit * 8, 24))
            if not messages_desc:
                return ""

            messages = list(reversed(messages_desc))  # Chronological

            # Build an effective session key for every message.
            synthetic_session_idx = 0
            last_seen_ts: Optional[datetime] = None
            session_start_by_key: Dict[str, datetime] = {}
            for msg in messages:
                msg_ts = msg.get("created_at") or dt_from_utc_iso(msg.get("created_at_utc"))
                raw_session_id = msg.get("conversation_session_id")
                if raw_session_id:
                    session_key = str(raw_session_id)
                else:
                    if (
                        last_seen_ts is None
                        or not msg_ts
                        or (self._ensure_utc(msg_ts) - self._ensure_utc(last_seen_ts)).total_seconds() / 60
                        > self.SESSION_GAP_MINUTES
                    ):
                        synthetic_session_idx += 1
                    session_key = f"legacy-session-{synthetic_session_idx}"
                msg["_session_key"] = session_key
                if msg_ts and session_key not in session_start_by_key:
                    session_start_by_key[session_key] = self._ensure_utc(msg_ts)
                if msg_ts:
                    last_seen_ts = msg_ts

            # Group chronological user->bot exchanges.
            exchanges: List[Dict[str, Any]] = []
            current_exchange: Optional[Dict[str, Any]] = None
            for msg in messages:
                mtype = msg.get("message_type")
                if mtype == "user":
                    if current_exchange:
                        exchanges.append(current_exchange)
                    session_key = msg["_session_key"]
                    current_exchange = {
                        "session_key": session_key,
                        "session_start": session_start_by_key.get(session_key),
                        "user": self._compact_summary_text(msg.get("content", "")),
                        "bot_parts": [],
                    }
                    continue
                if mtype == "bot" and current_exchange is not None:
                    current_exchange["bot_parts"].append(
                        self._compact_summary_text(msg.get("content", ""))
                    )

            if current_exchange:
                exchanges.append(current_exchange)
            if not exchanges:
                return ""

            recent_exchanges = exchanges[-limit:] if len(exchanges) > limit else exchanges
            lines = []
            last_session_key = None
            for exchange in recent_exchanges:
                session_key = exchange.get("session_key")
                if session_key and session_key != last_session_key:
                    session_start = exchange.get("session_start")
                    if isinstance(session_start, datetime):
                        session_label = self._ensure_utc(session_start).strftime("%Y-%m-%d %H:%M UTC")
                    else:
                        session_time_tag = self._extract_session_time_tag_utc(str(session_key))
                        session_start_dt = dt_from_utc_iso(session_time_tag) if session_time_tag else None
                        if session_start_dt:
                            session_label = session_start_dt.strftime("%Y-%m-%d %H:%M UTC")
                        else:
                            session_label = "Unknown UTC"
                    lines.append(f"[Session {session_label}]")
                    last_session_key = session_key

                lines.append(f"User: {exchange['user']}")
                bot_text = " ".join([p for p in exchange.get("bot_parts", []) if p]).strip()
                if bot_text:
                    lines.append(f"Bot: {bot_text}")
            
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
    
    def get_recent_history_by_importance(
        self,
        user_id: int,
        limit: int = 50,
        min_importance: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get recent conversation history prioritized by importance score.
        
        Args:
            user_id: User ID
            limit: Maximum number of messages to return
            min_importance: Minimum importance score (optional filter)
            session_id: Filter by conversation session (optional)
        
        Returns:
            List of conversation messages as dictionaries
        """
        try:
            with get_db_session() as session:
                has_session_column = self._has_conversation_session_column(session)
                query_parts = [
                    "SELECT id, user_id, chat_id, message_id, message_type, content, created_at_utc, importance_score, intent_category"
                ]
                if has_session_column:
                    query_parts[0] += ", conversation_session_id"
                query_parts.append("FROM conversations")
                query_parts.append("WHERE user_id = :user_id")
                
                params = {"user_id": str(user_id), "limit": limit}
                
                if min_importance is not None:
                    query_parts.append("AND (importance_score IS NULL OR importance_score >= :min_importance)")
                    params["min_importance"] = min_importance
                
                if session_id:
                    if not has_session_column:
                        return []
                    query_parts.append("AND conversation_session_id = :session_id")
                    params["session_id"] = session_id
                
                # Order by: current session first, then by importance score, then by time
                query_parts.append("ORDER BY created_at_utc DESC")
                query_parts.append("LIMIT :limit")
                
                query = text(" ".join(query_parts))
                
                rows = session.execute(query, params).mappings().fetchall()
                
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
                        "conversation_session_id": row.get("conversation_session_id"),
                        "conversation_session_time_tag_utc": self._extract_session_time_tag_utc(
                            row.get("conversation_session_id")
                        ),
                        "importance_score": row.get("importance_score"),
                        "intent_category": row.get("intent_category"),
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.warning(f"Failed to get conversation history by importance for user {user_id}: {e}")
            return []
