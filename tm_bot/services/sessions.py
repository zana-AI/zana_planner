import uuid
from typing import List, Optional
from datetime import datetime, timedelta

from models.models import Session, Action
from models.enums import SessionStatus, ActionType
from repositories.sessions_repo import SessionsRepository
from repositories.actions_repo import ActionsRepository


class SessionsService:
    def __init__(self, sessions_repo: SessionsRepository, actions_repo: ActionsRepository):
        self.sessions_repo = sessions_repo
        self.actions_repo = actions_repo

    @staticmethod
    def _pending_pause_seconds(session: Session, now: datetime) -> int:
        """Return the current pause interval in seconds for a paused session."""
        if session.status != SessionStatus.PAUSED.value or not session.last_state_change_at:
            return 0
        return max(0, int((now - session.last_state_change_at).total_seconds()))

    def _elapsed_seconds(self, session: Session, now: Optional[datetime] = None) -> int:
        """Calculate elapsed seconds excluding both stored and in-flight paused time."""
        reference_time = now or datetime.now()
        paused_seconds = int(session.paused_seconds_total or 0) + self._pending_pause_seconds(session, reference_time)
        elapsed_seconds = int((reference_time - session.started_at).total_seconds()) - paused_seconds
        return max(0, elapsed_seconds)

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
        pause_seconds = self._pending_pause_seconds(session, now)
        session.paused_seconds_total = int(session.paused_seconds_total or 0) + pause_seconds
        if session.expected_end_utc and pause_seconds > 0:
            session.expected_end_utc = session.expected_end_utc + timedelta(seconds=pause_seconds)
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
            pause_seconds = self._pending_pause_seconds(session, now)
            session.paused_seconds_total = int(session.paused_seconds_total or 0) + pause_seconds
            elapsed_seconds = int((now - session.started_at).total_seconds()) - int(session.paused_seconds_total or 0)
            elapsed_hours = max(0, elapsed_seconds) / 3600
        
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
        pause_seconds = self._pending_pause_seconds(session, now)
        session.paused_seconds_total = int(session.paused_seconds_total or 0) + pause_seconds
        session.status = SessionStatus.ABORTED.value
        session.ended_at = now
        session.last_state_change_at = now
        
        self.sessions_repo.update_session(session)
        return session

    def recover_on_startup(self, user_id: int) -> List[Session]:
        """Recover active sessions on bot startup."""
        active_sessions = self.sessions_repo.list_active_sessions(user_id)
        
        # TODO: Implement logic to handle sessions that were running when bot went down
        # For now, just return active sessions
        return active_sessions

    def get_session_elapsed_time(self, session: Session) -> float:
        """Calculate elapsed time for a session (excluding paused time)."""
        if session.status == SessionStatus.FINISHED.value and session.ended_at:
            end_time = session.ended_at
        else:
            end_time = datetime.now()
        
        return self._elapsed_seconds(session, end_time) / 3600  # Convert to hours

    def bump(self, user_id: int, session_id: str, additional_hours: float) -> Optional[Session]:
        """Add additional time to a session."""
        # TODO: Implement bump functionality - this could extend the session duration
        # or add time to the final calculation
        session = self.sessions_repo.get_session(user_id, session_id)
        if not session or session.status not in [SessionStatus.RUNNING.value, SessionStatus.PAUSED.value]:
            return None
        return session

    def peek(self, user_id: int, session_id: str) -> Optional[Session]:
        """Get session without modifying it."""
        # TODO: Implement peek functionality - get session for display purposes
        return self.sessions_repo.get_session(user_id, session_id)
