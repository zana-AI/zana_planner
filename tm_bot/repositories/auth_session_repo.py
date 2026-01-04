"""
Repository for managing authentication sessions.
Stores sessions in memory (can be extended to use SQLite for persistence).
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional
from models.models import AuthSession
from utils.logger import get_logger

logger = get_logger(__name__)


class AuthSessionRepository:
    """In-memory repository for authentication sessions."""
    
    def __init__(self):
        # Store sessions in memory: {session_token: AuthSession}
        self._sessions: Dict[str, AuthSession] = {}
    
    def create_session(
        self,
        user_id: int,
        telegram_auth_date: int,
        expires_in_days: int = 7
    ) -> AuthSession:
        """
        Create a new authentication session.
        
        Args:
            user_id: Telegram user ID
            telegram_auth_date: Original auth_date from Telegram
            expires_in_days: Number of days until expiration (default: 7)
        
        Returns:
            Created AuthSession
        """
        session_token = str(uuid.uuid4())
        now = datetime.now()
        expires_at = now + timedelta(days=expires_in_days)
        
        session = AuthSession(
            session_token=session_token,
            user_id=user_id,
            created_at=now,
            expires_at=expires_at,
            telegram_auth_date=telegram_auth_date
        )
        
        self._sessions[session_token] = session
        logger.debug(f"Created auth session for user {user_id}, expires at {expires_at}")
        
        return session
    
    def get_session(self, session_token: str) -> Optional[AuthSession]:
        """
        Get a session by token.
        
        Args:
            session_token: Session token
        
        Returns:
            AuthSession if found and not expired, None otherwise
        """
        session = self._sessions.get(session_token)
        
        if not session:
            return None
        
        # Check if expired
        if datetime.now() > session.expires_at:
            # Remove expired session
            del self._sessions[session_token]
            logger.debug(f"Session {session_token} expired and removed")
            return None
        
        return session
    
    def delete_session(self, session_token: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_token: Session token to delete
        
        Returns:
            True if session was deleted, False if not found
        """
        if session_token in self._sessions:
            del self._sessions[session_token]
            logger.debug(f"Deleted auth session {session_token}")
            return True
        return False
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired sessions.
        
        Returns:
            Number of sessions removed
        """
        now = datetime.now()
        expired_tokens = [
            token for token, session in self._sessions.items()
            if now > session.expires_at
        ]
        
        for token in expired_tokens:
            del self._sessions[token]
        
        if expired_tokens:
            logger.info(f"Cleaned up {len(expired_tokens)} expired auth sessions")
        
        return len(expired_tokens)
    
    def get_user_sessions(self, user_id: int) -> list[AuthSession]:
        """
        Get all active sessions for a user.
        
        Args:
            user_id: User ID
        
        Returns:
            List of active AuthSessions
        """
        now = datetime.now()
        return [
            session for session in self._sessions.values()
            if session.user_id == user_id and now <= session.expires_at
        ]

