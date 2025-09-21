import os
import csv
from typing import List, Optional
from datetime import datetime

import pandas as pd
# PANDAS_AVAILABLE = True

from models.models import Action


class ActionsRepository:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def _get_file_path(self, user_id: int) -> str:
        """Get the actions file path for a user."""
        return os.path.join(self.root_dir, str(user_id), 'actions.csv')

    def _ensure_user_dir(self, user_id: int) -> None:
        """Ensure user directory exists."""
        user_dir = os.path.join(self.root_dir, str(user_id))
        os.makedirs(user_dir, exist_ok=True)

    def _ensure_file_exists(self, user_id: int) -> None:
        """Ensure actions.csv exists with proper headers."""
        file_path = self._get_file_path(user_id)
        if not os.path.exists(file_path):
            self._ensure_user_dir(user_id)
            with open(file_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['user_id', 'promise_id', 'action', 'time_spent', 'at'])

    def append_action(self, action: Action) -> None:
        """Add a new action to the CSV file."""
        self._ensure_file_exists(action.user_id)
        
        file_path = self._get_file_path(action.user_id)
        with open(file_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                action.user_id,
                action.promise_id,
                action.action,
                action.time_spent,
                action.at.isoformat()
            ])

    def list_actions(self, user_id: int, since: Optional[datetime] = None) -> List[Action]:
        """Get all actions for a user, optionally filtered by date."""
        file_path = self._get_file_path(user_id)
        if not os.path.exists(file_path):
            return []

        try:
            df = pd.read_csv(file_path)
            if df.empty:
                return []

            actions = []
            for _, row in df.iterrows():
                action_at = pd.to_datetime(row['at']).to_pydatetime()
                
                # Filter by date if specified
                if since and action_at < since:
                    continue
                
                action = Action(
                    user_id=int(row['user_id']),
                    promise_id=str(row['promise_id']),
                    action=str(row['action']),
                    time_spent=float(row['time_spent']),
                    at=action_at
                )
                actions.append(action)
            
            return actions
        except Exception:
            return []

    def last_action_for_promise(self, user_id: int, promise_id: str) -> Optional[Action]:
        """Get the last action for a specific promise."""
        actions = self.list_actions(user_id)
        promise_actions = [a for a in actions if a.promise_id == promise_id]
        
        if not promise_actions:
            return None
        
        # Sort by timestamp and return the most recent
        return max(promise_actions, key=lambda a: a.at)

    def get_actions_df(self, user_id: int):
        """Get actions as a pandas DataFrame (for compatibility with existing code)."""
        file_path = self._get_file_path(user_id)
        if not os.path.exists(file_path):
            return pd.DataFrame(columns=['date', 'time', 'promise_id', 'time_spent'])


        try:
            df = pd.read_csv(file_path)
            if df.empty:
                return pd.DataFrame(columns=['date', 'time', 'promise_id', 'time_spent'])

            # Convert to legacy format for compatibility
            df['date'] = pd.to_datetime(df['at']).dt.date
            df['time'] = pd.to_datetime(df['at']).dt.time
            df['time_spent'] = df['time_spent'].astype(float)

            return df[['date', 'time', 'promise_id', 'time_spent']]

        except Exception:
            return pd.DataFrame(columns=['date', 'time', 'promise_id', 'time_spent'])
