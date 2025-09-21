import os
import csv
from typing import List, Optional
from datetime import datetime

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from models.models import Session


class SessionsRepository:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def _get_file_path(self, user_id: int) -> str:
        """Get the sessions file path for a user."""
        return os.path.join(self.root_dir, str(user_id), 'sessions.csv')

    def _ensure_user_dir(self, user_id: int) -> None:
        """Ensure user directory exists."""
        user_dir = os.path.join(self.root_dir, str(user_id))
        os.makedirs(user_dir, exist_ok=True)

    def _ensure_file_exists(self, user_id: int) -> None:
        """Ensure sessions.csv exists with proper headers."""
        file_path = self._get_file_path(user_id)
        if not os.path.exists(file_path):
            self._ensure_user_dir(user_id)
            with open(file_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'session_id', 'user_id', 'promise_id', 'status', 
                    'started_at', 'ended_at', 'paused_seconds_total', 
                    'last_state_change_at', 'message_id', 'chat_id'
                ])

    def create_session(self, session: Session) -> None:
        """Create a new session."""
        self._ensure_file_exists(session.user_id)
        
        file_path = self._get_file_path(session.user_id)
        with open(file_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                session.session_id,
                session.user_id,
                session.promise_id,
                session.status,
                session.started_at.isoformat(),
                session.ended_at.isoformat() if session.ended_at else '',
                session.paused_seconds_total,
                session.last_state_change_at.isoformat() if session.last_state_change_at else '',
                session.message_id or '',
                session.chat_id or ''
            ])

    def update_session(self, session: Session) -> None:
        """Update an existing session."""
        file_path = self._get_file_path(session.user_id)
        if not os.path.exists(file_path):
            return

        # Read all sessions
        sessions = self.list_sessions(session.user_id)
        
        # Update the specific session
        updated = False
        for i, existing_session in enumerate(sessions):
            if existing_session.session_id == session.session_id:
                sessions[i] = session
                updated = True
                break
        
        if not updated:
            return
        
        # Write back to file
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'session_id', 'user_id', 'promise_id', 'status', 
                'started_at', 'ended_at', 'paused_seconds_total', 
                'last_state_change_at', 'message_id', 'chat_id'
            ])
            
            for sess in sessions:
                writer.writerow([
                    sess.session_id,
                    sess.user_id,
                    sess.promise_id,
                    sess.status,
                    sess.started_at.isoformat(),
                    sess.ended_at.isoformat() if sess.ended_at else '',
                    sess.paused_seconds_total,
                    sess.last_state_change_at.isoformat() if sess.last_state_change_at else '',
                    sess.message_id or '',
                    sess.chat_id or ''
                ])

    def get_session(self, user_id: int, session_id: str) -> Optional[Session]:
        """Get a specific session by ID."""
        sessions = self.list_sessions(user_id)
        for session in sessions:
            if session.session_id == session_id:
                return session
        return None

    def list_sessions(self, user_id: int) -> List[Session]:
        """Get all sessions for a user."""
        file_path = self._get_file_path(user_id)
        if not os.path.exists(file_path):
            return []

        try:
            if PANDAS_AVAILABLE:
                df = pd.read_csv(file_path)
                if df.empty:
                    return []

                sessions = []
                for _, row in df.iterrows():
                    session = Session(
                        session_id=str(row['session_id']),
                        user_id=int(row['user_id']),
                        promise_id=str(row['promise_id']),
                        status=str(row['status']),
                        started_at=pd.to_datetime(row['started_at']).to_pydatetime(),
                        ended_at=pd.to_datetime(row['ended_at']).to_pydatetime() if pd.notna(row['ended_at']) else None,
                        paused_seconds_total=int(row['paused_seconds_total']),
                        last_state_change_at=pd.to_datetime(row['last_state_change_at']).to_pydatetime() if pd.notna(row['last_state_change_at']) else None,
                        message_id=int(row['message_id']) if pd.notna(row['message_id']) and str(row['message_id']).strip() else None,
                        chat_id=int(row['chat_id']) if pd.notna(row['chat_id']) and str(row['chat_id']).strip() else None
                    )
                    sessions.append(session)
                
                return sessions
            else:
                # Fallback to manual CSV parsing
                sessions = []
                with open(file_path, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        session = Session(
                            session_id=str(row['session_id']),
                            user_id=int(row['user_id']),
                            promise_id=str(row['promise_id']),
                            status=str(row['status']),
                            started_at=datetime.fromisoformat(row['started_at']),
                            ended_at=datetime.fromisoformat(row['ended_at']) if row['ended_at'] else None,
                            paused_seconds_total=int(row['paused_seconds_total']),
                            last_state_change_at=datetime.fromisoformat(row['last_state_change_at']) if row['last_state_change_at'] else None,
                            message_id=int(row['message_id']) if row['message_id'] and row['message_id'].strip() else None,
                            chat_id=int(row['chat_id']) if row['chat_id'] and row['chat_id'].strip() else None
                        )
                        sessions.append(session)
                
                return sessions
        except Exception:
            return []

    def list_active_sessions(self, user_id: int) -> List[Session]:
        """Get all active (running or paused) sessions for a user."""
        all_sessions = self.list_sessions(user_id)
        return [s for s in all_sessions if s.status in ['running', 'paused']]
