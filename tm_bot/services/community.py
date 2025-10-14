import random
from typing import List, Optional
from datetime import datetime

from repositories.community_repo import CommunityRepository
from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from repositories.settings_repo import SettingsRepository
from models.models import PromiseIdea, SharedAchievement, Promise


class CommunityService:
    """Service for managing community features like shared promise ideas and achievements."""
    
    def __init__(self, community_repo: CommunityRepository, promises_repo: PromisesRepository, 
                 actions_repo: ActionsRepository, settings_repo: SettingsRepository):
        self.community_repo = community_repo
        self.promises_repo = promises_repo
        self.actions_repo = actions_repo
        self.settings_repo = settings_repo
    
    def browse_promise_ideas(self, category: Optional[str] = None) -> List[PromiseIdea]:
        """Get promise ideas, optionally filtered by category."""
        ideas = self.community_repo.get_promise_ideas()
        
        if category:
            ideas = [idea for idea in ideas if idea.category.lower() == category.lower()]
        
        # Sort by popularity (descending)
        ideas.sort(key=lambda x: x.popularity, reverse=True)
        return ideas
    
    def format_promise_ideas_for_display(self, ideas: List[PromiseIdea], limit: int = 5) -> str:
        """Format promise ideas for display in Telegram."""
        if not ideas:
            return "No promise ideas found."
        
        text = "🌟 *Popular Promise Ideas*\n\n"
        
        for i, idea in enumerate(ideas[:limit], 1):
            text += f"{i}. *{idea.text}*\n"
            text += f"   📊 {idea.popularity} adoptions • {idea.avg_hours_per_week:.1f}h/week\n"
            text += f"   🏷️ {idea.category.title()}\n\n"
        
        return text
    
    def adopt_promise_idea(self, user_id: int, idea_id: str) -> str:
        """Adopt a promise idea as the user's own promise."""
        idea = self.community_repo.get_promise_idea_by_id(idea_id)
        if not idea:
            return f"Promise idea with ID '{idea_id}' not found."
        
        # Create a new promise for the user
        promise_id = self._generate_promise_id(user_id, 'C')  # C for Community
        
        promise = Promise(
            id=promise_id,
            text=idea.text,
            hours_per_week=idea.avg_hours_per_week,
            recurring=True,
            start_date=datetime.now().date(),
            end_date=datetime(datetime.now().year, 12, 31).date(),
            angle_deg=0,
            radius=0
        )
        
        self.promises_repo.upsert_promise(user_id, promise)
        
        # Increment popularity
        self.community_repo.increment_popularity(idea_id)
        
        return f"✅ Adopted promise idea: *{idea.text}*\nAdded as #{promise_id} with {idea.avg_hours_per_week:.1f}h/week target."
    
    def share_user_achievement(self, user_id: int, promise_id: str, hours_spent: float, period: str = "this week") -> str:
        """Create a shareable achievement from user's recent activity."""
        # Get user settings to check if sharing is enabled
        settings = self.settings_repo.get_settings(user_id)
        if not settings.share_data:
            return "Sharing is disabled in your settings."
        
        # Get the promise details
        promise = self.promises_repo.get_promise(user_id, promise_id)
        if not promise:
            return f"Promise with ID '{promise_id}' not found."
        
        # Create achievement
        achievement_id = f"ach_{user_id}_{int(datetime.now().timestamp())}"
        achievement = SharedAchievement(
            id=achievement_id,
            username=settings.display_name,
            promise_text=promise.text,
            hours_spent=hours_spent,
            period=period,
            shared_at=datetime.now()
        )
        
        self.community_repo.add_achievement(achievement)
        
        return f"🎉 Achievement shared! *{settings.display_name}* spent {hours_spent:.1f}h on *{promise.text}* {period}."
    
    def get_daily_inspiration(self, limit: int = 2) -> str:
        """Get random achievements for daily inspiration."""
        achievements = self.community_repo.get_achievements(limit=limit * 3)  # Get more to randomize from
        
        if not achievements:
            return ""
        
        # Randomly select achievements
        selected = random.sample(achievements, min(limit, len(achievements)))
        
        text = "🌟 *Community Highlights*\n\n"
        for achievement in selected:
            text += f"• *{achievement.username}* spent {achievement.hours_spent:.1f}h on *{achievement.promise_text}* {achievement.period}\n"
        
        return text
    
    def get_achievements_feed(self, limit: int = 10) -> str:
        """Get recent achievements for the community feed."""
        achievements = self.community_repo.get_achievements(limit)
        
        if not achievements:
            return "No recent achievements to show."
        
        text = "🏆 *Recent Community Achievements*\n\n"
        for achievement in achievements:
            text += f"• *{achievement.username}*: {achievement.hours_spent:.1f}h on *{achievement.promise_text}* {achievement.period}\n"
        
        return text
    
    def get_categories(self) -> List[str]:
        """Get all available promise idea categories."""
        ideas = self.community_repo.get_promise_ideas()
        categories = list(set(idea.category for idea in ideas))
        categories.sort()
        return categories
    
    def _generate_promise_id(self, user_id: int, prefix: str) -> str:
        """Generate a unique promise ID."""
        timestamp = int(datetime.now().timestamp())
        return f"{prefix}{user_id}{timestamp % 10000}"
