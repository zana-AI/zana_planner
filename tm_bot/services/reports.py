from typing import Dict, Any
from datetime import datetime, timedelta

from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from utils.time_utils import get_week_range


class ReportsService:
    def __init__(self, promises_repo: PromisesRepository, actions_repo: ActionsRepository):
        self.promises_repo = promises_repo
        self.actions_repo = actions_repo

    def get_weekly_summary(self, user_id: int, ref_time: datetime) -> Dict[str, Any]:
        """Get weekly summary data for a user."""
        # Get week boundaries
        week_start, week_end = get_week_range(ref_time)
        
        # Get all promises
        promises = self.promises_repo.list_promises(user_id)
        
        # Get actions from this week
        actions = self.actions_repo.list_actions(user_id, since=week_start)
        
        # Initialize report data
        report_data = {}
        for promise in promises:
            # Check if promise is active (start date has passed)
            if promise.start_date and promise.start_date <= ref_time.date():
                report_data[promise.id] = {
                    'text': promise.text,
                    'hours_promised': promise.hours_per_week,
                    'hours_spent': 0.0
                }
        
        # Accumulate hours for each promise
        for action in actions:
            if action.at >= week_start and action.at <= week_end:
                promise_id = action.promise_id
                if promise_id in report_data:
                    report_data[promise_id]['hours_spent'] += action.time_spent
        
        return report_data

    def get_promise_summary(self, user_id: int, promise_id: str, ref_time: datetime) -> Dict[str, Any]:
        """Get summary for a specific promise."""
        promise = self.promises_repo.get_promise(user_id, promise_id)
        if not promise:
            return {}
        
        # Get week boundaries
        week_start, week_end = get_week_range(ref_time)
        
        # Get actions for this promise
        all_actions = self.actions_repo.list_actions(user_id)
        promise_actions = [a for a in all_actions if a.promise_id == promise_id]
        
        # Calculate weekly hours
        weekly_actions = [a for a in promise_actions if week_start <= a.at <= week_end]
        weekly_hours = sum(a.time_spent for a in weekly_actions)
        
        # Calculate total hours
        total_hours = sum(a.time_spent for a in promise_actions)
        
        # Calculate streak
        streak = self._calculate_streak(promise_actions, ref_time)
        
        return {
            'promise': promise,
            'weekly_hours': weekly_hours,
            'total_hours': total_hours,
            'streak': streak,
            'recent_actions': promise_actions[-3:] if promise_actions else []
        }

    def _calculate_streak(self, actions: list, ref_time: datetime) -> int:
        """Calculate the current streak for a promise."""
        if not actions:
            return 0
        
        # Sort actions by date (most recent first)
        actions.sort(key=lambda a: a.at, reverse=True)
        
        # Get unique dates
        unique_dates = []
        seen_dates = set()
        for action in actions:
            action_date = action.at.date()
            if action_date not in seen_dates:
                unique_dates.append(action_date)
                seen_dates.add(action_date)
        
        if not unique_dates:
            return 0
        
        # Check if the last action was today or yesterday
        current_date = ref_time.date()
        last_action_date = unique_dates[0]
        
        if last_action_date == current_date:
            # Count consecutive days from today backwards
            streak = 0
            expected_date = current_date
            for action_date in unique_dates:
                if action_date == expected_date:
                    streak += 1
                    expected_date -= timedelta(days=1)
                else:
                    break
            return streak
        elif last_action_date == current_date - timedelta(days=1):
            # Count consecutive days from yesterday backwards
            streak = 0
            expected_date = current_date - timedelta(days=1)
            for action_date in unique_dates:
                if action_date == expected_date:
                    streak += 1
                    expected_date -= timedelta(days=1)
                else:
                    break
            return streak
        else:
            # Count negative streak (days since last action)
            days_since = (current_date - last_action_date).days
            return -days_since
