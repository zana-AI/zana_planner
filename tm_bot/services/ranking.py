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
        
        # Filter active promises (must have started and not ended)
        active_promises = [
            p for p in promises 
            if p.start_date and p.start_date <= now.date()
            and (not p.end_date or p.end_date >= now.date())
        ]
        
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
        """Calculate how behind the promise is this week"""
        tz = now.tzinfo  # may be None; if not None, we’ll localize naive datetimes to this tz

        def as_tz(dt: datetime) -> datetime:
            if tz is None:  # all naive: keep as-is
                return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
            # now is aware -> make dt aware in same tz if it’s naive, or convert if aware in another tz
            return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)

        # week start: Monday 03:00 in user's tz (or naive if tz is None)
        monday = now - timedelta(days=now.weekday())
        week_start = monday.replace(hour=3, minute=0, second=0, microsecond=0)
        if now < week_start:
            week_start -= timedelta(days=7)

        # ensure both bounds are in the same tz domain as the actions we’ll compare to
        now_local = as_tz(now)
        week_start_local = as_tz(week_start)

        # hours spent this week for this promise
        weekly_actions = [
            a for a in actions
            if a.promise_id == promise.id and week_start_local <= as_tz(a.at) <= now_local
        ]
        hours_spent = sum(float(getattr(a, "time_spent", 0.0) or 0.0) for a in weekly_actions)

        # expected by proportional progress through the week
        week_seconds = 7 * 24 * 3600
        progress = (now_local - week_start_local).total_seconds() / week_seconds
        progress = max(0.0, min(1.0, progress))  # clamp

        hpw = float(getattr(promise, "hours_per_week", 0.0) or 0.0)
        expected_hours = hpw * progress

        # positive if behind, 0 if on/ahead
        return max(0.0, expected_hours - hours_spent)

    def _get_recency_decay(self, promise: Promise, actions: list, now: datetime) -> float:
        """Calculate recency decay score (higher if not touched recently)."""
        # keep only this promise's actions
        promise_actions = [a for a in actions if a.promise_id == promise.id]
        if not promise_actions:
            return 3.0  # never worked on -> high priority

        # Normalize datetimes to the tz of 'now' (or keep naive if 'now' is naive)
        tz = now.tzinfo

        def as_tz(dt: datetime) -> datetime:
            if tz is None:
                # controller is using naive 'now' -> keep everything naive
                return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
            # controller is using aware 'now' -> localize/convert actions to the same tz
            return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)

        now_local = as_tz(now)
        # Find most recent action in the same tz domain
        most_recent = max(promise_actions, key=lambda a: as_tz(a.at))
        last_at_local = as_tz(most_recent.at)

        # Days since last action (>= 0)
        delta_days = max(0, (now_local.date() - last_at_local.date()).days)

        # Piecewise scoring (cap at 3.0)
        if delta_days == 0:
            return 0.0  # touched today
        elif delta_days == 1:
            return 1.0  # yesterday
        elif delta_days <= 3:
            return 2.0  # within 3 days
        else:
            return min(3.0, delta_days * 0.5)

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
