"""
Repository for user profile facts and state.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime

from sqlalchemy import text

from db.postgres_db import get_db_session, utc_now_iso, dt_from_utc_iso, dt_to_utc_iso


class ProfileRepository:
    """PostgreSQL-backed profile repository."""

    def __init__(self, root_dir: str = None):
        # root_dir kept for backward compatibility but not used for PostgreSQL
        self.root_dir = root_dir

    def upsert_fact(
        self,
        user_id: int,
        field_key: str,
        value_text: str,
        source: str = "inferred",
        confidence: float = 0.7,
    ) -> None:
        """Upsert a profile fact for a user."""
        user = str(user_id)
        now = utc_now_iso()
        
        # Validate source
        if source not in ("explicit_answer", "inferred", "system"):
            source = "inferred"
        
        # Clamp confidence
        confidence = max(0.0, min(1.0, confidence))
        
        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO user_profile_facts(
                        user_id, field_key, value_text, source, confidence,
                        created_at_utc, updated_at_utc
                    ) VALUES (
                        :user_id, :field_key, :value_text, :source, :confidence,
                        :created_at_utc, :updated_at_utc
                    )
                    ON CONFLICT (user_id, field_key) DO UPDATE SET
                        value_text = EXCLUDED.value_text,
                        source = EXCLUDED.source,
                        confidence = EXCLUDED.confidence,
                        updated_at_utc = EXCLUDED.updated_at_utc;
                """),
                {
                    "user_id": user,
                    "field_key": field_key,
                    "value_text": value_text,
                    "source": source,
                    "confidence": confidence,
                    "created_at_utc": now,
                    "updated_at_utc": now,
                },
            )

    def list_facts(self, user_id: int) -> List[Dict[str, Any]]:
        """List all profile facts for a user."""
        user = str(user_id)
        with get_db_session() as session:
            rows = session.execute(
                text("""
                    SELECT field_key, value_text, source, confidence,
                           created_at_utc, updated_at_utc
                    FROM user_profile_facts
                    WHERE user_id = :user_id
                    ORDER BY field_key;
                """),
                {"user_id": user},
            ).mappings().fetchall()
        
        return [
            {
                "field_key": row["field_key"],
                "value_text": row["value_text"],
                "source": row["source"],
                "confidence": float(row["confidence"]),
                "created_at_utc": row["created_at_utc"],
                "updated_at_utc": row["updated_at_utc"],
            }
            for row in rows
        ]

    def get_fact(self, user_id: int, field_key: str) -> Optional[Dict[str, Any]]:
        """Get a specific profile fact."""
        user = str(user_id)
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT field_key, value_text, source, confidence,
                           created_at_utc, updated_at_utc
                    FROM user_profile_facts
                    WHERE user_id = :user_id AND field_key = :field_key
                    LIMIT 1;
                """),
                {"user_id": user, "field_key": field_key},
            ).mappings().fetchone()
        
        if not row:
            return None
        
        return {
            "field_key": row["field_key"],
            "value_text": row["value_text"],
            "source": row["source"],
            "confidence": float(row["confidence"]),
            "created_at_utc": row["created_at_utc"],
            "updated_at_utc": row["updated_at_utc"],
        }

    def get_state(self, user_id: int) -> Dict[str, Any]:
        """Get profile state (pending question, last asked, etc.)."""
        user = str(user_id)
        with get_db_session() as session:
            row = session.execute(
                text("""
                    SELECT pending_field_key, pending_question_text,
                           pending_asked_at_utc, last_question_asked_at_utc
                    FROM user_profile_state
                    WHERE user_id = :user_id
                    LIMIT 1;
                """),
                {"user_id": user},
            ).mappings().fetchone()
        
        if not row:
            return {
                "pending_field_key": None,
                "pending_question_text": None,
                "pending_asked_at_utc": None,
                "last_question_asked_at_utc": None,
            }
        
        return {
            "pending_field_key": row["pending_field_key"],
            "pending_question_text": row["pending_question_text"],
            "pending_asked_at_utc": row["pending_asked_at_utc"],
            "last_question_asked_at_utc": row["last_question_asked_at_utc"],
        }

    def set_pending_question(
        self,
        user_id: int,
        field_key: str,
        question_text: str,
    ) -> None:
        """Set a pending profile question."""
        user = str(user_id)
        now = utc_now_iso()
        with get_db_session() as session:
            session.execute(
                text("""
                    INSERT INTO user_profile_state(
                        user_id, pending_field_key, pending_question_text,
                        pending_asked_at_utc, last_question_asked_at_utc
                    ) VALUES (
                        :user_id, :pending_field_key, :pending_question_text,
                        :pending_asked_at_utc, :last_question_asked_at_utc
                    )
                    ON CONFLICT (user_id) DO UPDATE SET
                        pending_field_key = EXCLUDED.pending_field_key,
                        pending_question_text = EXCLUDED.pending_question_text,
                        pending_asked_at_utc = EXCLUDED.pending_asked_at_utc,
                        last_question_asked_at_utc = EXCLUDED.last_question_asked_at_utc;
                """),
                {
                    "user_id": user,
                    "pending_field_key": field_key,
                    "pending_question_text": question_text,
                    "pending_asked_at_utc": now,
                    "last_question_asked_at_utc": now,
                },
            )

    def clear_pending_question(self, user_id: int) -> None:
        """Clear the pending profile question."""
        user = str(user_id)
        with get_db_session() as session:
            session.execute(
                text("""
                    UPDATE user_profile_state
                    SET pending_field_key = NULL,
                        pending_question_text = NULL,
                        pending_asked_at_utc = NULL
                    WHERE user_id = :user_id;
                """),
                {"user_id": user},
            )

    def update_last_question_asked(self, user_id: int) -> None:
        """Update the timestamp of the last question asked (without setting pending)."""
        user = str(user_id)
        now = utc_now_iso()
        with get_db_session() as session:
            # Ensure state row exists
            session.execute(
                text("""
                    INSERT INTO user_profile_state(
                        user_id, last_question_asked_at_utc
                    ) VALUES (
                        :user_id, :last_question_asked_at_utc
                    )
                    ON CONFLICT (user_id) DO UPDATE SET
                        last_question_asked_at_utc = EXCLUDED.last_question_asked_at_utc;
                """),
                {
                    "user_id": user,
                    "last_question_asked_at_utc": now,
                },
            )
