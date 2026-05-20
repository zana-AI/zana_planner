"""
Adapter to provide compatibility with the existing PlannerAPI interface
while using the new repository and service layers underneath.
"""
import asyncio
import json
import re
from datetime import datetime, date
from typing import List, Dict, Optional, Any, Union
from zoneinfo import ZoneInfo

from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from repositories.settings_repo import SettingsRepository
from repositories.sessions_repo import SessionsRepository
from repositories.nightly_state_repo import NightlyStateRepository
from repositories.templates_repo import TemplatesRepository
from repositories.instances_repo import InstancesRepository
from repositories.distractions_repo import DistractionsRepository
from repositories.profile_repo import ProfileRepository
from repositories.follows_repo import FollowsRepository
from repositories.plan_sessions_repo import PlanSessionsRepository
from repositories.reminders_repo import RemindersRepository
from services.reminder_dispatch import ReminderDispatchService
from db.postgres_db import get_db_session, resolve_promise_uuid
from services.reports import ReportsService
from services.template_unlocks import TemplateUnlocksService
from services.ranking import RankingService
from services.reminders import RemindersService
from services.sessions import SessionsService
from services.content_service import ContentService
from services.time_estimation_service import TimeEstimationService
from services.settings_service import SettingsService
from services.profile_service import ProfileService
from services.schema_service import SchemaService
from services.query_service import QueryService
from services.social_service import SocialService
from services.content_management_service import ContentManagementService
from models.models import Promise, Action, UserSettings
from models.enums import ActionType
from utils.logger import get_logger

logger = get_logger(__name__)


_PROMISE_ID_PATTERN = re.compile(r"\b([PT]\d{1,5})\b")


def _extract_first_promise_id(search_result: str) -> Optional[str]:
    """Pull the first 'P12'/'T03'-style id out of a search_promises text result."""
    if not search_result:
        return None
    m = _PROMISE_ID_PATTERN.search(str(search_result))
    return m.group(1) if m else None


def _short_item_label(item: Dict[str, Any], default: str, text_key: str = "promise_query") -> str:
    """Render a brief label for a batch item, used in success/failure summaries."""
    label = str(item.get(text_key) or item.get("promise") or item.get("text") or default).strip()
    return label[:40] if label else default


def _format_batch_summary(action_noun: str, ok: List[str], failed: List[str], total: int) -> str:
    """Return a compact human-readable batch result string."""
    parts = [f"✅ {len(ok)}/{total} {action_noun}"]
    if ok:
        parts.append(f" ({', '.join(ok)})")
    if failed:
        parts.append(f". Failed: {'; '.join(failed)}")
    return "".join(parts) + "."


class PlannerAPIAdapter:
    """Adapter that provides the old PlannerAPI interface using new services."""
    
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        
        # Initialize repositories
        self.promises_repo = PromisesRepository()
        self.actions_repo = ActionsRepository()
        self.settings_repo = SettingsRepository()
        self.sessions_repo = SessionsRepository()
        self.nightly_state_repo = NightlyStateRepository(root_dir)
        
        # Initialize services
        self.settings_service = SettingsService(self.settings_repo)
        self.reports_service = ReportsService(self.promises_repo, self.actions_repo)
        self.ranking_service = RankingService(self.promises_repo, self.actions_repo, self.settings_repo)
        self.reminders_service = RemindersService(self.ranking_service, self.settings_repo)
        self.sessions_service = SessionsService(self.sessions_repo, self.actions_repo)
        self.content_service = ContentService()
        self.time_estimation_service = TimeEstimationService(self.actions_repo)
        self.content_management_service = ContentManagementService(
            self.content_service, self.time_estimation_service
        )
        
        # Template-related repos and services
        self.templates_repo = TemplatesRepository()
        self.instances_repo = InstancesRepository()
        self.distractions_repo = DistractionsRepository()
        self.unlocks_service = TemplateUnlocksService()
        
        # Profile-related repos and services
        self.profile_repo = ProfileRepository()
        self.profile_service = ProfileService(self.profile_repo)
        
        # Social/community repos and services
        self.follows_repo = FollowsRepository()
        self.social_service = SocialService(self.follows_repo, self.settings_repo)
        
        # Schema and query services
        self.schema_service = SchemaService()
        self.query_service = QueryService()

        # Plan sessions
        self.plan_sessions_repo = PlanSessionsRepository()

        # Reminders (recurring fire-at-time pings tied to a promise)
        self.reminders_repo = RemindersRepository()
        self.reminder_dispatch = ReminderDispatchService()

    # Promise methods
    def add_promise(
        self,
        user_id,
        promise_text: str,
        num_hours_promised_per_week: float,
        recurring: bool = True,
        start_date: Optional[Union[date, datetime, str]] = None,
        end_date: Optional[Union[date, datetime, str]] = None,
    ):
        """Create an ongoing tracked goal with a weekly hour budget. Use for 'I want to read 5h/week'."""
        try:
            if user_id is None:
                raise ValueError("user_id is required and cannot be None")
            if not promise_text or not isinstance(promise_text, str):
                raise ValueError("Promise text must be a non-empty string")
            if not isinstance(num_hours_promised_per_week, (int, float)) or num_hours_promised_per_week < 0:
                raise ValueError("Hours promised must be a non-negative number (0.0 for check-based promises, > 0.0 for time-based promises)")

            # Generate promise ID
            promise_id = self._generate_promise_id(user_id, 'P' if recurring else 'T')

            start_date = self._coerce_date_like(start_date, "start_date")
            end_date = self._coerce_date_like(end_date, "end_date")
            
            if not start_date:
                start_date = datetime.now().date()
            if not end_date:
                end_date = datetime(datetime.now().year, 12, 31).date()
            if start_date > end_date:
                raise ValueError("start_date must be on or before end_date")

            promise = Promise(
                user_id=str(user_id),
                id=promise_id,
                text=promise_text.replace(" ", "_"),
                hours_per_week=num_hours_promised_per_week,
                recurring=recurring,
                start_date=start_date,
                end_date=end_date
            )

            self.promises_repo.upsert_promise(user_id, promise)
            return f"#{promise_id} Promise '{promise_text}' added successfully."

        except (ValueError, FileNotFoundError) as e:
            raise RuntimeError(f"Failed to add promise: {str(e)}")

    def create_reminder(
        self,
        user_id,
        text: str,
        remind_at: str,
    ) -> str:
        """Create a one-off reminder for a future date.

        Use when the user asks to be reminded, or states a one-off task/deadline
        with a future time. Examples:
            'remind me to call mom tonight'
            'I need to send Kamran the work permits by tomorrow evening'
            'یادم بنداز فردا ساعت ۹ به دکتر زنگ بزنم'

        Never use for ongoing goals the user wants to track time against
        (use add_promise) or for past completed activity (use log_completed_activity).
        This tool does NOT need an existing promise_id.

        Storage note: backed by a one-time promise (no hour budget). The reminder
        surfaces on the user's dashboard and in the nightly digest on its due date;
        minute-precise time-of-day pings are not yet wired.

        Args:
            text: What to remind the user about (short, user-facing)
            remind_at: ISO datetime for the reminder; resolve with resolve_datetime() first
        """
        try:
            remind_dt = self._coerce_datetime_like(remind_at, "remind_at")
        except ValueError as e:
            return str(e)
        if remind_dt is None:
            return "remind_at is required (call resolve_datetime first)."

        try:
            return self.add_promise(
                user_id=user_id,
                promise_text=text,
                num_hours_promised_per_week=0.0,
                recurring=True,
                end_date=remind_dt.date(),
            )
        except Exception as e:
            logger.error(f"create_reminder error: {e}")
            return f"Error creating reminder: {str(e)}"

    def create_recurring_reminder(
        self,
        user_id,
        promise_id: str,
        weekday: int,
        time_local: str,
    ) -> str:
        """Create a weekly recurring reminder ping for a promise.

        Use when the user wants to be pinged on a specific weekday + time every
        week ('remind me every Tuesday at 9am about the gym', 'ping me Sundays
        at 8pm to review the week'). Requires a promise_id.

        Never use for one-off reminders (use create_reminder) or to log time
        (use log_completed_activity).

        Args:
            promise_id: Promise ID this reminder is tied to (e.g. 'P10')
            weekday: 0=Monday ... 6=Sunday (Python convention)
            time_local: 24-hour local time as 'HH:MM' (e.g. '09:00', '20:30')
        """
        try:
            weekday = int(weekday)
            if weekday < 0 or weekday > 6:
                return "weekday must be 0 (Monday) through 6 (Sunday)."
        except (TypeError, ValueError):
            return "weekday must be an integer 0-6 (Monday=0)."

        time_str = str(time_local or "").strip()
        if not time_str or ":" not in time_str:
            return "time_local must be 'HH:MM' (e.g. '09:00')."
        if len(time_str.split(":")) == 2:
            time_str = f"{time_str}:00"

        try:
            with get_db_session() as session:
                p_uuid = resolve_promise_uuid(session, str(user_id), promise_id)
            if not p_uuid:
                return f"Promise '{promise_id}' not found."

            settings = self.settings_repo.get_settings(int(user_id))
            tz_raw = getattr(settings, "timezone", None)
            user_tz = tz_raw if tz_raw and tz_raw != "DEFAULT" else "UTC"

            reminder_id = self.reminders_repo.create_reminder({
                "promise_uuid": p_uuid,
                "kind": "fixed_time",
                "weekday": weekday,
                "time_local": time_str,
                "tz": user_tz,
                "enabled": True,
            })
            self.reminder_dispatch.update_next_run_times(int(user_id), p_uuid)

            day_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][weekday]
            return (
                f"✅ Recurring reminder set for {promise_id}: every "
                f"{day_name} at {time_str[:5]} ({user_tz}). id={reminder_id}"
            )
        except Exception as e:
            logger.error(f"create_recurring_reminder error: {e}")
            return f"Error creating recurring reminder: {str(e)}"

    def cancel_reminder(self, user_id, reminder_id: str) -> str:
        """Cancel (disable) a recurring reminder by its reminder_id.

        Use when the user wants to stop being pinged about something
        ('stop reminding me about gym', 'cancel that Tuesday reminder').
        Get reminder_id from list_reminders or the original create_recurring_reminder
        response. Does NOT delete past one-off reminders created via create_reminder
        (those are one-time promises; use delete_promise instead).

        Args:
            reminder_id: UUID of the reminder to disable
        """
        try:
            ok = self.reminders_repo.update_reminder(
                str(reminder_id), {"enabled": 0}
            )
            if not ok:
                return f"Reminder '{reminder_id}' not found."
            return f"✅ Reminder {reminder_id} cancelled."
        except Exception as e:
            logger.error(f"cancel_reminder error: {e}")
            return f"Error cancelling reminder: {str(e)}"

    def schedule_sessions(self, user_id, items: List[Dict[str, Any]]) -> str:
        """Schedule MULTIPLE future sessions in ONE call. Use when the user lists 2+ activities to plan.

        Each item: {promise_query: str, when: str, duration_min: int, title?: str}.
        Internally resolves `when` via resolve_datetime, finds promise_id via search_promises,
        then calls schedule_session. Items that fail (no matching promise / unparseable time)
        are reported but don't abort the rest.

        Use schedule_session (singular) for a single session.

        Args:
            items: List of session specs.
        """
        if not isinstance(items, list) or not items:
            return "items must be a non-empty list."
        if len(items) == 1:
            it = items[0] or {}
            return self._schedule_one_session(user_id, it)

        ok, failed = [], []
        for idx, it in enumerate(items):
            it = it or {}
            try:
                msg = self._schedule_one_session(user_id, it)
                if str(msg).lstrip().startswith(("✅", "Session", "#")):
                    ok.append(_short_item_label(it, "session"))
                else:
                    failed.append(f"{_short_item_label(it, 'session')} ({msg})")
            except Exception as e:
                logger.error(f"schedule_sessions item {idx} error: {e}")
                failed.append(f"{_short_item_label(it, 'session')} ({e})")

        return _format_batch_summary("sessions scheduled", ok, failed, total=len(items))

    def _schedule_one_session(self, user_id, item: Dict[str, Any]) -> str:
        promise_query = item.get("promise_query") or item.get("promise") or ""
        when = item.get("when") or item.get("planned_start") or ""
        duration_min = item.get("duration_min") or item.get("planned_duration_min")
        title = item.get("title")

        if not promise_query:
            return "no promise_query provided."
        if not when:
            return "no 'when' provided."

        promise_id = item.get("promise_id") or _extract_first_promise_id(
            self.search_promises(user_id, str(promise_query))
        )
        if not promise_id:
            return f"no promise matched '{promise_query}'."

        resolved_when = item.get("planned_start") or self.resolve_datetime(user_id, str(when))
        if resolved_when.lower().startswith(("could not parse", "error")):
            return resolved_when

        return self.schedule_session(
            user_id=user_id,
            promise_id=promise_id,
            title=title,
            planned_start=resolved_when,
            planned_duration_min=duration_min,
        )

    def log_completed_activities(self, user_id, items: List[Dict[str, Any]]) -> str:
        """Log MULTIPLE completed activities in ONE call. Use when the user reports 2+ done things.

        Each item: {promise_query: str, time_spent: float, happened_at?: str, notes?: str}.
        Past-tense only — never for future plans (use schedule_sessions) or reminders.
        Use log_completed_activity (singular) for a single entry.

        Args:
            items: List of activity logs.
        """
        if not isinstance(items, list) or not items:
            return "items must be a non-empty list."
        if len(items) == 1:
            return self._log_one_activity(user_id, items[0] or {})

        ok, failed = [], []
        for idx, it in enumerate(items):
            it = it or {}
            try:
                msg = self._log_one_activity(user_id, it)
                if "logged" in str(msg).lower():
                    ok.append(_short_item_label(it, "activity"))
                else:
                    failed.append(f"{_short_item_label(it, 'activity')} ({msg})")
            except Exception as e:
                logger.error(f"log_completed_activities item {idx} error: {e}")
                failed.append(f"{_short_item_label(it, 'activity')} ({e})")

        return _format_batch_summary("activities logged", ok, failed, total=len(items))

    def _log_one_activity(self, user_id, item: Dict[str, Any]) -> str:
        promise_query = item.get("promise_query") or item.get("promise") or ""
        time_spent = item.get("time_spent")
        happened_at = item.get("happened_at") or item.get("action_datetime")
        notes = item.get("notes")

        if time_spent is None:
            return "no time_spent provided."

        promise_id = item.get("promise_id") or _extract_first_promise_id(
            self.search_promises(user_id, str(promise_query))
        )
        if not promise_id:
            return f"no promise matched '{promise_query}'."

        resolved_when = None
        if happened_at:
            resolved_when = self.resolve_datetime(user_id, str(happened_at))
            if resolved_when.lower().startswith(("could not parse", "error")):
                return resolved_when

        return self.log_completed_activity(
            user_id=user_id,
            promise_id=promise_id,
            time_spent=time_spent,
            action_datetime=resolved_when,
            notes=notes,
        )

    def create_reminders(self, user_id, items: List[Dict[str, Any]]) -> str:
        """Create MULTIPLE one-off reminders in ONE call. Use when the user lists 2+ things to remember.

        Each item: {text: str, remind_at: str}.
        Use create_reminder (singular) for a single reminder.

        Args:
            items: List of reminder specs.
        """
        if not isinstance(items, list) or not items:
            return "items must be a non-empty list."
        if len(items) == 1:
            return self._create_one_reminder(user_id, items[0] or {})

        ok, failed = [], []
        for idx, it in enumerate(items):
            it = it or {}
            try:
                msg = self._create_one_reminder(user_id, it)
                if "added successfully" in str(msg).lower() or str(msg).startswith("#"):
                    ok.append(_short_item_label(it, "reminder", text_key="text"))
                else:
                    failed.append(f"{_short_item_label(it, 'reminder', text_key='text')} ({msg})")
            except Exception as e:
                logger.error(f"create_reminders item {idx} error: {e}")
                failed.append(f"{_short_item_label(it, 'reminder', text_key='text')} ({e})")

        return _format_batch_summary("reminders set", ok, failed, total=len(items))

    def _create_one_reminder(self, user_id, item: Dict[str, Any]) -> str:
        text = item.get("text") or ""
        remind_at = item.get("remind_at") or item.get("when") or ""
        if not text:
            return "no text provided."
        if not remind_at:
            return "no remind_at provided."

        resolved = remind_at
        if not str(remind_at).startswith(("20", "19")):
            resolved = self.resolve_datetime(user_id, str(remind_at))
            if resolved.lower().startswith(("could not parse", "error")):
                return resolved
        return self.create_reminder(user_id=user_id, text=text, remind_at=resolved)

    def mark_session_done(self, user_id, session_id: int) -> str:
        """Mark a scheduled session as completed.

        Use when the user reports finishing a previously-scheduled session
        ('I did the gym session', 'finished today's study block'). This will
        also auto-log time on the linked promise if the session had a
        planned_duration_min. Get session_id from get_upcoming_sessions or
        get_plan_sessions.

        Args:
            session_id: Numeric session ID
        """
        return self.update_plan_session_status(user_id, session_id, "done")

    def mark_session_skipped(self, user_id, session_id: int) -> str:
        """Mark a scheduled session as skipped (no time logged).

        Use when the user couldn't or chose not to do a planned session
        ('skipped this morning's run', 'didn't make it to the study block').
        Get session_id from get_upcoming_sessions or get_plan_sessions.

        Args:
            session_id: Numeric session ID
        """
        return self.update_plan_session_status(user_id, session_id, "skipped")

    def set_language(self, user_id, language: str) -> str:
        """Set the user's preferred reply language.

        Use when the user clearly asks to switch language ('speak Persian',
        'reply in French', 'switch to English'). Pass a 2-letter code:
        'en', 'fa', 'fr', 'ru', 'ar'. Never call on ambiguous complaints —
        only when the desired language is unambiguous.

        Args:
            language: 2-letter language code (e.g. 'en', 'fa', 'fr')
        """
        lang = str(language or "").strip().lower()
        if lang not in {"en", "fa", "fr", "ru", "ar", "es", "de"}:
            return f"Unsupported language code '{language}'. Use 'en', 'fa', 'fr', 'ru', 'ar'."
        return self.update_setting(user_id, "language", lang)

    def set_timezone(self, user_id, timezone: str) -> str:
        """Set the user's timezone (affects all date/time interpretation).

        Use when the user states their timezone ('I'm in Tehran', 'set my tz
        to Europe/Paris', 'I'm GMT+1'). Pass an IANA tz name like
        'Asia/Tehran', 'Europe/Paris', 'America/New_York', 'UTC'.

        Args:
            timezone: IANA timezone name (e.g. 'Asia/Tehran', 'UTC')
        """
        tz = str(timezone or "").strip()
        if not tz:
            return "timezone is required (e.g. 'Asia/Tehran', 'UTC')."
        try:
            ZoneInfo(tz)
        except Exception:
            return f"Unknown timezone '{tz}'. Use an IANA name like 'Asia/Tehran' or 'UTC'."
        return self.update_setting(user_id, "timezone", tz)

    def no_op(self, user_id):
        """No-op method for testing purposes."""
        return None

    def get_promise(self, user_id: int, promise_id: str) -> Optional[Promise]:
        """Get a specific promise by ID."""
        return self.promises_repo.get_promise(user_id, promise_id)

    def get_promises(self, user_id) -> List[Dict]:
        """List the user's promises (id, text, weekly hours, dates). Use to look up promise_ids."""
        promises = self.promises_repo.list_promises(user_id)
        return [self._promise_to_dict(p) for p in promises]
    
    def count_promises(self, user_id) -> int:
        """Get total number of promises for a user."""
        return len(self.promises_repo.list_promises(user_id))

    def delete_promise(self, user_id, promise_id: str):
        """Delete a promise by id. Always require user confirmation first."""
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
    ) -> str:
        """Update an existing promise's text, hours/week, recurrence, or dates (only sets fields you pass).

        Args:
            promise_id: Promise identifier (case-insensitive).
            promise_text: New description/title for the promise.
            hours_per_week: New target hours per week.
            recurring: Whether this promise is recurring.
            start_date: Optional new start date.
            end_date: Optional new end date.
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

        self.promises_repo.upsert_promise(user_id, promise)
        return f"Promise #{promise.id} updated successfully."

    # Action methods
    def log_completed_activity(
        self,
        user_id,
        promise_id: str,
        time_spent: float,
        action_datetime: Optional[Union[datetime, str]] = None,
        notes: Optional[str] = None,
    ) -> str:
        """Log time spent on a promise for an activity the user has ALREADY completed.

        Use ONLY when the user reports something already done in the past
        (e.g. "I did 2 hours of reading", "just finished a 30-min run").
        Never use for future plans, reminders, intentions, deadlines, or scheduled work.
        For future work tied to a promise use schedule_session; for one-off future
        pings use create_reminder.

        Args:
            promise_id: Promise ID (e.g., 'P10')
            time_spent: Hours already spent on the activity
            action_datetime: When the activity happened (defaults to now)
            notes: Optional notes/description for this entry
        """
        # Validate promise exists
        if not self.promises_repo.get_promise(user_id, promise_id):
            return f"Promise with ID '{promise_id}' not found."

        try:
            time_spent = float(time_spent)
        except (TypeError, ValueError):
            return "Time spent must be a positive number."

        if time_spent <= 0:
            return "Time spent must be a positive number."

        try:
            action_datetime = self._coerce_datetime_like(action_datetime, "action_datetime")
        except ValueError as e:
            return str(e)

        if action_datetime is None:
            action_datetime = datetime.now()

        action = Action(
            user_id=user_id,
            promise_id=promise_id,
            action=ActionType.LOG_TIME.value,
            time_spent=time_spent,
            at=action_datetime,
            notes=notes if notes and notes.strip() else None
        )

        self.actions_repo.append_action(action)
        return f"Action logged for promise ID '{promise_id}'."

    # Back-compat alias for internal Python callers; not exposed to the LLM
    # (see EXCLUDED_TOOLS in llm_handler._build_tools).
    add_action = log_completed_activity

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
        """Get the user's weekly progress report (hours logged vs promised per goal)."""
        if not reference_time:
            reference_time = datetime.now()
        
        summary = self.reports_service.get_weekly_summary(user_id, reference_time)
        return self.reports_service.format_weekly_report(summary)

    def get_weekly_visualization(self, user_id, reference_time: Optional[datetime] = None) -> str:
        """Generate weekly visualization image for a user."""
        if not reference_time:
            reference_time = datetime.now()
        elif isinstance(reference_time, str):
            # Try to parse ISO format or relative descriptions
            try:
                reference_time = datetime.fromisoformat(reference_time.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                # If parsing fails, use current time
                reference_time = datetime.now()
        
        # Return special marker that handler will detect
        timestamp_str = reference_time.isoformat()
        return f"[WEEKLY_VIZ:{timestamp_str}]"

    def open_mini_app(self, user_id, path: str = "/dashboard", context: Optional[str] = None) -> str:
        """Open the mini app for the user."""
        from urllib.parse import quote
        encoded_path = quote(path, safe='/:?=&')
        encoded_context = quote(context or "", safe='')
        return f"[MINI_APP:{encoded_path}:{encoded_context}]"

    def get_promise_report(self, user_id, promise_id: str) -> str:
        """Get promise report."""
        summary = self.reports_service.get_promise_summary(user_id, promise_id, datetime.now())
        if not summary:
            return f"Promise with ID '{promise_id}' not found."
        
        return self.reports_service.format_promise_report(summary)

    def get_promise_streak(self, user_id, promise_id: str) -> int:
        """Get promise streak."""
        summary = self.reports_service.get_promise_summary(user_id, promise_id, datetime.now())
        return summary.get('streak', 0) if summary else 0

    # Settings methods
    def get_settings(self, user_id) -> Dict[str, Any]:
        """Get user settings as a dict (timezone, nightly time, language, voice mode).
        
        Timezone returns UTC if not set or is DEFAULT placeholder.
        """
        settings = self.settings_repo.get_settings(int(user_id))
        tz = settings.timezone if settings.timezone and settings.timezone != "DEFAULT" else "UTC"
        return {
            "timezone": tz,
            "nightly_hh": settings.nightly_hh,
            "nightly_mm": settings.nightly_mm,
            "language": settings.language,
            "voice_mode": settings.voice_mode,
        }

    def get_setting(self, user_id, setting_key: str):
        """Get a single user setting value by key (timezone, nightly_hh, nightly_mm, language, voice_mode).
        
        Timezone returns UTC if not set or is DEFAULT placeholder.
        """
        settings = self.settings_repo.get_settings(int(user_id))
        key = (setting_key or "").strip().lower()
        if key == "timezone":
            tz = settings.timezone
            return tz if tz and tz != "DEFAULT" else "UTC"
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
        """Update a low-level user setting by key/value. Prefer set_language or set_timezone."""
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
            tz = self.settings_repo.get_settings(int(user_id)).timezone
            tzname = tz if tz and tz != "DEFAULT" else "UTC"
            today_iso = datetime.now(ZoneInfo(tzname)).strftime("%Y-%m-%d")
        except Exception:
            today_iso = datetime.now().strftime("%Y-%m-%d")
        return self.count_actions_on_date(user_id, today_iso)

    # Query and statistics methods
    def search_promises(self, user_id, query: str) -> str:
        """Find a user's promise_id by free-text query. Use when promise_id is unknown."""
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

    def get_promise_hours_total(self, user_id, promise_id: str, 
                              since_date: str = None, until_date: str = None) -> str:
        """Get total hours logged for a promise, optionally within a date range."""
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

    def get_all_hours_total(self, user_id, since_date: str = None, until_date: str = None) -> str:
        """Get total hours logged across all promises, optionally within a date range."""
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

    def list_actions_filtered(self, user_id, promise_id: str = None,
                             since_date: str = None, until_date: str = None) -> str:
        """Get list of actions with optional filtering by promise and date range."""
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


    # On-demand help tools
    def get_tool_help(self, user_id, tool_name: str) -> str:
        """
        Get detailed documentation for a specific tool.
        
        Use this when you need full documentation beyond the short description
        available in the system message.
        
        Args:
            tool_name: Name of the tool (e.g., 'query_database', 'add_action')
        
        Returns:
            Full tool documentation as a formatted string.
        """
        # Get the method from this adapter
        if not hasattr(self, tool_name):
            available = [m for m in dir(self) if not m.startswith('_') and callable(getattr(self, m))]
            return f"Tool '{tool_name}' not found. Available tools: {', '.join(available)}"
        
        method = getattr(self, tool_name)
        if not callable(method):
            return f"'{tool_name}' is not a callable tool."
        
        doc = method.__doc__ or "No documentation available for this tool."
        return doc.strip()
    
    def get_db_schema(self, user_id) -> str:
        """Get database schema and example queries for query_database tool."""
        return self.schema_service.get_schema_documentation()

    def query_database(self, user_id, sql_query: str) -> str:
        """Execute a read-only SQL query against your data for complex analytics."""
        if not sql_query or not sql_query.strip():
            return "Please provide a SQL query."
        
        success, results, error_msg = self.query_service.validate_and_execute_query(
            sql_query, str(user_id), auto_inject_user_id=True
        )
        
        if not success:
            return error_msg or "Query failed."
        
        return self.query_service.format_query_results(results or [])

    # Utility methods
    def _coerce_date_like(self, raw_value: Optional[Union[date, datetime, str]], field_name: str) -> Optional[date]:
        """Normalize date-like values into a date object."""
        if raw_value is None:
            return None
        if isinstance(raw_value, datetime):
            return raw_value.date()
        if isinstance(raw_value, date):
            return raw_value
        if isinstance(raw_value, str):
            text = raw_value.strip()
            if not text:
                return None
            normalized = text.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(normalized).date()
            except ValueError:
                try:
                    return date.fromisoformat(text)
                except ValueError:
                    # As a last resort, try more flexible parsing for common non-ISO formats.
                    # This mirrors the datetime parsing behavior in _coerce_datetime_like and
                    # makes the adapter more tolerant of LLM-generated date strings.
                    try:
                        from dateutil.parser import parse as parse_date
                        return parse_date(text).date()
                    except Exception as e:
                        raise ValueError(f"{field_name} must be an ISO date or datetime string") from e
        raise ValueError(f"{field_name} must be a date, datetime, or ISO date string")

    def _coerce_datetime_like(
        self,
        raw_value: Optional[Union[datetime, str]],
        field_name: str,
    ) -> Optional[datetime]:
        """Normalize datetime-like values into a datetime object."""
        if raw_value is None:
            return None
        if isinstance(raw_value, datetime):
            return raw_value
        if isinstance(raw_value, str):
            text = raw_value.strip()
            if not text:
                return None
            normalized = text.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(normalized)
            except ValueError:
                try:
                    from dateutil.parser import parse as parse_datetime
                    return parse_datetime(text)
                except Exception as e:
                    raise ValueError(f"{field_name} must be an ISO datetime string") from e
        raise ValueError(f"{field_name} must be a datetime or ISO datetime string")

    def _parse_date_arg(self, date_str: str, default: date = None) -> Optional[date]:
        """Parse YYYY-MM-DD string to date, with fallback to default."""
        if not date_str:
            return default
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            return default


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
            'end_date': promise.end_date.isoformat() if promise.end_date else '',
        }

    
    # Content management methods
    def process_shared_link(self, user_id, url: str) -> str:
        """Process a shared link and return formatted summary with time estimate."""
        return self.content_management_service.process_shared_link(int(user_id), url)
    
    def estimate_time_for_content(self, user_id, content_type: str, metadata: dict) -> float:
        """Estimate time needed for content."""
        return self.content_management_service.estimate_time_for_content(
            int(user_id), content_type, metadata
        )
    
    def get_work_hour_suggestion(self, user_id, day_of_week: str = None) -> dict:
        """Get work hour suggestion based on user patterns."""
        return self.content_management_service.get_work_hour_suggestion(
            int(user_id), day_of_week
        )
    
    def set_llm_handler(self, llm_handler):
        """Set LLM handler for content management and time estimation services."""
        self._llm_handler = llm_handler
        self.time_estimation_service.llm_handler = llm_handler
        self.content_management_service.set_llm_handler(llm_handler)
    
    def summarize_content(self, user_id, url: str, content_metadata: dict) -> str:
        """Summarize content using LLM."""
        return self.content_management_service.summarize_content(
            int(user_id), url, content_metadata
        )
    
    # Template methods
    def list_templates(self, user_id, category: Optional[str] = None) -> str:
        """List available promise templates, optionally filtered by category."""
        try:
            templates = self.templates_repo.list_templates(category=category, is_active=True)
            templates_with_status = self.unlocks_service.annotate_templates_with_unlock_status(user_id, templates)
            
            if not templates_with_status:
                return "No templates found."
            
            result = []
            for t in templates_with_status:
                status = "🔓 Unlocked" if t.get('unlocked', False) else "🔒 Locked"
                metric = f"{t.get('target_value', 0)}{'x' if t.get('metric_type') == 'count' else 'h'}"
                level_part = f" ({t['level']})" if t.get('level') else ""
                result.append(f"{status} - {t['title']}{level_part} - {metric} - {t.get('category', '')}")
            
            return "\n".join(result)
        except Exception as e:
            logger.error(f"Error listing templates: {str(e)}")
            return f"Error listing templates: {str(e)}"
    
    def get_template(self, user_id, template_id: str) -> str:
        """Get details for a specific template."""
        try:
            template = self.templates_repo.get_template(template_id)
            if not template:
                return f"Template '{template_id}' not found."
            
            unlock_status = self.unlocks_service.get_unlock_status(user_id, template_id)
            prerequisites = self.templates_repo.get_prerequisites(template_id)
            
            result = [f"Template: {template['title']}"]
            result.append(f"Category: {template.get('category', '')}")
            if template.get('level'):
                result.append(f"Level: {template['level']}")
            result.append(f"Status: {'🔓 Unlocked' if unlock_status['unlocked'] else '🔒 Locked'}")
            if not unlock_status['unlocked']:
                result.append(f"Lock reason: {unlock_status['lock_reason']}")
            desc = template.get('why') or template.get('description') or ''
            if desc:
                result.append(f"Description: {desc}")
            if template.get('done'):
                result.append(f"Done means: {template['done']}")
            if template.get('effort'):
                result.append(f"Effort: {template['effort']}")
            target_dir = template.get('target_direction', 'at_least')
            result.append(f"Target: {template.get('target_value', 0)}{'x' if template.get('metric_type') == 'count' else 'h'} ({target_dir})")
            
            if prerequisites:
                result.append("Prerequisites:")
                for p in prerequisites:
                    if p['kind'] == 'completed_template':
                        result.append(f"  - Complete template: {p['required_template_id']}")
                    elif p['kind'] == 'success_rate':
                        result.append(f"  - Achieve {p['min_success_rate']*100}% success on {p['required_template_id']} over {p['window_weeks']} weeks")
            
            return "\n".join(result)
        except Exception as e:
            logger.error(f"Error getting template: {str(e)}")
            return f"Error getting template: {str(e)}"
    
    def subscribe_template(
        self, user_id, template_id: str, start_date: Optional[str] = None, target_date: Optional[str] = None
    ) -> str:
        """Subscribe to a template (creates a promise and instance)."""
        try:
            from dateutil.parser import parse as parse_date
            
            # Check if unlocked
            unlock_status = self.unlocks_service.get_unlock_status(user_id, template_id)
            if not unlock_status['unlocked']:
                return f"Template is locked: {unlock_status['lock_reason']}"
            
            # Parse dates
            start = None
            target = None
            if start_date:
                try:
                    start = parse_date(start_date).date()
                except:
                    return f"Invalid start_date format: {start_date}"
            if target_date:
                try:
                    target = parse_date(target_date).date()
                except:
                    return f"Invalid target_date format: {target_date}"
            
            result = self.instances_repo.subscribe_template(user_id, template_id, start, target)
            return f"Subscribed to template '{template_id}'. Created promise #{result['promise_id']}."
        except Exception as e:
            logger.error(f"Error subscribing to template: {str(e)}")
            return f"Error subscribing to template: {str(e)}"
    
    def add_checkin(self, user_id, promise_id: str, action_datetime: Optional[datetime] = None) -> str:
        """Record a yes/no check-in for a count-based promise. Use 'I did it today'-style messages."""
        try:
            # Verify promise exists
            promise = self.promises_repo.get_promise(user_id, promise_id)
            if not promise:
                return f"Promise with ID '{promise_id}' not found."
            
            if not action_datetime:
                action_datetime = datetime.now()
            
            action = Action(
                user_id=user_id,
                promise_id=promise_id,
                action=ActionType.CHECKIN.value,
                time_spent=0.0,
                at=action_datetime
            )
            
            self.actions_repo.append_action(action)
            return f"Check-in recorded for promise ID '{promise_id}'."
        except Exception as e:
            logger.error(f"Error recording check-in: {str(e)}")
            return f"Error recording check-in: {str(e)}"
    
    def resolve_datetime(self, user_id, datetime_text: str) -> str:
        """Resolve a date/time phrase ('tomorrow 3pm', 'tonight', 'end of March') to an ISO datetime."""
        try:
            import dateparser
            import re

            settings = self.settings_repo.get_settings(int(user_id))
            tz_raw = getattr(settings, "timezone", None)
            user_tz = tz_raw if tz_raw and tz_raw != "DEFAULT" else "UTC"
            try:
                now_local = datetime.now(ZoneInfo(user_tz))
            except Exception:
                user_tz = "UTC"
                now_local = datetime.now(ZoneInfo("UTC"))

            # Normalize: strip parenthetical annotations like "(سه‌شنبه)" or "(Tuesday)"
            # which dateparser chokes on, and trim stray punctuation/whitespace.
            normalized = re.sub(r"\([^)]*\)", " ", datetime_text or "")
            normalized = re.sub(r"\s+", " ", normalized).strip(" .,،؛;:!?")
            if not normalized:
                normalized = (datetime_text or "").strip()

            # Parse with user-local relative base/timezone. Bias toward future since
            # users overwhelmingly schedule forward ("Friday", "tonight", "tomorrow").
            parsed = dateparser.parse(
                normalized,
                languages=["en", "fa", "fr", "ar", "ru"],
                settings={
                    "RELATIVE_BASE": now_local,
                    "TIMEZONE": user_tz,
                    "RETURN_AS_TIMEZONE_AWARE": True,
                    "PREFER_DATES_FROM": "future",
                },
            )
            if not parsed:
                return f"Could not parse datetime: '{datetime_text}'. Please use a clearer date/time description."

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ZoneInfo(user_tz))

            # Return ISO format datetime (timezone-aware when available).
            return parsed.isoformat()
        except ImportError:
            # Fallback if dateparser not available
            try:
                # Try basic ISO format
                parsed = datetime.fromisoformat(datetime_text.replace('Z', '+00:00'))
                return parsed.isoformat()
            except Exception:
                return f"Could not parse datetime: '{datetime_text}'. Please use ISO format (YYYY-MM-DDTHH:MM:SS)."
        except Exception as e:
            logger.error(f"Error resolving datetime: {str(e)}")
            return f"Error resolving datetime: {str(e)}"
    
    def get_overload_status(self, user_id) -> str:
        """Check if user is overloaded with too many active promises and suggest reducing scope."""
        try:
            instances = self.instances_repo.list_active_instances(user_id)
            promises = self.promises_repo.list_promises(user_id)
            
            # Calculate estimated weekly load
            total_estimated_hours = 0.0
            for instance in instances:
                target = instance['target_value']
                hours_per_unit = instance['estimated_hours_per_unit']
                if instance['metric_type'] == 'hours':
                    total_estimated_hours += target
                else:  # count
                    total_estimated_hours += target * hours_per_unit
            
            # Get recent actual weekly hours
            from datetime import datetime, timedelta
            ref_time = datetime.now()
            weekly_summary = self.reports_service.get_weekly_summary(user_id, ref_time)
            total_actual = sum(p.get('hours_spent', 0) for p in weekly_summary.values())
            
            # Check overload (estimated > 40 hours/week or actual > 35 hours/week consistently)
            is_overloaded = total_estimated_hours > 40 or (total_actual > 35 and len(instances) > 3)
            
            result = []
            result.append(f"Active template instances: {len(instances)}")
            result.append(f"Total promises: {len(promises)}")
            result.append(f"Estimated weekly load: {total_estimated_hours:.1f}h")
            result.append(f"Recent actual weekly: {total_actual:.1f}h")
            
            if is_overloaded:
                result.append("\n⚠️ OVERLOAD DETECTED")
                result.append("Recommendation: Reduce scope by:")
                result.append("1. Completing or abandoning some active instances")
                result.append("2. Downgrading to lower-level templates")
                result.append("3. Pausing some commitments temporarily")
            else:
                result.append("\n✅ Load looks manageable")
            
            return "\n".join(result)
        except Exception as e:
            logger.error(f"Error checking overload status: {str(e)}")
            return f"Error checking overload status: {str(e)}"
    
    def log_distraction(self, user_id, category: str, minutes: float, at: Optional[str] = None) -> str:
        """Log a distraction event (for budget templates)."""
        try:
            from datetime import datetime
            from dateutil.parser import parse as parse_datetime
            
            action_datetime = None
            if at:
                try:
                    action_datetime = parse_datetime(at)
                    if action_datetime.tzinfo is not None:
                        action_datetime = action_datetime.replace(tzinfo=None)
                except:
                    return f"Invalid datetime format: {at}"
            else:
                action_datetime = datetime.now()
            
            event_uuid = self.distractions_repo.log_distraction(user_id, category, minutes, action_datetime)
            return f"Distraction logged: {minutes} minutes in '{category}' category."
        except Exception as e:
            logger.error(f"Error logging distraction: {str(e)}")
            return f"Error logging distraction: {str(e)}"
    
    # Profile methods (exposed as LLM tools)
    def upsert_profile_fact(
        self,
        user_id,
        field_key: str,
        field_value: Union[str, List[str]],
        source: str = "inferred",
        confidence: float = 0.7,
    ) -> str:
        """
        Upsert a profile fact (e.g., status, schedule_type, primary_goal_1y, top_focus_area, main_constraint).
        
        Args:
            field_key: Profile field name (e.g., 'status', 'primary_goal_1y')
            field_value: The value to store (string, or list of strings which will be joined with commas)
            source: 'explicit_answer' (user directly answered), 'inferred' (extracted from conversation), or 'system'
            confidence: Confidence score 0.0-1.0 (1.0 for explicit answers, lower for inferred)
        
        Returns:
            Success message
        """
        try:
            if isinstance(field_value, list):
                field_value = ", ".join(str(v) for v in field_value)
            else:
                field_value = str(field_value)
            self.profile_service.upsert_fact(user_id, field_key, field_value, source, confidence)
            return f"Profile fact '{field_key}' updated to: {field_value}"
        except Exception as e:
            logger.error(f"Error upserting profile fact: {str(e)}")
            return f"Error updating profile: {str(e)}"
    
    def get_profile_status(self, user_id) -> str:
        """
        Get user profile status: completion, known facts, missing fields, pending question.
        
        Returns:
            JSON string with profile status
        """
        try:
            status = self.profile_service.get_profile_status(user_id)
            return json.dumps(status, indent=2)
        except Exception as e:
            logger.error(f"Error getting profile status: {str(e)}")
            return json.dumps({"error": str(e)})
    
    def maybe_ask_profile_question(self, user_id) -> str:
        """
        Check if we should ask a profile question and enqueue it if eligible.
        Only asks if: no pending question exists, profile incomplete, cooldown passed.
        
        Returns:
            JSON string: {"should_ask": bool, "field_key": str or null, "question_text": str or null}
        """
        try:
            result = self.profile_service.maybe_enqueue_next_question(user_id, cooldown_hours=24)
            if result:
                return json.dumps(result)
            else:
                return json.dumps({"should_ask": False, "field_key": None, "question_text": None})
        except Exception as e:
            logger.error(f"Error checking profile question eligibility: {str(e)}")
            return json.dumps({"should_ask": False, "field_key": None, "question_text": None, "error": str(e)})
    
    def clear_profile_pending_question(self, user_id) -> str:
        """
        Clear the pending profile question (call after user answers it).
        
        Returns:
            Success message
        """
        try:
            self.profile_service.clear_pending_question(user_id)
            return "Pending profile question cleared."
        except Exception as e:
            logger.error(f"Error clearing pending question: {str(e)}")
            return f"Error clearing pending question: {str(e)}"
    
    # =========================================================================
    # Social/Community Tools
    # =========================================================================
    # Privacy notes:
    # - All methods use the authenticated user_id (enforced by tool wrapper)
    # - Users can only query their own followers/following, not other users'
    # - Only public info (username, first_name) is returned, not sensitive data
    # - Follow/unfollow actions are always from the authenticated user's account
    
    def get_my_followers(self, user_id) -> str:
        """Get list of users who follow you."""
        return self.social_service.get_followers(int(user_id))
    
    def get_my_following(self, user_id) -> str:
        """Get list of users you follow."""
        return self.social_service.get_following(int(user_id))
    
    def get_community_stats(self, user_id) -> str:
        """Get your community statistics (follower and following counts)."""
        return self.social_service.get_community_stats(int(user_id))
    
    def follow_user(self, user_id, target_username: str) -> str:
        """Follow another user by their username."""
        return self.social_service.follow_user(int(user_id), target_username)
    
    def unfollow_user(self, user_id, target_username: str) -> str:
        """Unfollow a user by their username."""
        return self.social_service.unfollow_user(int(user_id), target_username)

    # =========================================================================
    # Plan Session Tools (Promise → Session → Checklist)
    # =========================================================================

    def get_plan_sessions(self, user_id, promise_id: str) -> str:
        """List all scheduled sessions for a promise (planned, done, and skipped).

        Returns sessions with status, scheduled datetime, duration, and checklist counts.
        Use this to check what sessions exist before scheduling or completing one.

        Args:
            promise_id: Promise ID (e.g. 'P10')
        """
        try:
            with get_db_session() as session:
                p_uuid = resolve_promise_uuid(session, str(user_id), promise_id)
            if not p_uuid:
                return f"Promise '{promise_id}' not found."
            sessions = self.plan_sessions_repo.list_for_promise(p_uuid, user_id)
            if not sessions:
                return f"No sessions found for promise {promise_id}."
            lines = []
            for s in sessions:
                status_icon = {"planned": "\U0001f4c5", "done": "\u2705", "skipped": "\u23ed\ufe0f"}.get(s["status"], "\u2753")
                title = s.get("title") or "Untitled session"
                start = s.get("planned_start") or "No time set"
                dur = f"{s['planned_duration_min']} min" if s.get("planned_duration_min") else "?"
                checklist = s.get("checklist") or []
                cl_summary = f" ({len(checklist)} checklist items)" if checklist else ""
                lines.append(f"  #{s['id']} {status_icon} {title} \u2014 {start} | {dur}{cl_summary}")
            return f"Sessions for {promise_id}:\n" + "\n".join(lines)
        except Exception as e:
            logger.error(f"get_plan_sessions error: {e}")
            return f"Error fetching sessions: {str(e)}"

    def schedule_session(
        self,
        user_id,
        promise_id: str,
        title: Optional[str] = None,
        planned_start: Optional[str] = None,
        planned_duration_min: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> str:
        """Schedule a FUTURE work session (time block) tied to an existing promise.

        Use when the user wants to plan doing something in the future for a specific
        duration against a promise they already track. Requires a promise_id.
        Examples: 'gym tomorrow at 7pm for 1 hour', 'study session Thursday 2h'.

        Never use for past activity (use log_completed_activity) or for one-off
        reminders with no associated promise (use create_reminder).

        planned_start must be an ISO datetime string; call resolve_datetime() first.
        planned_duration_min is in minutes (e.g. 60 for 1 hour, 30 for 30 minutes).

        Args:
            promise_id: Promise ID (e.g. 'P10')
            title: Optional label for this session (e.g. 'Morning run')
            planned_start: ISO datetime string; resolve with resolve_datetime() first
            planned_duration_min: Duration in minutes (integer)
            notes: Optional notes for this session
        """
        try:
            with get_db_session() as session:
                p_uuid = resolve_promise_uuid(session, str(user_id), promise_id)
            if not p_uuid:
                return f"Promise '{promise_id}' not found."
            data = {
                "title": title,
                "planned_start": planned_start,
                "planned_duration_min": planned_duration_min,
                "notes": notes,
                "checklist": [],
            }
            result = self.plan_sessions_repo.create(p_uuid, user_id, data)
            dur_str = f"{planned_duration_min} min" if planned_duration_min else "unspecified duration"
            start_str = planned_start or "no time set"
            session_title = title or "session"
            return (
                f"\u2705 Session #{result['id']} scheduled for promise {promise_id}: "
                f"'{session_title}' on {start_str} ({dur_str})."
            )
        except Exception as e:
            logger.error(f"schedule_session error: {e}")
            return f"Error scheduling session: {str(e)}"

    # Back-compat alias for internal Python callers; not exposed to the LLM
    # (see EXCLUDED_TOOLS in llm_handler._build_tools).
    add_plan_session = schedule_session

    def update_plan_session_status(
        self,
        user_id,
        session_id: int,
        status: str,
    ) -> str:
        """Mark a planned session as done, skipped, or back to planned.

        When marking 'done', this also logs time on the linked promise automatically
        if the session had a planned_duration_min. Use get_upcoming_sessions or
        get_plan_sessions to find the session_id first.
        Allowed status values: 'done', 'skipped', 'planned'.

        Args:
            session_id: Numeric session ID (from get_plan_sessions / get_upcoming_sessions)
            status: New status: 'done', 'skipped', or 'planned'
        """
        if status not in ("done", "skipped", "planned"):
            return "Invalid status. Use 'done', 'skipped', or 'planned'."
        try:
            result = self.plan_sessions_repo.update_status(session_id, user_id, status)
            if not result:
                return f"Session #{session_id} not found."

            # Auto-log time to the promise when marking a timed session done
            if status == "done" and result.get("planned_duration_min"):
                duration_hours = result["planned_duration_min"] / 60.0
                p_uuid = result.get("promise_uuid")
                if p_uuid:
                    try:
                        from sqlalchemy import text as _text
                        with get_db_session() as db_session:
                            row = db_session.execute(
                                _text("SELECT current_id FROM promises WHERE promise_uuid = :uuid LIMIT 1"),
                                {"uuid": p_uuid},
                            ).fetchone()
                        if row and row[0]:
                            self.add_action(user_id, row[0], duration_hours)
                    except Exception as log_err:
                        logger.warning(f"Could not auto-log time for completed session {session_id}: {log_err}")

            status_msg = {
                "done": "\u2705 Marked done",
                "skipped": "\u23ed\ufe0f Skipped",
                "planned": "\U0001f4c5 Reset to planned",
            }[status]
            title = result.get("title") or f"Session #{session_id}"
            return f"{status_msg}: '{title}'."
        except Exception as e:
            logger.error(f"update_plan_session_status error: {e}")
            return f"Error updating session: {str(e)}"

    def delete_plan_session(self, user_id, session_id: int) -> str:
        """Cancel and delete a scheduled session for a promise.

        Use when the user wants to cancel a planned work block.
        Get the session_id first using get_plan_sessions or get_upcoming_sessions.

        Args:
            session_id: Numeric session ID to cancel
        """
        try:
            deleted = self.plan_sessions_repo.delete(session_id, user_id)
            if not deleted:
                return f"Session #{session_id} not found."
            return f"\U0001f5d1\ufe0f Session #{session_id} cancelled."
        except Exception as e:
            logger.error(f"delete_plan_session error: {e}")
            return f"Error cancelling session: {str(e)}"

    def get_upcoming_sessions(self, user_id, days_ahead: int = 7) -> str:
        """Get all planned sessions across all promises for the next N days (default 7).

        Use to give the user an overview of their scheduled work blocks.
        Shows promise name, session title, scheduled datetime, and duration.

        Args:
            days_ahead: Number of days to look ahead (default 7)
        """
        try:
            from datetime import timezone, timedelta
            now = datetime.now(timezone.utc)
            since_iso = now.isoformat()
            until_iso = (now + timedelta(days=days_ahead)).isoformat()
            sessions = self.plan_sessions_repo.list_upcoming_for_user(user_id, since_iso, until_iso)
            if not sessions:
                return f"No planned sessions in the next {days_ahead} days."
            lines = [f"Upcoming sessions (next {days_ahead} days):"]
            for s in sessions:
                p_text = (s.get("promise_text") or s.get("promise_id") or "unknown promise").replace("_", " ")
                title = s.get("title") or f"Session #{s['id']}"
                start = s.get("planned_start") or "?"
                dur = f"{s['planned_duration_min']} min" if s.get("planned_duration_min") else "?"
                lines.append(f"  #{s['id']} [{p_text}] '{title}' \u2014 {start} | {dur}")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"get_upcoming_sessions error: {e}")
            return f"Error fetching upcoming sessions: {str(e)}"

    # ---------------------------------------------------------------------------
    # Async wrappers – offload sync DB/service calls to a thread pool so they
    # never block the asyncio event loop when concurrent_updates is enabled.
    # ---------------------------------------------------------------------------

    async def async_get_settings(self, user_id) -> Any:
        """Non-blocking wrapper for settings_service.get_settings."""
        return await asyncio.to_thread(self.settings_service.get_settings, user_id)

    async def async_save_settings(self, settings) -> None:
        """Non-blocking wrapper for settings_service.save_settings."""
        await asyncio.to_thread(self.settings_service.save_settings, settings)

    async def async_get_promises(self, user_id) -> List[Dict]:
        """Non-blocking wrapper for get_promises."""
        return await asyncio.to_thread(self.get_promises, user_id)

    async def async_get_promise_report(self, user_id, promise_id: str) -> str:
        """Non-blocking wrapper for get_promise_report."""
        return await asyncio.to_thread(self.get_promise_report, user_id, promise_id)

    async def async_get_weekly_summary(self, user_id, ref_time=None) -> Any:
        """Non-blocking wrapper for reports_service.get_weekly_summary."""
        return await asyncio.to_thread(self.reports_service.get_weekly_summary, user_id, ref_time)
