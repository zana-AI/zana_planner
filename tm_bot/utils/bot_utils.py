"""
Common utilities and helper functions for the Telegram bot.
Contains shared logic to avoid DRY violations.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from handlers.messages_store import get_message, get_user_language, Language
from services.planner_api_adapter import PlannerAPIAdapter
from utils.time_utils import beautify_time
from ui.keyboards import time_options_kb
from cbdata import encode_cb

logger = logging.getLogger(__name__)


class BotUtils:
    """Common utilities for bot operations."""
    
    @staticmethod
    def get_user_timezone(plan_keeper: PlannerAPIAdapter, user_id: int) -> str:
        """Get user timezone using the settings repository."""
        settings = plan_keeper.settings_repo.get_settings(user_id)
        return settings.timezone
    
    @staticmethod
    def set_user_timezone(plan_keeper: PlannerAPIAdapter, user_id: int, tzname: str) -> None:
        """Set user timezone using the settings repository."""
        settings = plan_keeper.settings_repo.get_settings(user_id)
        settings.timezone = tzname
        plan_keeper.settings_repo.save_settings(settings)
    
    @staticmethod
    def get_user_now(plan_keeper: PlannerAPIAdapter, user_id: int) -> Tuple[datetime, str]:
        """Return (now_in_user_tz, tzname)."""
        try:
            from zoneinfo import ZoneInfo
            tzname = BotUtils.get_user_timezone(plan_keeper, user_id) or "UTC"
            return datetime.now(ZoneInfo(tzname)), tzname
        except ImportError:
            logger.error("zoneinfo not available")
            return datetime.now(), "UTC"
    
    @staticmethod
    def hours_per_week_of(promise) -> float:
        """Extract hours_per_week whether promise is a dict or a dataclass."""
        try:
            return float(getattr(promise, "hours_per_week"))
        except Exception:
            return float((promise or {}).get("hours_per_week", 0.0) or 0.0)
    
    @staticmethod
    def last_hours_or(plan_keeper: PlannerAPIAdapter, user_id: int, promise_id: str, fallback: float) -> float:
        """Get last hours spent or fallback value."""
        last = plan_keeper.get_last_action_on_promise(user_id, promise_id)
        try:
            return float(getattr(last, "time_spent", fallback) or fallback)
        except Exception:
            return fallback
    
    @staticmethod
    async def send_error_message(update: Update, error_type: str, error_msg: str, user_id: int = None) -> None:
        """Send standardized error messages."""
        if user_id is None:
            user_id = update.effective_user.id
        
        user_lang = get_user_language(user_id)
        
        if error_type == "invalid_input":
            message = get_message("error_invalid_input", user_lang, error=error_msg)
        elif error_type == "general":
            message = get_message("error_general", user_lang, error=error_msg)
        elif error_type == "unexpected":
            message = get_message("error_unexpected", user_lang, error=error_msg)
        else:
            message = get_message("error_general", user_lang, error=error_msg)
        
        await update.message.reply_text(message, parse_mode='Markdown')
        logger.error(f"{error_type} error for user {user_id}: {error_msg}")
    
    @staticmethod
    async def send_callback_error(query, error_msg: str, user_id: int = None) -> None:
        """Send standardized error messages for callbacks."""
        if user_id is None:
            user_id = query.from_user.id
        
        user_lang = get_user_language(user_id)
        message = get_message("error_general", user_lang, error=error_msg)
        await query.edit_message_text(message, parse_mode='Markdown')
        logger.error(f"Callback error for user {user_id}: {error_msg}")
    
    @staticmethod
    def format_promise_list(promises: List[Dict[str, Any]], user_lang: Language) -> str:
        """Format a list of promises for display."""
        if not promises:
            return get_message("no_promises", user_lang)
        
        formatted_promises = ""
        sorted_promises = sorted(promises, key=lambda p: p['id'])
        
        for promise in sorted_promises:
            formatted_promises += get_message("promise_item", user_lang, 
                                            id=promise['id'], 
                                            text=promise['text'].replace('_', ' ')) + "\n"
        
        header = get_message("promises_list_header", user_lang)
        return f"{header}\n{formatted_promises}"
    
    @staticmethod
    async def send_promise_time_options(context: CallbackContext, user_id: int, promise, user_lang: Language) -> None:
        """Send time options for a promise."""
        weekly_h = BotUtils.hours_per_week_of(promise)
        base_day_h = weekly_h / 7.0
        last = context.bot_data.get('plan_keeper').get_last_action_on_promise(user_id, promise.id)
        curr_h = float(getattr(last, "time_spent", 0.0) or base_day_h)
        
        kb = time_options_kb(promise.id, curr_h=curr_h, base_day_h=base_day_h, weekly_h=weekly_h)
        message = get_message("nightly_question", user_lang, promise_text=promise.text)
        
        await context.bot.send_message(
            chat_id=user_id,
            text=message,
            reply_markup=kb,
            parse_mode="Markdown",
        )
    
    @staticmethod
    def create_show_more_keyboard(remaining_count: int, offset: int, batch_size: int, user_lang: Language) -> InlineKeyboardMarkup:
        """Create a 'show more' keyboard."""
        button_text = get_message("show_more_button", user_lang, count=remaining_count)
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(
                button_text,
                callback_data=encode_cb("show_more", o=offset, n=batch_size)
            )
        ]])
    
    @staticmethod
    async def handle_reminder_batch(context: CallbackContext, user_id: int, promises: List, 
                                  start_idx: int, batch_size: int, user_lang: Language) -> None:
        """Handle sending a batch of reminder messages."""
        plan_keeper = context.bot_data.get('plan_keeper')
        
        for promise in promises[start_idx:start_idx + batch_size]:
            weekly_h = BotUtils.hours_per_week_of(promise)
            base_day_h = weekly_h / 7.0
            last = plan_keeper.get_last_action_on_promise(user_id, promise.id)
            curr_h = float(getattr(last, "time_spent", 0.0) or base_day_h)
            
            kb = time_options_kb(promise.id, curr_h=curr_h, base_day_h=base_day_h, weekly_h=weekly_h)
            message = get_message("nightly_question", user_lang, promise_text=promise.text)
            
            await context.bot.send_message(
                chat_id=user_id,
                text=message,
                reply_markup=kb,
                parse_mode="Markdown",
            )
    
    @staticmethod
    def validate_timezone(tzname: str) -> bool:
        """Validate if timezone string is valid."""
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(tzname)
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_next_monday() -> datetime:
        """Get next Monday date."""
        return datetime.now() + timedelta(days=(7 - datetime.now().weekday()))
    
    @staticmethod
    def ensure_user_directory(root_dir: str, user_id: int) -> bool:
        """Ensure user directory exists, return True if created."""
        user_dir = os.path.join(root_dir, str(user_id))
        if not os.path.exists(user_dir):
            from utils_storage import create_user_directory
            return create_user_directory(root_dir, user_id)
        return False
    
    @staticmethod
    def format_session_text(session, promise_text: str, elapsed: str) -> str:
        """Format session text for display."""
        return (f"⏱ *Session for #{session.promise_id}: {promise_text}*"
                f"\nStarted {session.started_at.strftime('%H:%M')} | Elapsed: {elapsed}")
    
    @staticmethod
    def calculate_effective_hours(session) -> float:
        """Calculate effective hours for a session."""
        # TODO: implement proper session effective hours calculation
        return 0.5  # Placeholder implementation
    
    @staticmethod
    def parse_callback_data(query_data: str) -> Dict[str, Any]:
        """Parse callback data with error handling."""
        try:
            from cbdata import decode_cb
            return decode_cb(query_data)
        except Exception as e:
            logger.error(f"Error parsing callback data: {e}")
            return {}
    
    @staticmethod
    def safe_float_conversion(value: Any, default: float = 0.0) -> float:
        """Safely convert value to float."""
        try:
            return float(value) if value is not None else default
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def safe_int_conversion(value: Any, default: int = 0) -> int:
        """Safely convert value to int."""
        try:
            return int(value) if value is not None else default
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def get_promise_text(promise) -> str:
        """Extract text from promise object safely."""
        if hasattr(promise, 'text'):
            return promise.text
        elif isinstance(promise, dict):
            return promise.get('text', 'Unknown')
        else:
            return 'Unknown'
    
    @staticmethod
    def create_confirmation_keyboard(action: str, item_id: str, user_lang: Language) -> InlineKeyboardMarkup:
        """Create a confirmation keyboard for delete actions."""
        buttons = [
            InlineKeyboardButton(
                get_message("btn_yes_delete", user_lang), 
                callback_data=encode_cb(f"confirm_{action}", pid=item_id)
            ),
            InlineKeyboardButton(
                get_message("btn_no_cancel", user_lang), 
                callback_data=encode_cb(f"cancel_{action}", pid=item_id)
            ),
        ]
        return InlineKeyboardMarkup([buttons])
    
    @staticmethod
    def log_user_action(user_id: int, action: str, details: str = "") -> None:
        """Log user actions for debugging."""
        logger.info(f"User {user_id} performed action: {action} {details}")
    
    @staticmethod
    def format_time_duration(hours: float) -> str:
        """Format time duration in a user-friendly way."""
        if hours < 1:
            minutes = int(hours * 60)
            return f"{minutes}m"
        elif hours < 24:
            whole_hours = int(hours)
            remaining_minutes = int((hours - whole_hours) * 60)
            if remaining_minutes == 0:
                return f"{whole_hours}h"
            else:
                return f"{whole_hours}h {remaining_minutes}m"
        else:
            days = int(hours / 24)
            remaining_hours = int(hours % 24)
            if remaining_hours == 0:
                return f"{days}d"
            else:
                return f"{days}d {remaining_hours}h"
