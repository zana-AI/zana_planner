"""
Adapter to provide compatibility with the existing PlannerAPI interface
while using the new repository and service layers underneath.
"""
import os
import json
from datetime import datetime, date
from typing import List, Dict, Optional

from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from repositories.settings_repo import SettingsRepository
from repositories.sessions_repo import SessionsRepository
from services.reports import ReportsService
from services.ranking import RankingService
from services.reminders import RemindersService
from services.sessions import SessionsService
from models.models import Promise, Action, UserSettings
from models.enums import ActionType


class PlannerAPIAdapter:
    """Adapter that provides the old PlannerAPI interface using new services."""
    
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        
        # Initialize repositories
        self.promises_repo = PromisesRepository(root_dir)
        self.actions_repo = ActionsRepository(root_dir)
        self.settings_repo = SettingsRepository(root_dir)
        self.sessions_repo = SessionsRepository(root_dir)
        
        # Initialize services
        self.reports_service = ReportsService(self.promises_repo, self.actions_repo)
        self.ranking_service = RankingService(self.promises_repo, self.actions_repo, self.settings_repo)
        self.reminders_service = RemindersService(self.ranking_service, self.settings_repo)
        self.sessions_service = SessionsService(self.sessions_repo, self.actions_repo)

    # Promise methods
    def add_promise(self, user_id, promise_text: str, num_hours_promised_per_week: float, 
                   recurring: bool = False, start_date: Optional[datetime] = None, 
                   end_date: Optional[datetime] = None, promise_angle_deg: int = 0, 
                   promise_radius: Optional[int] = 0):
        """Add a new promise."""
        try:
            if not promise_text or not isinstance(promise_text, str):
                raise ValueError("Promise text must be a non-empty string")
            if not isinstance(num_hours_promised_per_week, (int, float)) or num_hours_promised_per_week <= 0:
                raise ValueError("Hours promised must be a positive number")

            # Generate promise ID
            promise_id = self._generate_promise_id(user_id, 'P' if recurring else 'T')
            
            if not start_date:
                start_date = datetime.now().date()
            if not end_date:
                end_date = datetime(datetime.now().year, 12, 31).date()

            promise = Promise(
                id=promise_id,
                text=promise_text.replace(" ", "_"),
                hours_per_week=num_hours_promised_per_week,
                recurring=recurring,
                start_date=start_date,
                end_date=end_date,
                angle_deg=promise_angle_deg,
                radius=promise_radius or 0
            )

            self.promises_repo.upsert_promise(user_id, promise)
            return f"#{promise_id} Promise '{promise_text}' added successfully."

        except (ValueError, FileNotFoundError) as e:
            raise RuntimeError(f"Failed to add promise: {str(e)}")

    def get_promises(self, user_id) -> List[Dict]:
        """Get all promises for a user (legacy format)."""
        promises = self.promises_repo.list_promises(user_id)
        return [self._promise_to_dict(p) for p in promises]

    def delete_promise(self, user_id, promise_id: str):
        """Delete a promise."""
        self.promises_repo.delete_promise(user_id, promise_id)
        return f"Promise #{promise_id} deleted successfully."

    def update_promise_start_date(self, user_id, promise_id: str, new_start_date: date) -> str:
        """Update promise start date."""
        promise = self.promises_repo.get_promise(user_id, promise_id)
        if not promise:
            return f"Promise with ID '{promise_id}' not found."
        
        promise.start_date = new_start_date
        self.promises_repo.upsert_promise(user_id, promise)
        return f"Promise #{promise_id} start date updated to {new_start_date}."

    # Action methods
    def add_action(self, user_id, promise_id: str, time_spent: float, action_datetime: Optional[datetime] = None) -> str:
        """Add an action."""
        # Validate promise exists
        if not self.promises_repo.get_promise(user_id, promise_id):
            return f"Promise with ID '{promise_id}' not found."

        if time_spent <= 0:
            return "Time spent must be a positive number."

        if not action_datetime:
            action_datetime = datetime.now()

        action = Action(
            user_id=user_id,
            promise_id=promise_id,
            action=ActionType.LOG_TIME.value,
            time_spent=time_spent,
            at=action_datetime
        )

        self.actions_repo.append_action(action)
        return f"Action logged for promise ID '{promise_id}'."

    def get_actions(self, user_id):
        """Get all actions for a user (legacy format)."""
        actions = self.actions_repo.list_actions(user_id)
        return [[a.at.date(), a.at.time(), a.promise_id, a.time_spent] for a in actions]

    def get_actions_df(self, user_id):
        """Get actions as DataFrame (for compatibility)."""
        return self.actions_repo.get_actions_df(user_id)

    def get_last_action_on_promise(self, user_id, promise_id: str):
        """Get last action for a promise (legacy format)."""
        action = self.actions_repo.last_action_for_promise(user_id, promise_id)
        if not action:
            return None
        
        # Return in legacy UserAction format
        from schema import UserAction
        return UserAction(
            action_date=action.at.date(),
            action_time=action.at.time().strftime("%H:%M:%S"),
            promise_id=action.promise_id,
            time_spent=action.time_spent
        )

    # Progress and reporting methods
    def get_promise_weekly_progress(self, user_id, promise_id: str) -> float:
        """Get weekly progress for a promise."""
        summary = self.reports_service.get_promise_summary(user_id, promise_id, datetime.now())
        if not summary:
            return 0.0
        
        promise = summary['promise']
        weekly_hours = summary['weekly_hours']
        return round(weekly_hours / (promise.hours_per_week + 1e-6), 2)

    def get_weekly_report(self, user_id, reference_time=None):
        """Get weekly report."""
        if not reference_time:
            reference_time = datetime.now()
        
        summary = self.reports_service.get_weekly_summary(user_id, reference_time)
        return self._format_weekly_report(summary)

    def get_promise_report(self, user_id, promise_id: str) -> str:
        """Get promise report."""
        summary = self.reports_service.get_promise_summary(user_id, promise_id, datetime.now())
        if not summary:
            return f"Promise with ID '{promise_id}' not found."
        
        return self._format_promise_report(summary)

    def get_promise_streak(self, user_id, promise_id: str) -> int:
        """Get promise streak."""
        summary = self.reports_service.get_promise_summary(user_id, promise_id, datetime.now())
        return summary.get('streak', 0) if summary else 0

    # Settings methods
    def update_setting(self, user_id, setting_key, setting_value):
        """Update user setting."""
        settings = self.settings_repo.get_settings(user_id)
        
        if setting_key == 'timezone':
            settings.timezone = setting_value
        elif setting_key == 'nightly_hh':
            settings.nightly_hh = int(setting_value)
        elif setting_key == 'nightly_mm':
            settings.nightly_mm = int(setting_value)
        
        self.settings_repo.save_settings(settings)
        return f"Setting '{setting_key}' updated to '{setting_value}'."

    # Utility methods
    def _generate_promise_id(self, user_id, promise_type='P'):
        """Generate unique promise ID."""
        promises = self.promises_repo.list_promises(user_id)
        last_id = 0
        
        if promises:
            try:
                promise_ids = [p.id for p in promises if p.id.startswith(promise_type)]
                numeric_ids = [int(p_id[1:]) for p_id in promise_ids]
                last_id = sorted(numeric_ids)[-1] if numeric_ids else 0
            except Exception:
                pass
        
        return f"{promise_type}{(last_id+1):02d}"

    def _promise_to_dict(self, promise: Promise) -> Dict:
        """Convert Promise model to legacy dict format."""
        return {
            'id': promise.id,
            'text': promise.text,
            'hours_per_week': promise.hours_per_week,
            'recurring': promise.recurring,
            'start_date': promise.start_date.isoformat() if promise.start_date else '',
            'end_date': promise.end_date.isoformat() if promise.end_date else '',
            'angle_deg': promise.angle_deg,
            'radius': promise.radius
        }

    def _format_weekly_report(self, summary: Dict) -> str:
        """Format weekly report from summary data."""
        if not summary:
            return "No data available for this week."
        
        report_lines = []
        for promise_id, data in summary.items():
            hours_promised = data['hours_promised']
            hours_spent = data['hours_spent']
            progress = min(100, int((hours_spent / hours_promised) * 100)) if hours_promised > 0 else 0

            bar_width = 10
            filled_length = (progress * bar_width) // 100
            empty_length = bar_width - filled_length
            progress_bar = f"{'█' * filled_length}{'_' * empty_length}"

            if progress < 30:
                diamond = "🔴"
            elif progress < 60:
                diamond = "🟠"
            elif progress < 90:
                diamond = "🟡"
            else:
                diamond = "✅"

            report_lines.append(
                f"{diamond} #{promise_id} **{data['text'][:36].replace('_', ' ')}**:\n"
                f" └──`[{progress_bar}] {progress:2d}%` ({hours_spent:.1f}/{hours_promised:.1f} h)"
            )

        return "\n".join(report_lines)

    def _format_promise_report(self, summary: Dict) -> str:
        """Format promise report from summary data."""
        promise = summary['promise']
        weekly_hours = summary['weekly_hours']
        total_hours = summary['total_hours']
        streak = summary['streak']
        
        progress = min(100, int((weekly_hours / promise.hours_per_week) * 100)) if promise.hours_per_week > 0 else 0
        
        if streak < 0:
            streak_str = f"{-streak} days since last action"
        elif streak == 0:
            streak_str = "🆕 No actions yet"
        else:
            streak_str = f"🔥 {streak} day{'s' if streak > 1 else ''} in a row"

        report = (
            f"**Report #{promise.id}**\n"
            f"*{promise.text.replace('_', ' ')}*\n"
            f"**You promised:** {promise.hours_per_week:.1f} hours/week\n"
            f"**This week:** {weekly_hours:.1f}/{promise.hours_per_week:.1f} hours "
            f"**Total {total_hours:.1f} hours spent** since {promise.start_date}\n"
            f"({progress}%)\n"
            f"**Streak:** {streak_str}"
        )

        return report
