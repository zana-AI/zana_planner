"""
Repository for managing bot tokens.
"""
from typing import List, Optional
import uuid

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso, check_table_exists
from utils.logger import get_logger


logger = get_logger(__name__)


class BotTokensRepository:
    """Repository for managing bot tokens."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def _has_bot_tokens_table(session) -> bool:
        """Return True when the optional bot_tokens table exists."""
        return check_table_exists(session, "bot_tokens")

    def create_bot_token(
        self,
        bot_token: str,
        bot_username: Optional[str] = None,
        description: Optional[str] = None,
        is_active: bool = True,
    ) -> str:
        """
        Create a new bot token entry.
        
        Args:
            bot_token: The Telegram bot API token
            bot_username: Bot username (e.g., @xaana_bot)
            description: Optional description
            is_active: Whether this token is currently active
            
        Returns:
            bot_token_id: The unique ID of the created bot token
        """
        bot_token_id = str(uuid.uuid4())
        now = utc_now_iso()
        
        with get_db_session() as session:
            if not self._has_bot_tokens_table(session):
                raise RuntimeError(
                    "Database schema is missing table 'bot_tokens'. "
                    "Run migrations (python scripts/run_migrations.py)."
                )

            session.execute(
                text("""
                    INSERT INTO bot_tokens(
                        bot_token_id, bot_token, bot_username, is_active, description,
                        created_at_utc, updated_at_utc
                    ) VALUES (
                        :bot_token_id, :bot_token, :bot_username, :is_active, :description,
                        :created_at_utc, :updated_at_utc
                    );
                """),
                {
                    "bot_token_id": bot_token_id,
                    "bot_token": bot_token,
                    "bot_username": bot_username,
                    "is_active": is_active,
                    "description": description,
                    "created_at_utc": now,
                    "updated_at_utc": now,
                },
            )
        
        return bot_token_id

    def get_bot_token(self, bot_token_id: str) -> Optional[dict]:
        """
        Get a bot token by ID.
        
        Returns:
            Dictionary with bot token details, or None if not found
        """
        with get_db_session() as session:
            if not self._has_bot_tokens_table(session):
                logger.warning("bot_tokens table is missing; returning no bot token")
                return None

            row = session.execute(
                text("""
                    SELECT bot_token_id, bot_token, bot_username, is_active, description,
                           created_at_utc, updated_at_utc
                    FROM bot_tokens
                    WHERE bot_token_id = :bot_token_id
                    LIMIT 1;
                """),
                {"bot_token_id": bot_token_id},
            ).mappings().fetchone()
            
            if not row:
                return None
            
            return {
                "bot_token_id": row["bot_token_id"],
                "bot_token": row["bot_token"],
                "bot_username": row["bot_username"],
                "is_active": bool(row["is_active"]),
                "description": row["description"],
                "created_at_utc": row["created_at_utc"],
                "updated_at_utc": row["updated_at_utc"],
            }

    def list_bot_tokens(self, is_active: Optional[bool] = None) -> List[dict]:
        """
        List bot tokens with optional filter.
        
        Args:
            is_active: Filter by active status (optional)
            
        Returns:
            List of bot token dictionaries
        """
        tokens = []
        
        with get_db_session() as session:
            if not self._has_bot_tokens_table(session):
                logger.warning("bot_tokens table is missing; returning empty bot token list")
                return []

            conditions = ["1=1"]
            params = {}
            
            if is_active is not None:
                conditions.append("is_active = :is_active")
                params["is_active"] = is_active
            
            query = f"""
                SELECT bot_token_id, bot_token, bot_username, is_active, description,
                       created_at_utc, updated_at_utc
                FROM bot_tokens
                WHERE {' AND '.join(conditions)}
                ORDER BY created_at_utc DESC
            """
            
            rows = session.execute(text(query), params).mappings().fetchall()
            
            for row in rows:
                tokens.append({
                    "bot_token_id": row["bot_token_id"],
                    "bot_token": row["bot_token"],
                    "bot_username": row["bot_username"],
                    "is_active": bool(row["is_active"]),
                    "description": row["description"],
                    "created_at_utc": row["created_at_utc"],
                    "updated_at_utc": row["updated_at_utc"],
                })
        
        return tokens

    def update_bot_token(
        self,
        bot_token_id: str,
        bot_token: Optional[str] = None,
        bot_username: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> bool:
        """
        Update a bot token.
        
        Returns:
            True if token was updated, False if not found
        """
        updates = []
        params = {"bot_token_id": bot_token_id}
        
        if bot_token is not None:
            updates.append("bot_token = :bot_token")
            params["bot_token"] = bot_token
        
        if bot_username is not None:
            updates.append("bot_username = :bot_username")
            params["bot_username"] = bot_username
        
        if description is not None:
            updates.append("description = :description")
            params["description"] = description
        
        if is_active is not None:
            updates.append("is_active = :is_active")
            params["is_active"] = is_active
        
        if not updates:
            return False
        
        updates.append("updated_at_utc = :updated_at_utc")
        params["updated_at_utc"] = utc_now_iso()
        
        with get_db_session() as session:
            if not self._has_bot_tokens_table(session):
                logger.warning("bot_tokens table is missing; skipping bot token update")
                return False

            result = session.execute(
                text(f"""
                    UPDATE bot_tokens
                    SET {', '.join(updates)}
                    WHERE bot_token_id = :bot_token_id;
                """),
                params,
            )
            return result.rowcount > 0

    def deactivate_bot_token(self, bot_token_id: str) -> bool:
        """Deactivate a bot token (set is_active to false)."""
        return self.update_bot_token(bot_token_id, is_active=False)
