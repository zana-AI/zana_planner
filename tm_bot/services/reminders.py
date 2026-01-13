from typing import List, Tuple
from datetime import datetime

from models.models import Promise
from services.ranking import RankingService
from repositories.settings_repo import SettingsRepository


class RemindersService:
    def __init__(self, ranking: RankingService, settings_repo: SettingsRepository):
        self.ranking = ranking
        self.settings_repo = settings_repo

    def select_nightly_top(self, user_id: int, now: datetime, n: int = 3) -> List[Promise]:
        """Select top N promises for nightly reminders."""
        # Get top promises from ranking service
        top_promises = self.ranking.top_n(user_id, now, n)
        
        # Filter out inactive promises and one-offs that are completed
        filtered_promises = []
        for promise in top_promises:
            # Skip if promise hasn't started yet
            if promise.start_date and promise.start_date > now.date():
                continue
            
            # Skip if promise has ended (end_date is in the past)
            if promise.end_date and promise.end_date < now.date():
                continue
            
            # Skip non-recurring promises that have reached full weekly progress
            # (This logic would need to be implemented based on current week progress)
            # For now, include all active promises
            
            filtered_promises.append(promise)
        
        return filtered_promises[:n]

    def compute_prepings(self, user_id: int, now: datetime) -> List[Tuple[Promise, datetime]]:
        """Compute pre-ping reminders for a user."""
        # For now, return empty list (no pre-pings)
        # Future: implement pattern-based pre-pings
        return []
