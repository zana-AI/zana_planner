import os
import json
from typing import List, Set
from datetime import date, datetime


class NightlyStateRepository:
    """Repository for tracking which promises have been shown in nightly reminders per day."""
    
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
    
    def _get_file_path(self, user_id: int) -> str:
        """Get the nightly state file path for a user."""
        return os.path.join(self.root_dir, str(user_id), 'nightly_state.json')
    
    def _ensure_user_dir(self, user_id: int) -> None:
        """Ensure user directory exists."""
        user_dir = os.path.join(self.root_dir, str(user_id))
        os.makedirs(user_dir, exist_ok=True)
    
    def get_shown_promise_ids(self, user_id: int, current_date: date) -> Set[str]:
        """Get the set of promise IDs that have been shown today."""
        file_path = self._get_file_path(user_id)
        
        if not os.path.exists(file_path):
            return set()
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f) or {}
            
            # Check if the stored date matches current date
            stored_date_str = data.get('last_date')
            if stored_date_str:
                stored_date = date.fromisoformat(stored_date_str)
                if stored_date == current_date:
                    # Same day, return the shown promise IDs
                    return set(data.get('shown_promise_ids', []))
                else:
                    # Different day, return empty set (will be reset)
                    return set()
            
            return set()
        except Exception:
            # If there's any error reading, return empty set
            return set()
    
    def mark_promises_as_shown(self, user_id: int, promise_ids: List[str], current_date: date) -> None:
        """Mark promise IDs as shown for the current date."""
        self._ensure_user_dir(user_id)
        file_path = self._get_file_path(user_id)
        
        # Get existing shown promises for today
        existing_shown = self.get_shown_promise_ids(user_id, current_date)
        
        # Add new promise IDs
        updated_shown = existing_shown.union(set(promise_ids))
        
        # Save to file
        data = {
            'last_date': current_date.isoformat(),
            'shown_promise_ids': list(updated_shown)
        }
        
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def reset_for_new_day(self, user_id: int, current_date: date) -> None:
        """Reset state for a new day (called when date changes)."""
        file_path = self._get_file_path(user_id)
        
        # If file doesn't exist, nothing to reset
        if not os.path.exists(file_path):
            return
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f) or {}
            
            stored_date_str = data.get('last_date')
            if stored_date_str:
                stored_date = date.fromisoformat(stored_date_str)
                if stored_date != current_date:
                    # Different day, reset
                    data = {
                        'last_date': current_date.isoformat(),
                        'shown_promise_ids': []
                    }
                    with open(file_path, 'w') as f:
                        json.dump(data, f, indent=2)
        except Exception:
            # If there's an error, just create a fresh state
            self._ensure_user_dir(user_id)
            data = {
                'last_date': current_date.isoformat(),
                'shown_promise_ids': []
            }
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
