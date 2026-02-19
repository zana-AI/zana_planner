from typing import List, Optional
from datetime import datetime
import json
import uuid

from sqlalchemy import text

from db.postgres_db import (
    get_db_session,
    utc_now_iso,
    dt_from_utc_iso,
    dt_to_utc_iso,
    get_table_columns,
)
from models.models import Broadcast
from utils.logger import get_logger


logger = get_logger(__name__)


class BroadcastsRepository:
    """Repository for managing scheduled broadcasts."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def _has_bot_token_column(session) -> bool:
        """Return True when broadcasts.bot_token_id exists."""
        return "bot_token_id" in set(get_table_columns(session, "broadcasts"))

    def create_broadcast(
        self,
        admin_id: int,
        message: str,
        target_user_ids: List[int],
        scheduled_time_utc: datetime,
        bot_token_id: Optional[str] = None,
    ) -> str:
        """
        Create a new broadcast.
        
        Args:
            admin_id: Admin user ID
            message: Broadcast message text
            target_user_ids: List of target user IDs
            scheduled_time_utc: Scheduled time in UTC
            bot_token_id: Optional bot token ID to use for this broadcast
        
        Returns:
            broadcast_id: The unique ID of the created broadcast
        """
        broadcast_id = str(uuid.uuid4())
        admin = str(admin_id)
        now = utc_now_iso()
        
        # Convert target_user_ids to JSON string
        target_ids_json = json.dumps([int(uid) for uid in target_user_ids])
        scheduled_time_str = dt_to_utc_iso(scheduled_time_utc)
        
        with get_db_session() as session:
            if self._has_bot_token_column(session):
                session.execute(
                    text("""
                        INSERT INTO broadcasts(
                            broadcast_id, admin_id, message, target_user_ids,
                            scheduled_time_utc, status, bot_token_id,
                            created_at_utc, updated_at_utc
                        ) VALUES (
                            :broadcast_id, :admin_id, :message, :target_user_ids,
                            :scheduled_time_utc, 'pending', :bot_token_id,
                            :created_at_utc, :updated_at_utc
                        );
                    """),
                    {
                        "broadcast_id": broadcast_id,
                        "admin_id": admin,
                        "message": message,
                        "target_user_ids": target_ids_json,
                        "scheduled_time_utc": scheduled_time_str,
                        "bot_token_id": bot_token_id,
                        "created_at_utc": now,
                        "updated_at_utc": now,
                    },
                )
            else:
                if bot_token_id:
                    logger.warning(
                        "broadcasts.bot_token_id column is missing; creating broadcast without custom bot token"
                    )
                session.execute(
                    text("""
                        INSERT INTO broadcasts(
                            broadcast_id, admin_id, message, target_user_ids,
                            scheduled_time_utc, status,
                            created_at_utc, updated_at_utc
                        ) VALUES (
                            :broadcast_id, :admin_id, :message, :target_user_ids,
                            :scheduled_time_utc, 'pending',
                            :created_at_utc, :updated_at_utc
                        );
                    """),
                    {
                        "broadcast_id": broadcast_id,
                        "admin_id": admin,
                        "message": message,
                        "target_user_ids": target_ids_json,
                        "scheduled_time_utc": scheduled_time_str,
                        "created_at_utc": now,
                        "updated_at_utc": now,
                    },
                )
        
        return broadcast_id

    def get_broadcast(self, broadcast_id: str) -> Optional[Broadcast]:
        """Get a broadcast by ID."""
        with get_db_session() as session:
            bot_token_select = (
                "bot_token_id" if self._has_bot_token_column(session) else "NULL AS bot_token_id"
            )
            row = session.execute(
                text(f"""
                    SELECT broadcast_id, admin_id, message, target_user_ids,
                           scheduled_time_utc, status, {bot_token_select},
                           created_at_utc, updated_at_utc
                    FROM broadcasts
                    WHERE broadcast_id = :broadcast_id
                    LIMIT 1;
                """),
                {"broadcast_id": broadcast_id},
            ).mappings().fetchone()
            
            if not row:
                return None
            
            # Parse target_user_ids from JSON
            target_ids = json.loads(row["target_user_ids"])
            
            return Broadcast(
                broadcast_id=row["broadcast_id"],
                admin_id=row["admin_id"],
                message=row["message"],
                target_user_ids=[int(uid) for uid in target_ids],
                scheduled_time_utc=dt_from_utc_iso(row["scheduled_time_utc"]),
                status=row["status"],
                bot_token_id=row.get("bot_token_id"),
                created_at=dt_from_utc_iso(row["created_at_utc"]),
                updated_at=dt_from_utc_iso(row["updated_at_utc"]),
            )

    def list_broadcasts(
        self,
        admin_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Broadcast]:
        """
        List broadcasts with optional filters.
        
        Args:
            admin_id: Filter by admin ID (optional)
            status: Filter by status (optional)
            limit: Maximum number of results
        """
        broadcasts = []
        
        with get_db_session() as session:
            has_bot_token_column = self._has_bot_token_column(session)
            conditions = ["1=1"]
            params = {}
            
            if admin_id:
                conditions.append("admin_id = :admin_id")
                params["admin_id"] = str(admin_id)
            
            if status:
                conditions.append("status = :status")
                params["status"] = status
            
            params["limit"] = limit
            
            query = f"""
                SELECT broadcast_id, admin_id, message, target_user_ids,
                       scheduled_time_utc, status,
                       {'bot_token_id' if has_bot_token_column else 'NULL AS bot_token_id'},
                       created_at_utc, updated_at_utc
                FROM broadcasts
                WHERE {' AND '.join(conditions)}
                ORDER BY created_at_utc DESC LIMIT :limit
            """
            
            rows = session.execute(text(query), params).mappings().fetchall()
            
            for row in rows:
                # Parse target_user_ids from JSON
                target_ids = json.loads(row["target_user_ids"])
                
                broadcasts.append(
                    Broadcast(
                        broadcast_id=row["broadcast_id"],
                        admin_id=row["admin_id"],
                        message=row["message"],
                        target_user_ids=[int(uid) for uid in target_ids],
                        scheduled_time_utc=dt_from_utc_iso(row["scheduled_time_utc"]),
                        status=row["status"],
                        bot_token_id=row.get("bot_token_id"),
                        created_at=dt_from_utc_iso(row["created_at_utc"]),
                        updated_at=dt_from_utc_iso(row["updated_at_utc"]),
                    )
                )
        
        return broadcasts

    def update_broadcast(
        self,
        broadcast_id: str,
        message: Optional[str] = None,
        target_user_ids: Optional[List[int]] = None,
        scheduled_time_utc: Optional[datetime] = None,
        status: Optional[str] = None,
        bot_token_id: Optional[str] = None,
    ) -> bool:
        """
        Update a broadcast.
        
        Returns:
            True if broadcast was updated, False if not found
        """
        updates = []
        params = {"broadcast_id": broadcast_id}
        
        if message is not None:
            updates.append("message = :message")
            params["message"] = message
        
        if target_user_ids is not None:
            updates.append("target_user_ids = :target_user_ids")
            params["target_user_ids"] = json.dumps([int(uid) for uid in target_user_ids])
        
        if scheduled_time_utc is not None:
            updates.append("scheduled_time_utc = :scheduled_time_utc")
            params["scheduled_time_utc"] = dt_to_utc_iso(scheduled_time_utc)
        
        if status is not None:
            updates.append("status = :status")
            params["status"] = status
        
        if bot_token_id is not None:
            updates.append("bot_token_id = :bot_token_id")
            params["bot_token_id"] = bot_token_id
        
        if not updates:
            return False
        
        updates.append("updated_at_utc = :updated_at_utc")
        params["updated_at_utc"] = utc_now_iso()
        
        with get_db_session() as session:
            if bot_token_id is not None and not self._has_bot_token_column(session):
                logger.warning(
                    "broadcasts.bot_token_id column is missing; skipping bot_token_id update"
                )
                updates = [u for u in updates if u != "bot_token_id = :bot_token_id"]
                params.pop("bot_token_id", None)

            if not updates or updates == ["updated_at_utc = :updated_at_utc"]:
                return False

            result = session.execute(
                text(f"""
                    UPDATE broadcasts
                    SET {', '.join(updates)}
                    WHERE broadcast_id = :broadcast_id;
                """),
                params,
            )
            return result.rowcount > 0

    def cancel_broadcast(self, broadcast_id: str) -> bool:
        """Cancel a broadcast (set status to 'cancelled')."""
        return self.update_broadcast(broadcast_id, status="cancelled")

    def mark_broadcast_completed(self, broadcast_id: str) -> bool:
        """Mark a broadcast as completed."""
        return self.update_broadcast(broadcast_id, status="completed")
