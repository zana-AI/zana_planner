import os
import json
from typing import List, Optional
from datetime import datetime

from models.models import PromiseIdea, SharedAchievement


class CommunityRepository:
    """Repository for managing community data (promise ideas and achievements)."""
    
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.global_dir = os.path.join(root_dir, "GLOBAL")
        self.promise_ideas_file = os.path.join(self.global_dir, "promise_ideas.ndjson")
        self.achievements_file = os.path.join(self.global_dir, "achievements.ndjson")
        
        # Ensure global directory exists
        os.makedirs(self.global_dir, exist_ok=True)
    
    def _ensure_files_exist(self) -> None:
        """Ensure NDJSON files exist."""
        for file_path in [self.promise_ideas_file, self.achievements_file]:
            if not os.path.exists(file_path):
                with open(file_path, 'w') as f:
                    pass  # Create empty file
    
    def get_promise_ideas(self) -> List[PromiseIdea]:
        """Read all promise ideas from NDJSON file."""
        self._ensure_files_exist()
        ideas = []
        
        try:
            with open(self.promise_ideas_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        idea = PromiseIdea(
                            id=data['id'],
                            text=data['text'],
                            category=data['category'],
                            popularity=data['popularity'],
                            avg_hours_per_week=data['avg_hours_per_week'],
                            created_at=datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
                        )
                        ideas.append(idea)
        except Exception:
            pass  # Return empty list on error
        
        return ideas
    
    def add_promise_idea(self, idea: PromiseIdea) -> None:
        """Append a new promise idea to the NDJSON file."""
        self._ensure_files_exist()
        
        data = {
            'id': idea.id,
            'text': idea.text,
            'category': idea.category,
            'popularity': idea.popularity,
            'avg_hours_per_week': idea.avg_hours_per_week,
            'created_at': idea.created_at.isoformat() + 'Z'
        }
        
        with open(self.promise_ideas_file, 'a') as f:
            f.write(json.dumps(data) + '\n')
    
    def increment_popularity(self, idea_id: str) -> None:
        """Increment popularity count for a promise idea."""
        ideas = self.get_promise_ideas()
        
        # Find and update the idea
        for idea in ideas:
            if idea.id == idea_id:
                idea.popularity += 1
                break
        
        # Rewrite the entire file with updated data
        with open(self.promise_ideas_file, 'w') as f:
            for idea in ideas:
                data = {
                    'id': idea.id,
                    'text': idea.text,
                    'category': idea.category,
                    'popularity': idea.popularity,
                    'avg_hours_per_week': idea.avg_hours_per_week,
                    'created_at': idea.created_at.isoformat() + 'Z'
                }
                f.write(json.dumps(data) + '\n')
    
    def get_achievements(self, limit: int = 10) -> List[SharedAchievement]:
        """Get recent achievements from the NDJSON file."""
        self._ensure_files_exist()
        achievements = []
        
        try:
            with open(self.achievements_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        achievement = SharedAchievement(
                            id=data['id'],
                            username=data['username'],
                            promise_text=data['promise_text'],
                            hours_spent=data['hours_spent'],
                            period=data['period'],
                            shared_at=datetime.fromisoformat(data['shared_at'].replace('Z', '+00:00'))
                        )
                        achievements.append(achievement)
        except Exception:
            pass  # Return empty list on error
        
        # Sort by shared_at descending and limit
        achievements.sort(key=lambda x: x.shared_at, reverse=True)
        return achievements[:limit]
    
    def add_achievement(self, achievement: SharedAchievement) -> None:
        """Append a new achievement to the NDJSON file."""
        self._ensure_files_exist()
        
        data = {
            'id': achievement.id,
            'username': achievement.username,
            'promise_text': achievement.promise_text,
            'hours_spent': achievement.hours_spent,
            'period': achievement.period,
            'shared_at': achievement.shared_at.isoformat() + 'Z'
        }
        
        with open(self.achievements_file, 'a') as f:
            f.write(json.dumps(data) + '\n')
    
    def get_promise_idea_by_id(self, idea_id: str) -> Optional[PromiseIdea]:
        """Get a specific promise idea by ID."""
        ideas = self.get_promise_ideas()
        for idea in ideas:
            if idea.id == idea_id:
                return idea
        return None
