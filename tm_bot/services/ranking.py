from typing import List, Tuple
from datetime import datetime, timedelta

from models.models import Promise
from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from repositories.settings_repo import SettingsRepository


class RankingService:
    def __init__(self, promises_repo: PromisesRepository, actions_repo: ActionsRepository, settings_repo: SettingsRepository):
        self.promises_repo = promises_repo
        self.actions_repo = actions_repo
        self.settings_repo = settings_repo

    def score_promises_for_today(self, user_id: int, now: datetime) -> List[Tuple[Promise, float]]:
        """
        Score promises for today using rule-based signals.
        Higher scores indicate higher priority.
        """
        promises = self.promises_repo.list_promises(user_id)
        actions = self.actions_repo.list_actions(user_id)
        
        # Filter active promises
        active_promises = [p for p in promises if p.start_date and p.start_date <= now.date()]
        
        scored_promises = []
        for promise in active_promises:
            score = self._calculate_promise_score(promise, actions, now)
            scored_promises.append((promise, score))
        
        return scored_promises

    def _calculate_promise_score(self, promise: Promise, actions: List, now: datetime) -> float:
        """Calculate score for a single promise."""
        score = 0.0
        
        # Signal 1: Weekly deficit (behind target this week)
        weekly_deficit = self._get_weekly_deficit(promise, actions, now)
        score += weekly_deficit * 2.0  # Weight: 2.0
        
        # Signal 2: Recency decay (not touched in N days)
        recency_decay = self._get_recency_decay(promise, actions, now)
        score += recency_decay * 1.5  # Weight: 1.5
        
        # Signal 3: Touched today penalty (small penalty for already worked on)
        touched_today_penalty = self._get_touched_today_penalty(promise, actions, now)
        score -= touched_today_penalty * 0.5  # Weight: -0.5
        
        # Signal 4: Day of week fit (optional small boost)
        day_boost = self._get_day_of_week_boost(promise, now)
        score += day_boost * 0.3  # Weight: 0.3
        
        return score

    def _get_weekly_deficit(self, promise: Promise, actions: List, now: datetime) -> float:
        """Calculate how behind the promise is this week."""
        # Get week boundaries (Monday at 3 AM)
        monday = now - timedelta(days=now.weekday())
        week_start = monday.replace(hour=3, minute=0, second=0, microsecond=0)
        if now < week_start:
            week_start -= timedelta(days=7)
        
        # Calculate hours spent this week
        weekly_actions = [a for a in actions 
                         if a.promise_id == promise.id 
                         and week_start <= a.at <= now]
        hours_spent = sum(a.time_spent for a in weekly_actions)
        
        # Calculate expected hours by now (proportional to week progress)
        week_progress = (now - week_start).total_seconds() / (7 * 24 * 3600)
        expected_hours = promise.hours_per_week * week_progress
        
        # Return deficit (positive if behind, negative if ahead)
        return max(0, expected_hours - hours_spent)

    def _get_recency_decay(self, promise: Promise, actions: List, now: datetime) -> float:
        """Calculate recency decay score (higher if not touched recently)."""
        promise_actions = [a for a in actions if a.promise_id == promise.id]
        
        if not promise_actions:
            # Never worked on - high priority
            return 3.0
        
        # Get most recent action
        most_recent = max(promise_actions, key=lambda a: a.at)
        days_since = (now - most_recent.at).days
        
        # Exponential decay: score decreases as days since last action increases
        if days_since == 0:
            return 0.0  # Worked on today
        elif days_since == 1:
            return 1.0  # Worked on yesterday
        elif days_since <= 3:
            return 2.0  # Worked on within 3 days
        else:
            return min(3.0, days_since * 0.5)  # Cap at 3.0

    def _get_touched_today_penalty(self, promise: Promise, actions: List, now: datetime) -> float:
        """Calculate penalty for already working on this promise today."""
        today = now.date()
        today_actions = [a for a in actions 
                        if a.promise_id == promise.id 
                        and a.at.date() == today]
        
        if not today_actions:
            return 0.0
        
        # Small penalty for already working on it today
        return 1.0

    def _get_day_of_week_boost(self, promise: Promise, now: datetime) -> float:
        """Calculate day of week boost (optional feature)."""
        # For now, return 0 (no day-specific logic)
        # Future: could boost certain promises on certain days
        return 0.0

    def top_n(self, user_id: int, now: datetime, n: int = 3) -> List[Promise]:
        """Get top N promises for today."""
        scores = self.score_promises_for_today(user_id, now)
        # Sort by score (descending) and take top N
        sorted_promises = sorted(scores, key=lambda t: t[1], reverse=True)
        return [promise for promise, _ in sorted_promises[:n]]
