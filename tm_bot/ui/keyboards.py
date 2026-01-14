from typing import List, Optional
from telegram import InlineKeyboardMarkup

from models.models import Promise
from platforms.keyboards import (
    nightly_card_kb as _nightly_card_kb,
    weekly_report_kb as _weekly_report_kb,
    time_options_kb as _time_options_kb,
    pomodoro_kb as _pomodoro_kb,
    language_selection_kb as _language_selection_kb,
    voice_mode_selection_kb as _voice_mode_selection_kb,
    morning_calendar_kb as _morning_calendar_kb,
    content_actions_kb as _content_actions_kb,
    preping_kb as _preping_kb,
    session_running_kb as _session_running_kb,
    session_paused_kb as _session_paused_kb,
    session_finish_confirm_kb as _session_finish_confirm_kb,
    session_adjust_kb as _session_adjust_kb,
    broadcast_confirmation_kb as _broadcast_confirmation_kb,
    session_controls_kb as _session_controls_kb,
    delete_confirmation_kb as _delete_confirmation_kb,
    mini_app_kb as _mini_app_kb,
    navigation_kb as _navigation_kb,
)
from platforms.telegram.keyboard_adapter import TelegramKeyboardAdapter

# Adapter to convert platform-agnostic keyboards to Telegram format
_keyboard_adapter = TelegramKeyboardAdapter()


def nightly_card_kb(promises_top3: List[Promise], has_more: bool = False) -> InlineKeyboardMarkup:
    """Create keyboard for nightly reminder card."""
    keyboard = _nightly_card_kb(promises_top3, has_more)
    return _keyboard_adapter.build_keyboard(keyboard)


def session_controls_kb(session_running: bool) -> InlineKeyboardMarkup:
    """Create keyboard for session controls."""
    keyboard = _session_controls_kb(session_running)
    return _keyboard_adapter.build_keyboard(keyboard)


def weekly_report_kb(ref_time, miniapp_url: Optional[str] = None) -> InlineKeyboardMarkup:
    """Create keyboard for weekly report with refresh button and optional mini app button."""
    keyboard = _weekly_report_kb(ref_time, miniapp_url)
    return _keyboard_adapter.build_keyboard(keyboard)

def time_options_kb(
    promise_id: str,
    curr_h: float,
    base_day_h: float,
    weekly_h: float | None = None,
    show_timer: bool = False,  # TODO: Implement show_timer functionality
) -> InlineKeyboardMarkup:
    """
    Row 1:  🙅 None | 🟢 <current> | 🏁 max
    Row 2:  Skip (wk) | -X | +2X   (X is adaptive)
    """
    keyboard = _time_options_kb(promise_id, curr_h, base_day_h, weekly_h, show_timer)
    return _keyboard_adapter.build_keyboard(keyboard)


def pomodoro_kb() -> InlineKeyboardMarkup:
    """Create keyboard for Pomodoro timer."""
    keyboard = _pomodoro_kb()
    return _keyboard_adapter.build_keyboard(keyboard)


def delete_confirmation_kb(promise_id: str) -> InlineKeyboardMarkup:
    """Create keyboard for delete confirmation."""
    keyboard = _delete_confirmation_kb(promise_id)
    return _keyboard_adapter.build_keyboard(keyboard)

def preping_kb(promise_id: str, snooze_min: int = 30):
    keyboard = _preping_kb(promise_id, snooze_min)
    return _keyboard_adapter.build_keyboard(keyboard)

def session_running_kb(session_id: str):
    keyboard = _session_running_kb(session_id)
    return _keyboard_adapter.build_keyboard(keyboard)

def session_paused_kb(session_id: str):
    keyboard = _session_paused_kb(session_id)
    return _keyboard_adapter.build_keyboard(keyboard)

def session_finish_confirm_kb(session_id: str, proposed_h: float):
    keyboard = _session_finish_confirm_kb(session_id, proposed_h)
    return _keyboard_adapter.build_keyboard(keyboard)

def session_adjust_kb(session_id: str, base_h: float):
    keyboard = _session_adjust_kb(session_id, base_h)
    return _keyboard_adapter.build_keyboard(keyboard)


def language_selection_kb() -> InlineKeyboardMarkup:
    """Create keyboard for language selection."""
    keyboard = _language_selection_kb()
    return _keyboard_adapter.build_keyboard(keyboard)


def voice_mode_selection_kb() -> InlineKeyboardMarkup:
    """Create keyboard for voice mode preference selection."""
    keyboard = _voice_mode_selection_kb()
    return _keyboard_adapter.build_keyboard(keyboard)


def morning_calendar_kb() -> InlineKeyboardMarkup:
    """Create keyboard for morning calendar question."""
    keyboard = _morning_calendar_kb()
    return _keyboard_adapter.build_keyboard(keyboard)


def content_actions_kb(calendar_url: str = None, url: str = None, can_summarize: bool = False, url_id: str = None) -> InlineKeyboardMarkup:
    """Create keyboard for content actions (calendar, summarize).
    
    Args:
        calendar_url: Google Calendar URL (uses url button, no size limit)
        url: Original content URL (stored separately if needed)
        can_summarize: Whether to show summarize button
        url_id: Short ID for URL storage (if provided, use this instead of encoding URL)
    """
    keyboard = _content_actions_kb(calendar_url, url, can_summarize, url_id)
    if keyboard:
        return _keyboard_adapter.build_keyboard(keyboard)
    return None


def broadcast_confirmation_kb() -> InlineKeyboardMarkup:
    """Create keyboard for broadcast confirmation (Schedule/Cancel)."""
    keyboard = _broadcast_confirmation_kb()
    return _keyboard_adapter.build_keyboard(keyboard)


def mini_app_kb(mini_app_url: str, button_text: str = "Open App") -> InlineKeyboardMarkup:
    """Create keyboard with mini app button."""
    keyboard = _mini_app_kb(mini_app_url)
    return _keyboard_adapter.build_keyboard(keyboard)


def navigation_kb(mini_app_url: str) -> InlineKeyboardMarkup:
    """Create navigation keyboard with Weekly, Community, and Explore buttons."""
    keyboard = _navigation_kb(mini_app_url)
    return _keyboard_adapter.build_keyboard(keyboard)


