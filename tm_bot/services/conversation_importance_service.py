"""
Service for batch scoring conversation importance using LLM.
Processes users separately to prevent data leakage.
"""

import uuid
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from sqlalchemy import text
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel

from db.postgres_db import get_db_session, utc_now_iso, dt_from_utc_iso
from llms.llm_env_utils import load_llm_env
from langchain_google_vertexai import ChatVertexAI
from langchain_openai import ChatOpenAI
from utils.logger import get_logger

logger = get_logger(__name__)


# Pydantic model for importance scoring output
class ImportanceScoreOutput(BaseModel):
    importance_score: int  # 0-100
    reasoning: str
    key_themes: List[str]
    intent_category: str


# Importance scoring prompt
IMPORTANCE_SCORING_PROMPT = """
=== ROLE ===
You are an importance evaluator for a task management and habit tracking assistant bot.

=== BOT'S PURPOSE ===
The bot helps users:
1. **Track Goals & Habits**: Users create "promises" (goals/habits) and log "actions" (time spent on activities)
2. **Get Strategic Advice**: Coaching on productivity, goal achievement, time management
3. **Manage Preferences**: Learn user's schedule, constraints, life stage, goals, and preferences
4. **Progress Tracking**: Help users understand their progress, streaks, and patterns
5. **Contextual Assistance**: Understand user's situation to provide personalized help

=== IMPORTANCE SCORING CRITERIA ===
Rate conversation importance from 0-100 based on how valuable this exchange is for:
- Understanding the user's goals, preferences, constraints, or context
- Enabling concrete actions (creating promises, logging actions, changing settings)
- Resolving ambiguity or clarifying user intent
- Building a long-term understanding of the user

**HIGH IMPORTANCE (80-100):**
- User explicitly states preferences, goals, constraints, or life context
- Promise creation/modification/deletion (concrete goal management)
- Action logging (time tracking on promises)
- Settings changes (timezone, language, notifications)
- Profile information (life stage, schedule type, primary goals, focus areas, constraints)
- Strategic commitments or decisions
- User corrections that fix misunderstandings

**MEDIUM IMPORTANCE (40-79):**
- Clarifications that resolve ambiguity in ongoing conversations
- Progress queries that reveal user patterns or concerns
- Coaching questions showing user's strategic thinking
- Follow-up questions within an active conversation session
- Context that helps understand user's current situation
- Questions about how to use the bot effectively

**LOW IMPORTANCE (0-39):**
- Casual chat, greetings, acknowledgments ("hi", "thanks", "ok")
- Jokes, humor, or purely social engagement
- Generic questions with no actionable outcome
- Redundant information already captured in previous conversations
- Simple confirmations without new information

=== EVALUATION INSTRUCTIONS ===
1. Consider the FULL exchange (user message + bot response if available)
2. Focus on what NEW information or VALUE this conversation provides
3. Consider both explicit content and implicit context
4. If the conversation led to a concrete action (promise created, action logged), it's likely high importance
5. If it's just maintaining engagement without new information, it's low importance
6. If it reveals user preferences, goals, or constraints, it's high importance

=== OUTPUT ===
Provide ONLY a JSON object with:
{
  "importance_score": <integer 0-100>,
  "reasoning": "<brief explanation of why this score>",
  "key_themes": ["<theme1>", "<theme2>", ...],
  "intent_category": "<category>" // e.g., "promise_creation", "action_logging", "preference_statement", "clarification", "casual_chat", "coaching_question", etc.
}
"""


class ConversationImportanceService:
    """Service for scoring conversation importance using LLM."""

    def __init__(self) -> None:
        self._llm_model = None
        self._parser = JsonOutputParser(pydantic_object=ImportanceScoreOutput)
        self._initialize_llm()

    @staticmethod
    def _ensure_utc(ts: datetime) -> datetime:
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)

    @classmethod
    def _new_session_id(cls, start_ts: datetime) -> str:
        ts = cls._ensure_utc(start_ts)
        # Time-tagged session ID to make session start visible from the value itself.
        return f"s-{ts.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    
    def _initialize_llm(self) -> None:
        """Initialize LLM model for importance scoring."""
        try:
            cfg = load_llm_env()
            
            # Use a lightweight model for scoring (cost-efficient)
            if cfg.get("GCP_PROJECT_ID", ""):
                self._llm_model = ChatVertexAI(
                    model=cfg.get("GCP_GEMINI_MODEL", "gemini-1.5-flash"),
                    project=cfg["GCP_PROJECT_ID"],
                    location=cfg.get("GCP_LLM_LOCATION", cfg.get("GCP_LOCATION", "us-central1")),
                    temperature=0.3,  # Lower temperature for more consistent scoring
                )
            elif cfg.get("OPENAI_API_KEY", ""):
                self._llm_model = ChatOpenAI(
                    openai_api_key=cfg["OPENAI_API_KEY"],
                    temperature=0.3,
                    model="gpt-4o-mini",  # Use mini for cost efficiency
                )
            
            if not self._llm_model:
                raise ValueError("No LLM configured for importance scoring")
                
        except Exception as e:
            logger.error(f"Failed to initialize LLM for importance scoring: {e}")
            raise
    
    def score_conversation_exchange(
        self,
        user_message: str,
        bot_response: Optional[str] = None,
    ) -> Optional[ImportanceScoreOutput]:
        """
        Score a single conversation exchange using LLM.
        
        Args:
            user_message: User's message content
            bot_response: Bot's response content (optional)
        
        Returns:
            ImportanceScoreOutput if successful, None on error
        """
        if not self._llm_model:
            logger.error("LLM model not initialized")
            return None
        
        try:
            # Build conversation context
            exchange_text = f"User: {user_message}"
            if bot_response:
                exchange_text += f"\n\nBot: {bot_response}"
            
            # Create messages
            messages = [
                SystemMessage(content=IMPORTANCE_SCORING_PROMPT),
                HumanMessage(content=f"Evaluate this conversation exchange:\n\n{exchange_text}"),
            ]
            
            # Call LLM
            result = self._llm_model.invoke(messages)
            content = getattr(result, "content", "") or ""
            
            # Parse JSON response
            parsed = self._parser.parse(content)
            
            if isinstance(parsed, dict):
                return ImportanceScoreOutput(**parsed)
            elif isinstance(parsed, ImportanceScoreOutput):
                return parsed
            else:
                logger.warning(f"Unexpected parser output type: {type(parsed)}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to score conversation exchange: {e}")
            return None
    
    def get_unscored_conversations_for_user(
        self,
        user_id: int,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get unscored conversations for a specific user.
        
        Args:
            user_id: User ID
            limit: Maximum number of conversations to return (None for all)
        
        Returns:
            List of conversation dictionaries
        """
        try:
            with get_db_session() as session:
                query = text("""
                    SELECT 
                        c.id,
                        c.user_id,
                        c.message_type,
                        c.content,
                        c.created_at_utc,
                        -- Get bot response if available (next message after user message)
                        (
                            SELECT c2.content
                            FROM conversations c2
                            WHERE c2.user_id = c.user_id
                                AND c2.message_type = 'bot'
                                AND c2.created_at_utc > c.created_at_utc
                            ORDER BY c2.created_at_utc ASC
                            LIMIT 1
                        ) as bot_response
                    FROM conversations c
                    WHERE c.user_id = :user_id
                        AND c.message_type = 'user'
                        AND c.importance_score IS NULL
                    ORDER BY c.created_at_utc ASC
                    LIMIT :limit
                """)
                
                params = {"user_id": str(user_id)}
                if limit:
                    params["limit"] = limit
                else:
                    params["limit"] = 10000  # Large limit for "all"
                
                rows = session.execute(query, params).mappings().fetchall()
                
                return [
                    {
                        "id": row["id"],
                        "user_id": row["user_id"],
                        "message_type": row["message_type"],
                        "content": row["content"],
                        "created_at_utc": row["created_at_utc"],
                        "bot_response": row["bot_response"],
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Failed to get unscored conversations for user {user_id}: {e}")
            return []
    
    def assign_conversation_session_id(
        self,
        user_id: int,
        conversation_id: int,
        message_timestamp: datetime,
        gap_threshold_minutes: int = 30,
    ) -> str:
        """
        Assign or retrieve conversation_session_id based on time gaps.
        
        Args:
            user_id: User ID
            conversation_id: Current conversation ID
            message_timestamp: Timestamp of the message
            gap_threshold_minutes: Minutes threshold for new session (default: 30)
        
        Returns:
            conversation_session_id
        """
        try:
            with get_db_session() as session:
                # Get last conversation for this user
                last_row = session.execute(
                    text("""
                        SELECT id, conversation_session_id, created_at_utc
                        FROM conversations
                        WHERE user_id = :user_id
                            AND id < :current_id
                        ORDER BY created_at_utc DESC
                        LIMIT 1
                    """),
                    {"user_id": str(user_id), "current_id": conversation_id},
                ).fetchone()
                
                if not last_row or not last_row[1]:  # No previous conversation or no session_id
                    return self._new_session_id(message_timestamp)
                
                # Check time gap
                last_timestamp = dt_from_utc_iso(last_row[2])
                if last_timestamp:
                    time_gap_minutes = (message_timestamp - last_timestamp).total_seconds() / 60
                    
                    if time_gap_minutes > gap_threshold_minutes:
                        # New session - user was away
                        return self._new_session_id(message_timestamp)
                
                # Continue existing session
                return last_row[1]
                
        except Exception as e:
            logger.warning(f"Failed to assign session ID for conversation {conversation_id}: {e}")
            # Fallback: generate new session ID
            return self._new_session_id(message_timestamp)
    
    def score_user_conversations(
        self,
        user_id: int,
        batch_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Score all unscored conversations for a specific user.
        Processes in batches to avoid overwhelming the LLM.
        
        Args:
            user_id: User ID
            batch_size: Number of conversations to process per batch
        
        Returns:
            Dictionary with scoring statistics
        """
        logger.info(f"Starting importance scoring for user {user_id}")
        
        stats = {
            "user_id": user_id,
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "errors": [],
        }
        
        try:
            # Get all unscored conversations for this user
            conversations = self.get_unscored_conversations_for_user(user_id)
            
            if not conversations:
                logger.info(f"No unscored conversations for user {user_id}")
                return stats
            
            logger.info(f"Found {len(conversations)} unscored conversations for user {user_id}")
            
            # Process in batches
            for i in range(0, len(conversations), batch_size):
                batch = conversations[i:i + batch_size]
                logger.info(f"Processing batch {i//batch_size + 1} ({len(batch)} conversations) for user {user_id}")
                
                for conv in batch:
                    try:
                        # Assign session ID first
                        message_timestamp = dt_from_utc_iso(conv["created_at_utc"])
                        if not message_timestamp:
                            logger.warning(f"Invalid timestamp for conversation {conv['id']}")
                            stats["failed"] += 1
                            continue
                        
                        session_id = self.assign_conversation_session_id(
                            user_id=user_id,
                            conversation_id=conv["id"],
                            message_timestamp=message_timestamp,
                        )
                        
                        # Score the conversation
                        score_result = self.score_conversation_exchange(
                            user_message=conv["content"],
                            bot_response=conv.get("bot_response"),
                        )
                        
                        if not score_result:
                            logger.warning(f"Failed to get score for conversation {conv['id']}")
                            stats["failed"] += 1
                            continue
                        
                        # Update conversation in database
                        with get_db_session() as session:
                            session.execute(
                                text("""
                                    UPDATE conversations
                                    SET 
                                        conversation_session_id = :session_id,
                                        importance_score = :score,
                                        importance_reasoning = :reasoning,
                                        intent_category = :intent,
                                        key_themes = :themes,
                                        scored_at_utc = :scored_at
                                    WHERE id = :id AND user_id = :user_id
                                """),
                                {
                                    "id": conv["id"],
                                    "user_id": str(user_id),
                                    "session_id": session_id,
                                    "score": score_result.importance_score,
                                    "reasoning": score_result.reasoning,
                                    "intent": score_result.intent_category,
                                    "themes": score_result.key_themes,
                                    "scored_at": utc_now_iso(),
                                },
                            )
                        
                        stats["successful"] += 1
                        stats["total_processed"] += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing conversation {conv.get('id', 'unknown')} for user {user_id}: {e}")
                        stats["failed"] += 1
                        stats["total_processed"] += 1
                        stats["errors"].append(f"Conv {conv.get('id', 'unknown')}: {str(e)}")
                
                # Small delay between batches to avoid rate limits
                time.sleep(0.5)
            
            logger.info(
                f"Completed importance scoring for user {user_id}: "
                f"{stats['successful']} successful, {stats['failed']} failed"
            )
            
        except Exception as e:
            logger.exception(f"Fatal error scoring conversations for user {user_id}: {e}")
            stats["errors"].append(f"Fatal: {str(e)}")
        
        return stats
    
    def score_all_users_conversations(
        self,
        batch_size_per_user: int = 50,
    ) -> Dict[str, Any]:
        """
        Score conversations for all users.
        Processes each user separately to prevent data leakage.
        
        Args:
            batch_size_per_user: Number of conversations to process per batch per user
        
        Returns:
            Dictionary with overall statistics
        """
        logger.info("Starting batch importance scoring for all users")
        
        overall_stats = {
            "total_users": 0,
            "users_processed": 0,
            "users_failed": 0,
            "total_conversations_scored": 0,
            "user_results": [],
        }
        
        try:
            # Get all user IDs from database
            with get_db_session() as session:
                rows = session.execute(text("SELECT DISTINCT user_id FROM conversations WHERE importance_score IS NULL")).fetchall()
                user_ids = [int(row[0]) for row in rows if row[0]]
            
            overall_stats["total_users"] = len(user_ids)
            logger.info(f"Found {len(user_ids)} users with unscored conversations")
            
            # Process each user separately
            for user_id in user_ids:
                try:
                    logger.info(f"Processing user {user_id} ({overall_stats['users_processed'] + 1}/{len(user_ids)})")
                    
                    user_stats = self.score_user_conversations(
                        user_id=user_id,
                        batch_size=batch_size_per_user,
                    )
                    
                    overall_stats["user_results"].append(user_stats)
                    overall_stats["total_conversations_scored"] += user_stats["successful"]
                    overall_stats["users_processed"] += 1
                    
                    # Clear any cached data between users to prevent leakage
                    # (LLM model is stateless, but good practice)
                    
                except Exception as e:
                    logger.exception(f"Failed to process user {user_id}: {e}")
                    overall_stats["users_failed"] += 1
                    overall_stats["user_results"].append({
                        "user_id": user_id,
                        "error": str(e),
                    })
            
            logger.info(
                f"Completed batch importance scoring: "
                f"{overall_stats['users_processed']} users processed, "
                f"{overall_stats['total_conversations_scored']} conversations scored"
            )
            
        except Exception as e:
            logger.exception(f"Fatal error in batch importance scoring: {e}")
        
        return overall_stats
