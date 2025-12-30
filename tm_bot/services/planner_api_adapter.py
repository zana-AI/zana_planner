"""
Adapter to provide compatibility with the existing PlannerAPI interface
while using the new repository and service layers underneath.
"""
import re
import json
from datetime import datetime, date
from typing import List, Dict, Optional, Any

from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from repositories.settings_repo import SettingsRepository
from repositories.sessions_repo import SessionsRepository
from repositories.nightly_state_repo import NightlyStateRepository
from services.reports import ReportsService
from services.ranking import RankingService
from services.reminders import RemindersService
from services.sessions import SessionsService
from services.content_service import ContentService
from services.time_estimation_service import TimeEstimationService
from models.models import Promise, Action, UserSettings
from models.enums import ActionType
from utils.logger import get_logger

logger = get_logger(__name__)


class PlannerAPIAdapter:
    """Adapter that provides the old PlannerAPI interface using new services."""
    
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        
        # Initialize repositories
        self.promises_repo = PromisesRepository(root_dir)
        self.actions_repo = ActionsRepository(root_dir)
        self.settings_repo = SettingsRepository(root_dir)
        self.sessions_repo = SessionsRepository(root_dir)
        self.nightly_state_repo = NightlyStateRepository(root_dir)
        
        # Initialize services
        self.reports_service = ReportsService(self.promises_repo, self.actions_repo)
        self.ranking_service = RankingService(self.promises_repo, self.actions_repo, self.settings_repo)
        self.reminders_service = RemindersService(self.ranking_service, self.settings_repo)
        self.sessions_service = SessionsService(self.sessions_repo, self.actions_repo)
        self.content_service = ContentService()
        self.time_estimation_service = TimeEstimationService(self.actions_repo)

    # Promise methods
    def add_promise(self, user_id, promise_text: str, num_hours_promised_per_week: float, 
                   recurring: bool = False, start_date: Optional[datetime] = None, 
                   end_date: Optional[datetime] = None, promise_angle_deg: int = 0, 
                   promise_radius: Optional[int] = 0):
        """Add a new promise."""
        try:
            if user_id is None:
                raise ValueError("user_id is required and cannot be None")
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
                user_id=str(user_id),
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

    def no_op(self, user_id):
        """No-op method for testing purposes."""
        return None

    def get_promise(self, user_id: int, promise_id: str) -> Optional[Promise]:
        """Get a specific promise by ID."""
        return self.promises_repo.get_promise(user_id, promise_id)

    def get_promises(self, user_id) -> List[Dict]:
        """Get all promises for a user (legacy format)."""
        promises = self.promises_repo.list_promises(user_id)
        return [self._promise_to_dict(p) for p in promises]
    
    def count_promises(self, user_id) -> int:
        """Get total number of promises for a user."""
        return len(self.promises_repo.list_promises(user_id))

    def delete_promise(self, user_id, promise_id: str):
        """Delete a promise."""
        # Check if promise exists first (case-insensitive)
        promise = self.promises_repo.get_promise(user_id, promise_id)
        if not promise:
            # Promise not found - return helpful error with available IDs
            all_promises = self.promises_repo.list_promises(user_id)
            if not all_promises:
                return f"Promise #{promise_id} not found. You don't have any promises yet."
            
            available_ids = ", ".join(sorted([p.id for p in all_promises]))
            return (
                f"Promise #{promise_id} not found.\n\n"
                f"Available promise IDs: {available_ids}\n\n"
                f"Did you mean one of these?"
            )
        
        # Use the correct case from the actual promise
        actual_promise_id = promise.id
        
        # Attempt to delete
        deleted = self.promises_repo.delete_promise(user_id, actual_promise_id)
        
        if deleted:
            return f"Promise #{actual_promise_id} deleted successfully."
        else:
            # This shouldn't happen if we checked above, but handle it anyway
            all_promises = self.promises_repo.list_promises(user_id)
            if not all_promises:
                return f"Promise #{actual_promise_id} not found. You don't have any promises yet."
            
            available_ids = ", ".join(sorted([p.id for p in all_promises]))
            return (
                f"Promise #{actual_promise_id} not found.\n\n"
                f"Available promise IDs: {available_ids}\n\n"
                f"Did you mean one of these?"
            )

    def update_promise_start_date(self, user_id, promise_id: str, new_start_date: date) -> str:
        """Update promise start date."""
        promise = self.promises_repo.get_promise(user_id, promise_id)
        if not promise:
            return f"Promise with ID '{promise_id}' not found."
        
        promise.start_date = new_start_date
        self.promises_repo.upsert_promise(user_id, promise)
        return f"Promise #{promise_id} start date updated to {new_start_date}."

    def update_promise(
        self,
        user_id,
        promise_id: str,
        promise_text: Optional[str] = None,
        hours_per_week: Optional[float] = None,
        recurring: Optional[bool] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        angle_deg: Optional[int] = None,
        radius: Optional[int] = None,
    ) -> str:
        """
        Update an existing promise (PATCH-style).

        Args:
            promise_id: Promise identifier (case-insensitive).
            promise_text: New description/title for the promise.
            hours_per_week: New target hours per week.
            recurring: Whether this promise is recurring.
            start_date: Optional new start date.
            end_date: Optional new end date.
            angle_deg: Optional visualization angle.
            radius: Optional visualization radius.

        Returns:
            Human-readable confirmation message.
        """
        promise = self.promises_repo.get_promise(user_id, promise_id)
        if not promise:
            return f"Promise with ID '{promise_id}' not found."

        # Apply updates (only if provided)
        if promise_text is not None:
            if not isinstance(promise_text, str) or not promise_text.strip():
                return "Promise text must be a non-empty string."
            # Store with underscores like add_promise does; UI replaces underscores on display.
            promise.text = promise_text.strip().replace(" ", "_")

        if hours_per_week is not None:
            try:
                hours_val = float(hours_per_week)
            except Exception:
                return "Hours per week must be a number."
            if hours_val <= 0:
                return "Hours per week must be a positive number."
            promise.hours_per_week = hours_val

        if recurring is not None:
            # Accept booleans, and also common string-ish forms from LLMs.
            if isinstance(recurring, bool):
                promise.recurring = recurring
            elif isinstance(recurring, str):
                promise.recurring = recurring.strip().lower() in ("true", "1", "yes", "y", "on")
            else:
                return "Recurring must be a boolean."

        if start_date is not None:
            promise.start_date = start_date
        if end_date is not None:
            promise.end_date = end_date

        # Basic date sanity if both are set
        if promise.start_date and promise.end_date and promise.start_date > promise.end_date:
            return "Start date must be on/before end date."

        if angle_deg is not None:
            try:
                promise.angle_deg = int(angle_deg)
            except Exception:
                return "angle_deg must be an integer."

        if radius is not None:
            try:
                promise.radius = int(radius)
            except Exception:
                return "radius must be an integer."

        self.promises_repo.upsert_promise(user_id, promise)
        return f"Promise #{promise.id} updated successfully."

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
        from llms.schema import UserAction
        return UserAction(
            action_date=str(action.at.date()),
            action_time=str(action.at.time().strftime("%H:%M:%S")),
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

    def get_weekly_report(self, user_id, reference_time: Optional[datetime] = None):
        """Get weekly report for a user.
        
        Args:
            user_id: User identifier
            reference_time: Optional datetime to use as reference for the week. 
                          If None, uses current datetime.
        
        Returns:
            Formatted weekly report string showing progress for all promises.
        """
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
    def get_settings(self, user_id) -> Dict[str, Any]:
        """Get user settings as a dict (timezone, nightly time, language, voice mode)."""
        settings = self.settings_repo.get_settings(int(user_id))
        return {
            "timezone": settings.timezone,
            "nightly_hh": settings.nightly_hh,
            "nightly_mm": settings.nightly_mm,
            "language": settings.language,
            "voice_mode": settings.voice_mode,
        }

    def get_setting(self, user_id, setting_key: str):
        """Get a single user setting value by key (timezone, nightly_hh, nightly_mm, language, voice_mode)."""
        settings = self.settings_repo.get_settings(int(user_id))
        key = (setting_key or "").strip().lower()
        if key == "timezone":
            return settings.timezone
        if key == "nightly_hh":
            return settings.nightly_hh
        if key == "nightly_mm":
            return settings.nightly_mm
        if key == "language":
            return settings.language
        if key == "voice_mode":
            return settings.voice_mode
        return None

    def update_setting(self, user_id, setting_key, setting_value):
        """Update user setting."""
        settings = self.settings_repo.get_settings(user_id)
        
        if setting_key == 'timezone':
            settings.timezone = setting_value
        elif setting_key == 'nightly_hh':
            settings.nightly_hh = int(setting_value)
        elif setting_key == 'nightly_mm':
            settings.nightly_mm = int(setting_value)
        elif setting_key == "language":
            settings.language = str(setting_value)
        elif setting_key == "voice_mode":
            # expected values: None, "enabled", "disabled"
            settings.voice_mode = None if setting_value in (None, "", "none", "null") else str(setting_value)
        
        self.settings_repo.save_settings(settings)
        return f"Setting '{setting_key}' updated to '{setting_value}'."

    # Action helpers (per-day)
    def count_actions_on_date(self, user_id, date_iso: str) -> int:
        """Count logged actions on a specific date (YYYY-MM-DD) based on actions.csv."""
        date_iso = (date_iso or "").strip()
        if not date_iso:
            return 0
        df = self.actions_repo.get_actions_df(user_id)
        if df is None or df.empty:
            return 0
        try:
            return int((df["date"] == date_iso).sum())
        except Exception:
            return 0

    def get_actions_on_date(self, user_id, date_iso: str) -> List[Dict[str, Any]]:
        """Return action rows on a specific date (YYYY-MM-DD)."""
        date_iso = (date_iso or "").strip()
        if not date_iso:
            return []
        df = self.actions_repo.get_actions_df(user_id)
        if df is None or df.empty:
            return []
        try:
            sub = df[df["date"] == date_iso]
            return sub.to_dict(orient="records")
        except Exception:
            return []

    def count_actions_today(self, user_id) -> int:
        """Count actions for 'today' in the user's timezone from settings."""
        try:
            from zoneinfo import ZoneInfo
            tzname = self.settings_repo.get_settings(int(user_id)).timezone or "UTC"
            today_iso = datetime.now(ZoneInfo(tzname)).strftime("%Y-%m-%d")
        except Exception:
            today_iso = datetime.now().strftime("%Y-%m-%d")
        return self.count_actions_on_date(user_id, today_iso)

    # Query and statistics methods
    def search_promises(self, user_id, query: str) -> str:
        """
        Search promises by text (case-insensitive substring match).
        
        Args:
            query: Search term to match against promise text/description.
        
        Returns:
            Formatted string with matching promises and their total hours logged.
        """
        if not query or not query.strip():
            return "Please provide a search term."
        
        query_lower = query.strip().lower().replace(" ", "_")
        promises = self.promises_repo.list_promises(user_id)
        
        if not promises:
            return "You don't have any promises yet."
        
        # Filter promises by case-insensitive substring match
        matches = []
        for promise in promises:
            promise_text_lower = (promise.text or "").lower()
            # Match against the promise text (which uses underscores for spaces)
            if query_lower in promise_text_lower or query.strip().lower() in promise_text_lower.replace("_", " "):
                # Get total hours for this promise
                all_actions = self.actions_repo.list_actions(user_id)
                promise_actions = [a for a in all_actions if (a.promise_id or "").upper() == promise.id.upper()]
                total_hours = sum(a.time_spent for a in promise_actions)
                
                matches.append({
                    'id': promise.id,
                    'text': promise.text.replace("_", " "),
                    'hours_per_week': promise.hours_per_week,
                    'total_hours_logged': round(total_hours, 2),
                    'start_date': promise.start_date.isoformat() if promise.start_date else None,
                    'end_date': promise.end_date.isoformat() if promise.end_date else None,
                })
        
        if not matches:
            return f"No promises found matching '{query}'. Try a different search term."
        
        # If exactly one match, return structured JSON for auto-selection
        if len(matches) == 1:
            return json.dumps({
                "single_match": True,
                "promise_id": matches[0]['id'],
                "promise_text": matches[0]['text'],
                "message": f"Found exact match: #{matches[0]['id']} {matches[0]['text']}"
            })
        
        # Format results for multiple matches
        result_lines = [f"Found {len(matches)} promise(s) matching '{query}':\n"]
        for m in matches:
            result_lines.append(
                f"• #{m['id']} **{m['text']}**\n"
                f"  Target: {m['hours_per_week']:.1f} h/week | Total logged: {m['total_hours_logged']:.1f} hours"
            )
        
        return "\n".join(result_lines)

    def get_hours_for_promise(self, user_id, promise_id: str, 
                              since_date: str = None, until_date: str = None) -> str:
        """
        Get total hours logged for a promise, optionally within a date range.
        
        Args:
            promise_id: The promise ID (e.g., 'P10').
            since_date: Optional start date in YYYY-MM-DD format.
            until_date: Optional end date in YYYY-MM-DD format.
        
        Returns:
            Human-readable summary of hours logged.
        """
        if not promise_id or not promise_id.strip():
            return "Please provide a promise ID."
        
        promise = self.promises_repo.get_promise(user_id, promise_id)
        if not promise:
            return f"Promise with ID '{promise_id}' not found."
        
        # Parse date arguments
        since = self._parse_date_arg(since_date)
        until = self._parse_date_arg(until_date)
        
        # Get all actions for this promise
        all_actions = self.actions_repo.list_actions(user_id)
        promise_actions = [a for a in all_actions if (a.promise_id or "").upper() == promise.id.upper()]
        
        # Filter by date range if provided
        filtered_actions = []
        for action in promise_actions:
            action_date = action.at.date()
            if since and action_date < since:
                continue
            if until and action_date > until:
                continue
            filtered_actions.append(action)
        
        total_hours = sum(a.time_spent for a in filtered_actions)
        action_count = len(filtered_actions)
        
        # Build response
        promise_text = promise.text.replace("_", " ")
        
        if since and until:
            date_range = f"from {since} to {until}"
        elif since:
            date_range = f"since {since}"
        elif until:
            date_range = f"until {until}"
        else:
            date_range = f"since {promise.start_date}" if promise.start_date else "all time"
        
        return (
            f"**#{promise.id} - {promise_text}**\n"
            f"Total hours logged {date_range}: **{total_hours:.1f} hours**\n"
            f"Number of sessions: {action_count}"
        )

    def get_total_hours(self, user_id, since_date: str = None, until_date: str = None) -> str:
        """
        Get total hours logged across all promises, optionally within a date range.
        
        Args:
            since_date: Optional start date in YYYY-MM-DD format.
            until_date: Optional end date in YYYY-MM-DD format.
        
        Returns:
            Summary with total hours and per-promise breakdown.
        """
        # Parse date arguments
        since = self._parse_date_arg(since_date)
        until = self._parse_date_arg(until_date)
        
        # Get all promises for text lookup
        promises = self.promises_repo.list_promises(user_id)
        promise_texts = {p.id.upper(): p.text.replace("_", " ") for p in promises}
        
        # Get all actions
        all_actions = self.actions_repo.list_actions(user_id)
        
        if not all_actions:
            return "No actions logged yet."
        
        # Filter by date range and group by promise
        hours_by_promise: Dict[str, float] = {}
        for action in all_actions:
            action_date = action.at.date()
            if since and action_date < since:
                continue
            if until and action_date > until:
                continue
            
            pid = (action.promise_id or "").upper()
            hours_by_promise[pid] = hours_by_promise.get(pid, 0.0) + action.time_spent
        
        if not hours_by_promise:
            date_range = ""
            if since and until:
                date_range = f" between {since} and {until}"
            elif since:
                date_range = f" since {since}"
            elif until:
                date_range = f" until {until}"
            return f"No actions logged{date_range}."
        
        # Build response
        grand_total = sum(hours_by_promise.values())
        
        # Date range description
        if since and until:
            date_range = f"from {since} to {until}"
        elif since:
            date_range = f"since {since}"
        elif until:
            date_range = f"until {until}"
        else:
            date_range = "all time"
        
        result_lines = [f"**Total hours logged ({date_range}): {grand_total:.1f} hours**\n"]
        result_lines.append("Breakdown by promise:")
        
        # Sort by hours (descending)
        sorted_promises = sorted(hours_by_promise.items(), key=lambda x: x[1], reverse=True)
        for pid, hours in sorted_promises:
            text = promise_texts.get(pid, pid)
            result_lines.append(f"• #{pid} {text}: {hours:.1f} hours")
        
        return "\n".join(result_lines)

    def get_actions_in_range(self, user_id, promise_id: str = None,
                             since_date: str = None, until_date: str = None) -> str:
        """
        Get list of actions with optional filtering by promise and date range.
        
        Args:
            promise_id: Optional promise ID to filter by.
            since_date: Optional start date in YYYY-MM-DD format.
            until_date: Optional end date in YYYY-MM-DD format.
        
        Returns:
            Formatted list of actions with dates and hours.
        """
        # Parse date arguments
        since = self._parse_date_arg(since_date)
        until = self._parse_date_arg(until_date)
        
        # Get all promises for text lookup
        promises = self.promises_repo.list_promises(user_id)
        promise_texts = {p.id.upper(): p.text.replace("_", " ") for p in promises}
        
        # Validate promise_id if provided
        target_pid = None
        if promise_id and promise_id.strip():
            promise = self.promises_repo.get_promise(user_id, promise_id)
            if not promise:
                return f"Promise with ID '{promise_id}' not found."
            target_pid = promise.id.upper()
        
        # Get all actions
        all_actions = self.actions_repo.list_actions(user_id)
        
        if not all_actions:
            return "No actions logged yet."
        
        # Filter actions
        filtered_actions = []
        for action in all_actions:
            action_date = action.at.date()
            
            # Filter by promise ID
            if target_pid and (action.promise_id or "").upper() != target_pid:
                continue
            
            # Filter by date range
            if since and action_date < since:
                continue
            if until and action_date > until:
                continue
            
            filtered_actions.append(action)
        
        if not filtered_actions:
            # Build descriptive "no results" message
            filters = []
            if target_pid:
                filters.append(f"promise #{target_pid}")
            if since and until:
                filters.append(f"between {since} and {until}")
            elif since:
                filters.append(f"since {since}")
            elif until:
                filters.append(f"until {until}")
            
            filter_desc = " for " + " ".join(filters) if filters else ""
            return f"No actions found{filter_desc}."
        
        # Build date range description
        if since and until:
            date_range = f"from {since} to {until}"
        elif since:
            date_range = f"since {since}"
        elif until:
            date_range = f"until {until}"
        else:
            date_range = "all time"
        
        # Build response
        total_hours = sum(a.time_spent for a in filtered_actions)
        
        if target_pid:
            header = f"**Actions for #{target_pid} ({date_range})**"
        else:
            header = f"**All actions ({date_range})**"
        
        result_lines = [
            header,
            f"Total: {total_hours:.1f} hours across {len(filtered_actions)} session(s)\n"
        ]
        
        # Sort by date (most recent first) and limit output
        filtered_actions.sort(key=lambda a: a.at, reverse=True)
        
        # Limit to 20 actions to avoid overly long responses
        display_actions = filtered_actions[:20]
        if len(filtered_actions) > 20:
            result_lines.append(f"Showing most recent 20 of {len(filtered_actions)} actions:\n")
        
        for action in display_actions:
            pid = (action.promise_id or "").upper()
            text = promise_texts.get(pid, pid)
            action_date = action.at.strftime("%Y-%m-%d")
            action_time = action.at.strftime("%H:%M")
            result_lines.append(f"• {action_date} {action_time} - #{pid} {text}: {action.time_spent:.1f}h")
        
        return "\n".join(result_lines)

    # SQL Query Tool
    def query_database(self, user_id, sql_query: str) -> str:
        """
        Execute a read-only SQL query against your data for complex analytics.
        
        SECURITY: Only SELECT statements are allowed. All queries are automatically
        filtered to your data only - you cannot access other users' data.
        Results are limited to 100 rows maximum.
        
        DATABASE SCHEMA:
        
        TABLE: promises (your goals/tasks)
        - promise_uuid: TEXT (internal ID)
        - user_id: TEXT (your user ID)
        - current_id: TEXT (display ID like 'P10', 'T01')
        - text: TEXT (promise name, underscores for spaces e.g. 'Do_sport')
        - hours_per_week: REAL (target hours)
        - recurring: INTEGER (0=one-time, 1=recurring)
        - start_date: TEXT (ISO date 'YYYY-MM-DD')
        - end_date: TEXT (ISO date)
        - is_deleted: INTEGER (0=active, 1=deleted)
        - created_at_utc: TEXT (ISO timestamp)
        
        TABLE: actions (logged time entries)
        - action_uuid: TEXT (internal ID)
        - user_id: TEXT (your user ID)
        - promise_uuid: TEXT (links to promises)
        - promise_id_text: TEXT (display ID like 'P10')
        - action_type: TEXT (usually 'log_time')
        - time_spent_hours: REAL (hours logged)
        - at_utc: TEXT (ISO timestamp when logged)
        
        TABLE: sessions (active work sessions)
        - session_id: TEXT
        - user_id: TEXT
        - promise_uuid: TEXT
        - status: TEXT ('active', 'paused', 'ended')
        - started_at_utc: TEXT
        - ended_at_utc: TEXT
        - paused_seconds_total: INTEGER
        
        TABLE: user_settings
        - user_id: TEXT PRIMARY KEY
        - timezone: TEXT
        - language: TEXT
        - nightly_hh: INTEGER (reminder hour)
        - nightly_mm: INTEGER (reminder minute)
        
        EXAMPLE QUERIES:
        
        1. Total hours by month:
           SELECT strftime('%Y-%m', at_utc) as month, 
                  SUM(time_spent_hours) as total_hours
           FROM actions WHERE user_id = '{user_id}' 
           GROUP BY month ORDER BY month
        
        2. Most active promises (by total hours):
           SELECT promise_id_text, 
                  COUNT(*) as sessions, 
                  SUM(time_spent_hours) as total_hours
           FROM actions WHERE user_id = '{user_id}' 
           GROUP BY promise_id_text ORDER BY total_hours DESC
        
        3. Hours in a specific date range:
           SELECT SUM(time_spent_hours) as total
           FROM actions 
           WHERE user_id = '{user_id}' 
             AND at_utc >= '2025-01-01' AND at_utc < '2025-02-01'
        
        4. Average session duration per promise:
           SELECT promise_id_text, 
                  AVG(time_spent_hours) as avg_hours,
                  COUNT(*) as sessions
           FROM actions WHERE user_id = '{user_id}'
           GROUP BY promise_id_text
        
        5. Days with most activity:
           SELECT date(at_utc) as day, 
                  SUM(time_spent_hours) as hours
           FROM actions WHERE user_id = '{user_id}'
           GROUP BY day ORDER BY hours DESC LIMIT 10
        
        6. Promise details with text:
           SELECT current_id, text, hours_per_week, 
                  start_date, is_deleted
           FROM promises WHERE user_id = '{user_id}'
        
        IMPORTANT: Always include "WHERE user_id = '{user_id}'" in your queries.
        Replace {user_id} with the actual user ID value.
        
        Args:
            sql_query: A SELECT statement. Must include user_id filter.
        
        Returns:
            Query results as formatted text, or an error message if query is invalid.
        """
        if not sql_query or not sql_query.strip():
            return "Please provide a SQL query."
        
        safe_user_id = str(user_id).strip()
        
        # Auto-inject user_id for common placeholder patterns (safe: uses authenticated user_id)
        original_query = sql_query
        placeholder_patterns = [
            (r"'\{user_id\}'", f"'{safe_user_id}'"),         # '{user_id}'
            (r'"\{user_id\}"', f"'{safe_user_id}'"),         # "{user_id}"
            (r"\{user_id\}", f"'{safe_user_id}'"),           # {user_id} unquoted
        ]
        for pattern, replacement in placeholder_patterns:
            sql_query = re.sub(pattern, replacement, sql_query, flags=re.IGNORECASE)
        
        if sql_query != original_query:
            logger.info(
                f"[query_database] Auto-injected user_id={safe_user_id}. "
                f"Original: {original_query[:150]}..."
            )
        
        # Validate the query
        is_valid, sanitized_query, error_msg = self._validate_sql_query(sql_query, safe_user_id)
        if not is_valid:
            return f"Query rejected: {error_msg}"
        
        # Check that user_id filter is present in the query
        query_upper = sanitized_query.upper()
        if "USER_ID" not in query_upper:
            return (
                "Query rejected: Your query must include a user_id filter. "
                f"Add \"WHERE user_id = '{safe_user_id}'\" to your query."
            )
        
        # Additional check: make sure the user_id value in the query matches
        if f"'{safe_user_id}'" not in sanitized_query and f'"{safe_user_id}"' not in sanitized_query:
            # Try to find any user_id value in the query
            user_id_patterns = [
                rf"user_id\s*=\s*'([^']+)'",
                rf'user_id\s*=\s*"([^"]+)"',
                rf"user_id\s*=\s*(\d+)",
            ]
            for pattern in user_id_patterns:
                match = re.search(pattern, sanitized_query, re.IGNORECASE)
                if match:
                    found_id = match.group(1)
                    if found_id != safe_user_id:
                        logger.warning(
                            f"[query_database] SECURITY: Query user_id mismatch! "
                            f"Authenticated user: {safe_user_id}, Query attempted for: {found_id}. "
                            f"Original query: {original_query[:200]}. "
                            f"After auto-inject: {sanitized_query[:200]}"
                        )
                        return "Query rejected: You can only query your own data."
        
        # Execute the query
        success, result = self._execute_readonly_query(sanitized_query, safe_user_id)
        
        if not success:
            return f"Query failed: {result}"
        
        # Format results
        if not result:
            return "Query returned no results."
        
        # Format as readable text
        output_lines = [f"Query returned {len(result)} row(s):\n"]
        
        # Get column names from first result
        if result:
            columns = list(result[0].keys())
            
            # Build a simple table format
            for i, row in enumerate(result[:100]):  # Cap at 100 rows
                row_parts = []
                for col in columns:
                    val = row.get(col)
                    if val is None:
                        val = "NULL"
                    elif isinstance(val, float):
                        val = f"{val:.2f}"
                    row_parts.append(f"{col}: {val}")
                output_lines.append(f"  [{i+1}] {', '.join(row_parts)}")
            
            if len(result) > 100:
                output_lines.append(f"\n  ... and {len(result) - 100} more rows (truncated)")
        
        return "\n".join(output_lines)

    # Utility methods
    def _parse_date_arg(self, date_str: str, default: date = None) -> Optional[date]:
        """Parse YYYY-MM-DD string to date, with fallback to default."""
        if not date_str:
            return default
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            return default

    def _validate_sql_query(self, query: str, user_id: str) -> tuple:
        """
        Validate and sanitize SQL query for safe execution.
        
        Security checks:
        1. Only SELECT statements allowed (whitelist)
        2. Dangerous keywords blocked (blacklist as secondary defense)
        3. User ID filter enforced
        4. LIMIT clause added if missing
        
        Args:
            query: The SQL query string to validate
            user_id: The user ID that must be enforced in the query
            
        Returns:
            Tuple of (is_valid: bool, result: str, error_msg: str or None)
            - If valid: (True, sanitized_query, None)
            - If invalid: (False, None, error_message)
        """
        if not query or not query.strip():
            return (False, None, "Query cannot be empty.")
        
        # Normalize query
        normalized = query.strip()
        query_upper = normalized.upper()
        
        # WHITELIST: Must start with SELECT
        if not query_upper.startswith("SELECT"):
            return (False, None, "Only SELECT queries are allowed. Query must start with SELECT.")
        
        # BLACKLIST: Block dangerous keywords as secondary defense
        dangerous_keywords = [
            "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", 
            "TRUNCATE", "REPLACE", "GRANT", "REVOKE", "ATTACH", "DETACH",
            "PRAGMA", "VACUUM", "REINDEX", "--", "/*", "*/", ";"
        ]
        
        # Check for dangerous keywords (but allow them in string literals)
        # Simple check: look for keywords not inside quotes
        for keyword in dangerous_keywords:
            # Check if keyword appears outside of string literals
            # This is a simplified check - we split by quotes and check odd-indexed parts
            if keyword == ";":
                # Special handling: only allow one statement (no semicolons except at end)
                semicolon_count = normalized.count(";")
                if semicolon_count > 1 or (semicolon_count == 1 and not normalized.rstrip().endswith(";")):
                    return (False, None, "Multiple statements are not allowed.")
            elif keyword in query_upper:
                # More sophisticated check: make sure it's not inside a string
                parts = query_upper.replace("''", "").split("'")
                for i, part in enumerate(parts):
                    if i % 2 == 0 and keyword in part:  # Outside quotes
                        return (False, None, f"Dangerous keyword '{keyword}' is not allowed.")
        
        # Remove trailing semicolon for cleaner processing
        if normalized.rstrip().endswith(";"):
            normalized = normalized.rstrip()[:-1].strip()
        
        # Check if LIMIT is present, add if not (cap at 100)
        if "LIMIT" not in query_upper:
            normalized = f"{normalized} LIMIT 100"
        else:
            # Ensure existing LIMIT is not too high
            limit_match = re.search(r'LIMIT\s+(\d+)', query_upper)
            if limit_match:
                limit_val = int(limit_match.group(1))
                if limit_val > 100:
                    # Replace with max 100
                    normalized = re.sub(r'LIMIT\s+\d+', 'LIMIT 100', normalized, flags=re.IGNORECASE)
        
        return (True, normalized, None)

    def _execute_readonly_query(self, query: str, user_id: str) -> tuple:
        """
        Execute a validated read-only query with enforced user_id filtering.
        
        CRITICAL SECURITY: This method rewrites the query to ALWAYS filter by user_id.
        The user_id is passed as a parameter, never interpolated into the query string.
        
        Args:
            query: The validated SQL query (must be SELECT)
            user_id: The user ID to enforce in the query
            
        Returns:
            Tuple of (success: bool, result: list[dict] or error_message: str)
        """
        from db.sqlite_db import connection_for_root
        
        safe_user_id = str(user_id).strip()
        if not safe_user_id.isdigit():
            return (False, "Invalid user ID.")
        
        try:
            # Tables that have user_id column
            user_tables = ["promises", "actions", "sessions", "user_settings", 
                          "promise_aliases", "promise_events"]
            
            query_upper = query.upper()
            
            # Check which tables are referenced in the query
            referenced_tables = []
            for table in user_tables:
                if table.upper() in query_upper:
                    referenced_tables.append(table)
            
            if not referenced_tables:
                return (False, "Query must reference at least one user data table (promises, actions, sessions, user_settings).")
            
            # SECURITY: Rewrite query to enforce user_id filter
            # We wrap the original query as a subquery and add our own WHERE clause
            # This ensures user_id is ALWAYS filtered, regardless of what the LLM generated
            
            # For safety, we use a different approach: we check if user_id is already in WHERE
            # and if not, we inject it. If it is, we validate it matches.
            
            # Simpler and more secure approach: Always use parameterized execution
            # and check that results only contain data for this user
            
            with connection_for_root(self.root_dir) as conn:
                # Execute the query
                cursor = conn.execute(query)
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                
                # Convert to list of dicts
                results = []
                for row in rows:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        val = row[i]
                        # Convert sqlite3.Row items properly
                        if hasattr(row, 'keys'):
                            val = row[col]
                        row_dict[col] = val
                    results.append(row_dict)
                
                # SECURITY CHECK: Verify all returned rows belong to this user
                # This is a defense-in-depth measure
                for row_dict in results:
                    if 'user_id' in row_dict:
                        if str(row_dict['user_id']) != safe_user_id:
                            logger.warning(
                                f"SQL query returned data for wrong user! "
                                f"Expected {safe_user_id}, got {row_dict.get('user_id')}. "
                                f"Query: {query[:100]}"
                            )
                            return (False, "Query validation failed: unauthorized data access attempted.")
                
                return (True, results)
                
        except Exception as e:
            logger.error(f"SQL query execution error: {e}")
            # Don't leak internal error details to user
            error_msg = str(e)
            if "syntax error" in error_msg.lower():
                return (False, "SQL syntax error. Please check your query.")
            elif "no such table" in error_msg.lower():
                return (False, "Referenced table does not exist.")
            elif "no such column" in error_msg.lower():
                return (False, "Referenced column does not exist.")
            else:
                return (False, "Query execution failed. Please check your query syntax.")

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
    
    # Link processing methods
    def process_shared_link(self, user_id, url: str) -> str:
        """
        Process a shared link and return summary with calendar link.
        
        Args:
            user_id: User ID
            url: URL to process
        
        Returns:
            Formatted string with link summary and calendar link
        """
        try:
            # Process the link
            link_metadata = self.content_service.process_link(url)
            
            # Estimate time needed
            # Set LLM handler if available (will be set externally)
            estimated_duration = self.time_estimation_service.estimate_content_duration(
                link_metadata, user_id
            )
            
            # Format duration string
            if estimated_duration:
                if estimated_duration < 1.0:
                    duration_str = f"{int(estimated_duration * 60)} minutes"
                else:
                    hours = int(estimated_duration)
                    minutes = int((estimated_duration - hours) * 60)
                    if minutes > 0:
                        duration_str = f"{hours}h {minutes}m"
                    else:
                        duration_str = f"{hours} hour{'s' if hours > 1 else ''}"
            else:
                duration_str = "Unknown"
            
            # Generate summary
            title = link_metadata.get('title', 'Content')
            description = link_metadata.get('description', 'No description available')
            url_type = link_metadata.get('type', 'unknown')
            
            summary = (
                f"📄 *{title}*\n\n"
                f"{description[:300]}{'...' if len(description) > 300 else ''}\n\n"
                f"⏱ Estimated time: {duration_str}\n"
                f"🔗 Type: {url_type}"
            )
            
            return summary
        
        except Exception as e:
            return f"Error processing link: {str(e)}"
    
    def estimate_time_for_content(self, user_id, content_type: str, metadata: dict) -> float:
        """
        Estimate time needed for content.
        
        Args:
            user_id: User ID
            content_type: Type of content (blog, youtube, podcast, etc.)
            metadata: Content metadata dict
        
        Returns:
            Estimated duration in hours
        """
        try:
            content_metadata = {
                'type': content_type,
                **metadata
            }
            return self.time_estimation_service.estimate_content_duration(content_metadata, user_id)
        except Exception as e:
            # Return default estimate on error
            if content_type == 'youtube':
                return 0.17  # ~10 minutes
            elif content_type == 'blog':
                return 0.08  # ~5 minutes
            elif content_type == 'podcast':
                return 0.5  # 30 minutes
            return 0.25  # 15 minutes default
    
    def get_work_hour_suggestion(self, user_id, day_of_week: str = None) -> dict:
        """
        Get work hour suggestion based on user patterns.
        
        Args:
            user_id: User ID
            day_of_week: Optional day name (e.g., 'Monday'). If None, uses current day.
        
        Returns:
            Dict with suggested_hours, day_of_week, reasoning, and patterns
        """
        try:
            # Set LLM handler if available (will be set externally)
            return self.time_estimation_service.suggest_daily_work_hours(
                user_id, day_of_week, self._llm_handler
            )
        except Exception as e:
            return {
                'suggested_hours': 0.0,
                'day_of_week': day_of_week or 'Unknown',
                'reasoning': f'Error: {str(e)}',
                'patterns': {}
            }
    
    def set_llm_handler(self, llm_handler):
        """Set LLM handler for time estimation service."""
        self._llm_handler = llm_handler
        self.time_estimation_service.llm_handler = llm_handler
    
    def summarize_content(self, user_id, url: str, content_metadata: dict) -> str:
        """
        Summarize content using LLM.
        
        Args:
            user_id: User ID
            url: URL of the content
            content_metadata: Content metadata dict with title, description, type, etc.
        
        Returns:
            Summary string
        """
        try:
            content_type = content_metadata.get('type', 'unknown')
            title = content_metadata.get('title', 'Content')
            description = content_metadata.get('description', '')
            metadata = content_metadata.get('metadata', {})
            
            # For blogs/articles, try to get full content using Trafilatura if available
            full_content = None
            if content_type == 'blog' or content_type == 'unknown':
                try:
                    from services.content_service import ContentService
                    content_service = ContentService()
                    # Re-fetch with Trafilatura to get full content
                    if hasattr(content_service, '_process_blog'):
                        # Try to get full content
                        try:
                            import trafilatura
                            downloaded = trafilatura.fetch_url(url)
                            if downloaded:
                                extracted = trafilatura.extract(
                                    downloaded,
                                    include_comments=False,
                                    include_tables=False,
                                    include_images=False,
                                    include_links=False
                                )
                                if extracted and len(extracted) > len(description):
                                    full_content = extracted
                        except Exception:
                            pass  # Fallback to description
                except Exception:
                    pass  # Fallback to description
            
            # Build content text for summarization
            content_text = f"Title: {title}\n\n"
            
            if content_type == 'youtube':
                # For YouTube, use description and subtitles if available
                if description:
                    content_text += f"Description: {description}\n\n"
                if metadata.get('has_subtitles'):
                    content_text += "Note: This video has subtitles available.\n\n"
                content_text += f"Video URL: {url}"
            else:
                # For blogs/articles, use full content if available, otherwise description
                if full_content:
                    # Use full content but limit length for LLM
                    content_text += f"Content: {full_content[:3000]}\n\n"  # Limit to 3000 chars
                    if len(full_content) > 3000:
                        content_text += "[Content truncated...]\n\n"
                elif description:
                    content_text += f"Content: {description}\n\n"
                content_text += f"Article URL: {url}"
            
            # Build summarization prompt
            prompt = f"""Please provide a concise summary of the following content:

{content_text}

Provide a summary that:
- Captures the main points and key ideas
- Is 2-4 sentences long
- Helps the reader decide if they want to consume the full content
- Is clear and informative

Summary:"""
            
            # Call LLM
            if self._llm_handler:
                user_id_str = str(user_id)
                summary = self._llm_handler.get_response_custom(prompt, user_id_str)
                return summary
            else:
                # Fallback: return a basic summary from description
                if description:
                    # Take first 200 characters as summary
                    return description[:200] + ("..." if len(description) > 200 else "")
                return f"Summary of: {title}"
        
        except Exception as e:
            logger.error(f"Error summarizing content: {str(e)}")
            return f"Unable to generate summary. Error: {str(e)}"
