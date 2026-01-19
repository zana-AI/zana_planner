"""
Service for computing next_run_at_utc and dispatching reminders.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, time, timedelta
import pytz
from zoneinfo import ZoneInfo

from repositories.reminders_repo import RemindersRepository
from repositories.schedules_repo import SchedulesRepository
from repositories.settings_repo import SettingsRepository
from db.postgres_db import utc_now_iso, dt_to_utc_iso, dt_from_utc_iso
from utils.logger import get_logger

logger = get_logger(__name__)


class ReminderDispatchService:
    """Service for computing reminder next_run times and dispatching them."""

    def __init__(self, root_dir: str = None):
        self.root_dir = root_dir
        self.reminders_repo = RemindersRepository(root_dir)
        self.schedules_repo = SchedulesRepository(root_dir)
        self.settings_repo = SettingsRepository(root_dir)

    def _get_user_timezone(self, user_id: int) -> str:
        """Get user's timezone, defaulting to UTC."""
        settings = self.settings_repo.get_settings(user_id)
        if settings and settings.timezone and settings.timezone != "DEFAULT":
            return settings.timezone
        return "UTC"

    def _parse_time(self, time_str: str) -> time:
        """Parse time string (HH:MM:SS or HH:MM) to time object."""
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        second = int(parts[2]) if len(parts) > 2 else 0
        return time(hour, minute, second)

    def _get_timezone(self, tz_str: Optional[str], user_id: int) -> Any:
        """Get timezone object, using user tz if tz_str is None."""
        tz_name = tz_str if tz_str else self._get_user_timezone(user_id)
        try:
            return ZoneInfo(tz_name)
        except Exception:
            try:
                return pytz.timezone(tz_name)
            except Exception:
                return pytz.UTC

    def compute_next_run_at_utc(
        self,
        reminder: Dict[str, Any],
        user_id: int,
        now: Optional[datetime] = None
    ) -> Optional[datetime]:
        """
        Compute next_run_at_utc for a reminder.
        
        For slot_offset: computes next slot time + offset
        For fixed_time: computes next occurrence of weekday + time_local
        """
        if now is None:
            now = datetime.now(pytz.UTC)
        else:
            if now.tzinfo is None:
                now = now.replace(tzinfo=pytz.UTC)
        
        kind = reminder["kind"]
        tz = self._get_timezone(reminder.get("tz"), user_id)
        now_local = now.astimezone(tz)
        
        if kind == "slot_offset":
            # Need slot info
            slot_id = reminder.get("slot_id")
            if not slot_id:
                return None
            
            slot = self.schedules_repo.get_slot(slot_id)
            if not slot or not slot.get("is_active"):
                return None
            
            offset_minutes = reminder.get("offset_minutes", 0)
            weekday = slot["weekday"]
            start_time_str = slot["start_local_time"]
            start_time = self._parse_time(start_time_str) if isinstance(start_time_str, str) else start_time_str
            
            # Find next occurrence of this weekday + time
            days_ahead = (weekday - now_local.weekday()) % 7
            if days_ahead == 0:
                # Today - check if time has passed
                target_time = datetime.combine(now_local.date(), start_time).replace(tzinfo=tz)
                if target_time <= now_local:
                    days_ahead = 7  # Next week
            
            next_slot = datetime.combine(
                (now_local + timedelta(days=days_ahead)).date(),
                start_time
            ).replace(tzinfo=tz)
            
            # Apply offset (subtract for "before" reminders)
            next_run = next_slot - timedelta(minutes=offset_minutes)
            
            # Convert to UTC
            return next_run.astimezone(pytz.UTC).replace(tzinfo=None)
        
        elif kind == "fixed_time":
            weekday = reminder.get("weekday")
            time_local_str = reminder.get("time_local")
            if weekday is None or not time_local_str:
                return None
            
            time_local = self._parse_time(time_local_str) if isinstance(time_local_str, str) else time_local_str
            
            # Find next occurrence of this weekday + time
            days_ahead = (weekday - now_local.weekday()) % 7
            if days_ahead == 0:
                # Today - check if time has passed
                target_time = datetime.combine(now_local.date(), time_local).replace(tzinfo=tz)
                if target_time <= now_local:
                    days_ahead = 7  # Next week
            
            next_run = datetime.combine(
                (now_local + timedelta(days=days_ahead)).date(),
                time_local
            ).replace(tzinfo=tz)
            
            # Convert to UTC
            return next_run.astimezone(pytz.UTC).replace(tzinfo=None)
        
        return None

    def update_next_run_times(self, user_id: int, promise_uuid: str) -> None:
        """Update next_run_at_utc for all reminders of a promise."""
        reminders = self.reminders_repo.list_reminders(promise_uuid, enabled=True)
        now = datetime.now(pytz.UTC)
        
        for reminder in reminders:
            next_run = self.compute_next_run_at_utc(reminder, user_id, now)
            if next_run:
                self.reminders_repo.update_reminder(reminder["reminder_id"], {
                    "next_run_at_utc": dt_to_utc_iso(next_run)
                })

    def dispatch_due_reminders(
        self,
        callback: callable,
        limit: int = 100
    ) -> int:
        """
        Dispatch due reminders by calling callback for each.
        
        Args:
            callback: Function(user_id, promise_uuid, reminder) to call for each due reminder
            limit: Max reminders to process in one batch
        
        Returns:
            Number of reminders dispatched
        """
        due_reminders = self.reminders_repo.get_due_reminders(limit)
        dispatched = 0
        
        for reminder in due_reminders:
            try:
                # Get user_id from promise_uuid
                from db.postgres_db import get_db_session
                from sqlalchemy import text
                
                with get_db_session() as session:
                    user_row = session.execute(
                        text("SELECT user_id FROM promises WHERE promise_uuid = :promise_uuid LIMIT 1"),
                        {"promise_uuid": reminder["promise_uuid"]}
                    ).fetchone()
                    
                    if not user_row:
                        logger.warning(f"Could not find user for promise {reminder['promise_uuid']}")
                        continue
                    
                    user_id = int(user_row[0])
                
                # Call callback
                callback(user_id, reminder["promise_uuid"], reminder)
                
                # Update last_sent_at_utc and compute next_run_at_utc
                now = datetime.now(pytz.UTC)
                next_run = self.compute_next_run_at_utc(reminder, user_id, now)
                
                update_data = {
                    "last_sent_at_utc": dt_to_utc_iso(now)
                }
                if next_run:
                    update_data["next_run_at_utc"] = dt_to_utc_iso(next_run)
                
                self.reminders_repo.update_reminder(reminder["reminder_id"], update_data)
                dispatched += 1
                
            except Exception as e:
                logger.exception(f"Error dispatching reminder {reminder.get('reminder_id')}: {e}")
                continue
        
        return dispatched
