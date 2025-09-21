import uuid
from typing import List, Optional
from datetime import datetime

from models.models import Session, Action
from models.enums import SessionStatus, ActionType
from repositories.sessions_repo import SessionsRepository
from repositories.actions_repo import ActionsRepository


class SessionsService:
    def __init__(self, sessions_repo: SessionsRepository, actions_repo: ActionsRepository):
        self.sessions_repo = sessions_repo
        self.actions_repo = actions_repo

    def start(self, user_id: int, promise_id: str, message_id: Optional[int] = None, chat_id: Optional[int] = None) -> Session:
        """Start a new session for a promise."""
        session_id = str(uuid.uuid4())
        now = datetime.now()
        
        session = Session(
            session_id=session_id,
            user_id=user_id,
            promise_id=promise_id,
            status=SessionStatus.RUNNING.value,
            started_at=now,
            last_state_change_at=now,
            message_id=message_id,
            chat_id=chat_id
        )
        
        self.sessions_repo.create_session(session)
        return session

    def pause(self, user_id: int, session_id: str) -> Optional[Session]:
        """Pause a running session."""
        session = self.sessions_repo.get_session(user_id, session_id)
        if not session or session.status != SessionStatus.RUNNING.value:
            return None
        
        now = datetime.now()
        session.status = SessionStatus.PAUSED.value
        session.last_state_change_at = now
        
        self.sessions_repo.update_session(session)
        return session

    def resume(self, user_id: int, session_id: str) -> Optional[Session]:
        """Resume a paused session."""
        session = self.sessions_repo.get_session(user_id, session_id)
        if not session or session.status != SessionStatus.PAUSED.value:
            return None
        
        now = datetime.now()
        session.status = SessionStatus.RUNNING.value
        session.last_state_change_at = now
        
        self.sessions_repo.update_session(session)
        return session

    def finish(self, user_id: int, session_id: str, override_hours: Optional[float] = None) -> Optional[Action]:
        """Finish a session and log the time spent."""
        session = self.sessions_repo.get_session(user_id, session_id)
        if not session or session.status not in [SessionStatus.RUNNING.value, SessionStatus.PAUSED.value]:
            return None
        
        now = datetime.now()
        
        # Calculate elapsed time
        if override_hours is not None:
            elapsed_hours = override_hours
        else:
            elapsed_seconds = (now - session.started_at).total_seconds() - session.paused_seconds_total
            elapsed_hours = max(0, elapsed_seconds / 3600)
        
        # Create action record
        action = Action(
            user_id=user_id,
            promise_id=session.promise_id,
            action=ActionType.LOG_TIME.value,
            time_spent=elapsed_hours,
            at=now
        )
        
        # Update session
        session.status = SessionStatus.FINISHED.value
        session.ended_at = now
        session.last_state_change_at = now
        
        self.sessions_repo.update_session(session)
        self.actions_repo.append_action(action)
        
        return action

    def abort(self, user_id: int, session_id: str) -> Optional[Session]:
        """Abort a session without logging time."""
        session = self.sessions_repo.get_session(user_id, session_id)
        if not session or session.status not in [SessionStatus.RUNNING.value, SessionStatus.PAUSED.value]:
            return None
        
        now = datetime.now()
        session.status = SessionStatus.ABORTED.value
        session.ended_at = now
        session.last_state_change_at = now
        
        self.sessions_repo.update_session(session)
        return session

    def recover_on_startup(self, user_id: int) -> List[Session]:
        """Recover active sessions on bot startup."""
        active_sessions = self.sessions_repo.list_active_sessions(user_id)
        
        # For now, just return active sessions
        # Future: could implement logic to handle sessions that were running when bot went down
        return active_sessions

    def get_session_elapsed_time(self, session: Session) -> float:
        """Calculate elapsed time for a session (excluding paused time)."""
        if session.status == SessionStatus.FINISHED.value and session.ended_at:
            end_time = session.ended_at
        else:
            end_time = datetime.now()
        
        elapsed_seconds = (end_time - session.started_at).total_seconds() - session.paused_seconds_total
        return max(0, elapsed_seconds / 3600)  # Convert to hours
