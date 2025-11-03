import os
import json
from typing import List, Optional
from datetime import datetime

import pandas as pd
from models.models import Promise


class PromisesRepository:
    def __init__(self, root_dir: str):
        self.root_dir = root_dir

    def _get_file_path(self, user_id: int) -> str:
        """Get the promises file path for a user."""
        return os.path.join(self.root_dir, str(user_id), 'promises.csv')

    def _get_json_file_path(self, user_id: int) -> str:
        """Get the promises JSON file path for a user (legacy format)."""
        return os.path.join(self.root_dir, str(user_id), 'promises.json')

    def _ensure_user_dir(self, user_id: int) -> None:
        """Ensure user directory exists."""
        user_dir = os.path.join(self.root_dir, str(user_id))
        os.makedirs(user_dir, exist_ok=True)

    def list_promises(self, user_id: int) -> List[Promise]:
        """Get all promises for a user."""
        # Try CSV first, fallback to JSON
        csv_path = self._get_file_path(user_id)
        json_path = self._get_json_file_path(user_id)
        
        if os.path.exists(csv_path):
            return self._load_from_csv(user_id, csv_path)
        elif os.path.exists(json_path):
            return self._load_from_json(user_id, json_path)
        else:
            return []

    def _load_from_csv(self, user_id: int, file_path: str) -> List[Promise]:
        """Load promises from CSV file using pandas."""
        try:
            df = pd.read_csv(file_path)
            promises: List[Promise] = []
            for _, row in df.iterrows():
                promise = Promise(
                    user_id=user_id,
                    id=str(row.get('id', '')),
                    text=str(row.get('text', '')),
                    hours_per_week=float(row.get('hours_per_week', 0)),
                    recurring=bool(row.get('recurring', False)),
                    start_date=pd.to_datetime(row.get('start_date')).date() if pd.notna(row.get('start_date')) else None,
                    end_date=pd.to_datetime(row.get('end_date')).date() if pd.notna(row.get('end_date')) else None,
                    angle_deg=int(row.get('angle_deg', 0)),
                    radius=int(row.get('radius', 0)) if pd.notna(row.get('radius')) else 0
                )
                promises.append(promise)
            return promises
        except Exception as e:
            print(f"Error loading promises from CSV: {str(e)}")
            return []

    def _load_from_json(self, uesr_id: int, file_path: str) -> List[Promise]:
        """Load promises from JSON file (legacy format)."""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            promises = []
            for item in data:
                promise = Promise(
                    user_id=uesr_id,
                    id=item.get('id', ''),
                    text=item.get('text', ''),
                    hours_per_week=float(item.get('hours_per_week', 0)),
                    recurring=bool(item.get('recurring', False)),
                    start_date=datetime.strptime(item.get('start_date', ''), '%Y-%m-%d').date() if item.get('start_date') else None,
                    end_date=datetime.strptime(item.get('end_date', ''), '%Y-%m-%d').date() if item.get('end_date') else None,
                    angle_deg=int(item.get('angle_deg', 0)),
                    radius=int(item.get('radius', 0)) if item.get('radius') is not None else 0
                )
                promises.append(promise)
            return promises
        except Exception as e:
            print(f"Error loading promises from JSON: {str(e)}")
            return []

    def get_promise(self, user_id: int, promise_id: str) -> Optional[Promise]:
        """Get a specific promise by ID."""
        promises = self.list_promises(user_id)
        for promise in promises:
            if promise.id == promise_id:
                return promise
        return None

    def upsert_promise(self, user_id: int, promise: Promise) -> None:
        """Create or update a promise."""
        self._ensure_user_dir(user_id)
        
        # Load existing promises
        promises = self.list_promises(user_id)
        
        # Update or add the promise
        updated = False
        for i, existing_promise in enumerate(promises):
            if existing_promise.id == promise.id:
                promises[i] = promise
                updated = True
                break
        
        if not updated:
            promises.append(promise)
        
        # Save to CSV format
        self._save_to_csv(user_id, promises)

    def _save_to_csv(self, user_id: int, promises: List[Promise]) -> None:
        """Save promises to CSV format using pandas."""
        file_path = self._get_file_path(user_id)

        data = []
        for promise in promises:
            data.append({
                'id': promise.id,
                'text': promise.text,
                'hours_per_week': promise.hours_per_week,
                'recurring': promise.recurring,
                'start_date': promise.start_date.isoformat() if promise.start_date else '',
                'end_date': promise.end_date.isoformat() if promise.end_date else '',
                'angle_deg': promise.angle_deg,
                'radius': promise.radius
            })

        df = pd.DataFrame(data)
        df.to_csv(file_path, index=False)

    def delete_promise(self, user_id: int, promise_id: str) -> None:
        """Delete a promise by ID."""
        promises = self.list_promises(user_id)
        promises = [p for p in promises if p.id != promise_id]
        self._save_to_csv(user_id, promises)
