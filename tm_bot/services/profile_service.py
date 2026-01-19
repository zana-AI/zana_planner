"""
Service for user profile management.
"""
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta

from repositories.profile_repo import ProfileRepository
from db.postgres_db import dt_from_utc_iso, utc_now_iso
from utils.logger import get_logger

logger = get_logger(__name__)


class ProfileService:
    """Service for managing user profiles."""

    # Core profile fields (MVP: 5 fields)
    CORE_FIELDS = [
        "status",
        "schedule_type",
        "primary_goal_1y",
        "top_focus_area",
        "main_constraint",
    ]

    # Question bank: one short question per field
    QUESTIONS = {
        "status": "What best describes your current life stage? (e.g., student, working professional, parent, retired)",
        "schedule_type": "What's your typical work schedule? (e.g., fixed 9-5, flexible, shifts, irregular)",
        "primary_goal_1y": "What's the #1 thing you want to achieve in the next 12 months? (one sentence)",
        "top_focus_area": "What area are you focusing on most right now? (e.g., health, career, learning, relationships)",
        "main_constraint": "What's your biggest obstacle these days? (e.g., time, energy, clarity, motivation)",
    }

    def __init__(self, profile_repo: ProfileRepository):
        self.profile_repo = profile_repo

    def get_profile_status(self, user_id: int) -> Dict[str, Any]:
        """
        Get profile status: facts, missing fields, completion percentage, pending question.
        
        Returns:
            {
                "facts": {field_key: value_text, ...},
                "missing_fields": [field_key, ...],
                "completion_percentage": float (0-100),
                "completion_text": "Core profile: 2/5",
                "pending_field_key": Optional[str],
                "pending_question_text": Optional[str],
            }
        """
        facts_list = self.profile_repo.list_facts(user_id)
        state = self.profile_repo.get_state(user_id)
        
        # Build facts dict
        facts = {f["field_key"]: f["value_text"] for f in facts_list}
        
        # Find missing core fields
        missing = [field for field in self.CORE_FIELDS if field not in facts]
        
        # Calculate completion
        completed = len(self.CORE_FIELDS) - len(missing)
        completion_pct = (completed / len(self.CORE_FIELDS)) * 100.0
        completion_text = f"Core profile: {completed}/{len(self.CORE_FIELDS)}"
        
        return {
            "facts": facts,
            "missing_fields": missing,
            "completion_percentage": completion_pct,
            "completion_text": completion_text,
            "pending_field_key": state.get("pending_field_key"),
            "pending_question_text": state.get("pending_question_text"),
        }

    def maybe_enqueue_next_question(
        self,
        user_id: int,
        cooldown_hours: int = 24,
    ) -> Optional[Dict[str, Any]]:
        """
        Atomically check if we should ask a profile question and enqueue it if eligible.
        
        Eligibility:
        - No pending question exists
        - At least one core field is missing
        - Cooldown has passed since last question (or never asked)
        
        Returns:
            None if not eligible, or {
                "should_ask": True,
                "field_key": str,
                "question_text": str,
            }
        """
        state = self.profile_repo.get_state(user_id)
        
        # Check if there's already a pending question
        if state.get("pending_field_key"):
            return None
        
        # Get missing fields
        status = self.get_profile_status(user_id)
        missing = status["missing_fields"]
        
        if not missing:
            # Profile is complete
            return None
        
        # Check cooldown
        last_asked_str = state.get("last_question_asked_at_utc")
        if last_asked_str:
            try:
                last_asked = dt_from_utc_iso(last_asked_str)
                now = datetime.utcnow()
                hours_since = (now - last_asked).total_seconds() / 3600.0
                if hours_since < cooldown_hours:
                    # Still in cooldown
                    return None
            except Exception as e:
                logger.warning(f"Error parsing last_question_asked_at_utc for user {user_id}: {e}")
                # On error, allow asking (safer to ask than to never ask)
        
        # Pick the first missing field (simple priority: order in CORE_FIELDS)
        field_key = missing[0]
        question_text = self.QUESTIONS.get(field_key, f"Tell me about your {field_key}.")
        
        # Atomically set pending question
        self.profile_repo.set_pending_question(user_id, field_key, question_text)
        
        return {
            "should_ask": True,
            "field_key": field_key,
            "question_text": question_text,
        }

    def upsert_fact(
        self,
        user_id: int,
        field_key: str,
        value_text: str,
        source: str = "inferred",
        confidence: float = 0.7,
    ) -> None:
        """Upsert a profile fact."""
        # Validate field_key (allow any, but log if not in core fields)
        if field_key not in self.CORE_FIELDS:
            logger.debug(f"Upserting non-core profile field: {field_key}")
        
        self.profile_repo.upsert_fact(user_id, field_key, value_text, source, confidence)

    def clear_pending_question(self, user_id: int) -> None:
        """Clear the pending profile question."""
        self.profile_repo.clear_pending_question(user_id)
