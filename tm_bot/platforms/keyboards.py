"""
Platform-agnostic keyboard builder utilities.

This module provides helper functions to create platform-agnostic keyboards
that can be converted to platform-specific formats (Telegram, Discord, etc.).
"""

from typing import List, Optional
from datetime import datetime

from .types import Keyboard, KeyboardButton
from models.models import Promise
from utils.time_utils import beautify_time, round_time
from cbdata import encode_cb


def create_button(text: str, callback_data: Optional[str] = None, url: Optional[str] = None, web_app_url: Optional[str] = None) -> KeyboardButton:
    """Create a platform-agnostic keyboard button."""
    return KeyboardButton(text=text, callback_data=callback_data, url=url, web_app_url=web_app_url)


def nightly_card_kb(promises_top3: List[Promise], has_more: bool = False) -> Keyboard:
    """Create keyboard for nightly reminder card."""
    keyboard = Keyboard()
    
    for promise in promises_top3:
        button = create_button(
            text=f"Log time for #{promise.id}",
            callback_data=encode_cb("session_start", promise.id)
        )
        keyboard.add_row(button)
    
    if has_more:
        more_button = create_button(
            text="Show more promises",
            callback_data=encode_cb("show_more")
        )
        keyboard.add_row(more_button)
    
    return keyboard


def weekly_report_kb(ref_time: datetime, miniapp_url: Optional[str] = None) -> Keyboard:
    """Create keyboard for weekly report with refresh button and optional mini app button."""
    keyboard = Keyboard()
    refresh_callback = encode_cb("refresh_weekly", t=str(int(ref_time.timestamp())))
    refresh_button = create_button(text="🔄 Refresh", callback_data=refresh_callback)
    
    if miniapp_url:
        # Format ref_time as ISO datetime for URL parameter
        ref_time_iso = ref_time.isoformat()
        mini_app_url_with_params = f"{miniapp_url}?ref_time={ref_time_iso}"
        mini_app_button = create_button(text="🌐 View in App", web_app_url=mini_app_url_with_params)
        # Add both buttons on the same row
        keyboard.add_row(refresh_button, mini_app_button)
    else:
        # Only refresh button if no miniapp_url provided
        keyboard.add_row(refresh_button)
    
    return keyboard


def _adaptive_step_min(curr_h: float, base_day_h: float) -> int:
    """Return an adaptive step in minutes based on current/base size."""
    m = max(curr_h, base_day_h) * 60
    if m < 20:
        return 5
    if m < 45:
        return 10
    if m < 120:
        return 15
    if m < 240:
        return 30
    return 60


def time_options_kb(
    promise_id: str,
    curr_h: float,
    base_day_h: float,
    weekly_h: Optional[float] = None,
    show_timer: bool = False,  # TODO: Implement show_timer functionality
) -> Keyboard:
    """
    Create keyboard for time selection options.
    
    Row 1:  🙅 None | 🟢 <current> | 🏁 max
    Row 2:  Skip (wk) | -X | +2X   (X is adaptive)
    """
    keyboard = Keyboard()
    
    # Robust inputs
    base_day_h = max(0.0, float(base_day_h or 0.0))
    weekly_h = float(weekly_h) if weekly_h is not None else base_day_h * 7.0

    if curr_h <= 0.5:
        curr_h = max(0.0, round_time(curr_h, step_min=5))
    else:
        curr_h = round_time(curr_h, step_min=15)

    # Max: cap to 7h/day for big workloads; otherwise let small quotas reach their whole weekly target.
    max_h = round_time(max(base_day_h, min(weekly_h, 7.0)), step_min=15)

    # Adaptive delta
    step_min = _adaptive_step_min(curr_h, base_day_h)
    delta_h = step_min / 60.0
    two_delta = 2 * delta_h

    # Row 1 — one-tap logs
    row1 = [
        create_button("🙅 None", callback_data=encode_cb("time_spent", pid=promise_id, value=0.0)),
        create_button(f"🟢 {beautify_time(curr_h)}", callback_data=encode_cb("time_spent", pid=promise_id, value=curr_h)),
        create_button(f"🏁 {beautify_time(max_h)}", callback_data=encode_cb("time_spent", pid=promise_id, value=max_h)),
    ]
    keyboard.add_row(*row1)

    # Row 2 — skip week + adaptive −X / +2X
    row2 = [
        create_button("⏭️ Skip (wk)", callback_data=encode_cb("remind_next_week", pid=promise_id)),
        create_button(f"-{int(step_min)}m", callback_data=encode_cb("update_time_spent", pid=promise_id, value=-delta_h, c=curr_h)),
        create_button(f"+{int(2*step_min)}m", callback_data=encode_cb("update_time_spent", pid=promise_id, value=two_delta, c=curr_h)),
    ]
    keyboard.add_row(*row2)

    return keyboard


def pomodoro_kb() -> Keyboard:
    """Create keyboard for Pomodoro timer."""
    keyboard = Keyboard()
    buttons = [
        create_button("Start", callback_data=encode_cb("pomodoro_start")),
        create_button("Pause", callback_data=encode_cb("pomodoro_pause")),
        create_button("Stop", callback_data=encode_cb("pomodoro_stop"))
    ]
    keyboard.add_row(*buttons)
    return keyboard


def language_selection_kb() -> Keyboard:
    """Create keyboard for language selection."""
    keyboard = Keyboard()
    buttons = [
        create_button("English", callback_data=encode_cb("set_language", lang="en")),
        create_button("فارسی (Persian)", callback_data=encode_cb("set_language", lang="fa")),
        create_button("Français (French)", callback_data=encode_cb("set_language", lang="fr"))
    ]
    for button in buttons:
        keyboard.add_row(button)
    return keyboard


def voice_mode_selection_kb() -> Keyboard:
    """Create keyboard for voice mode preference selection."""
    keyboard = Keyboard()
    keyboard.add_row(create_button("✅ Yes, enable voice mode", callback_data=encode_cb("voice_mode", enabled="true")))
    keyboard.add_row(create_button("❌ No, text only", callback_data=encode_cb("voice_mode", enabled="false")))
    return keyboard


def morning_calendar_kb() -> Keyboard:
    """Create keyboard for morning calendar question."""
    keyboard = Keyboard()
    buttons = [
        create_button("✅ Yes, add to calendar", callback_data=encode_cb("add_to_calendar_yes")),
        create_button("❌ No, thanks", callback_data=encode_cb("add_to_calendar_no")),
    ]
    keyboard.add_row(*buttons)
    return keyboard


def content_actions_kb(
    calendar_url: Optional[str] = None,
    url: Optional[str] = None,
    can_summarize: bool = False,
    url_id: Optional[str] = None
) -> Optional[Keyboard]:
    """
    Create keyboard for content actions (calendar, summarize).
    
    Args:
        calendar_url: Google Calendar URL (uses url button, no size limit)
        url: Original content URL (stored separately if needed)
        can_summarize: Whether to show summarize button
        url_id: Short ID for URL storage (if provided, use this instead of encoding URL)
    """
    keyboard = Keyboard()
    
    if calendar_url:
        keyboard.add_row(create_button("📅 Add to Calendar", url=calendar_url))
    
    if can_summarize and url_id:
        # Use short ID instead of full URL to avoid callback_data size limit (64 bytes)
        keyboard.add_row(create_button("📝 Summarize", callback_data=encode_cb("summarize_content", url_id=url_id)))
    
    return keyboard if keyboard.buttons else None


def preping_kb(promise_id: str, snooze_min: int = 30) -> Keyboard:
    """Create keyboard for preping (pre-session) actions."""
    keyboard = Keyboard()
    buttons = [
        create_button("Start ⏱", callback_data=encode_cb("preping_start", pid=promise_id)),
        create_button(f"Snooze {snooze_min}m", callback_data=encode_cb("preping_snooze", pid=promise_id, m=snooze_min)),
        create_button("Not today 🙅", callback_data=encode_cb("preping_skip", pid=promise_id)),
    ]
    keyboard.add_row(*buttons)
    return keyboard


def session_running_kb(session_id: str) -> Keyboard:
    """Create keyboard for running session controls."""
    keyboard = Keyboard()
    row1 = [
        create_button("Pause ⏸️", callback_data=encode_cb("session_pause", s=session_id)),
        create_button("Finish ✅", callback_data=encode_cb("session_finish_open", s=session_id)),
    ]
    keyboard.add_row(*row1)
    
    row2 = [
        create_button("+15m", callback_data=encode_cb("session_plus", s=session_id, v=0.25)),
        create_button("+30m", callback_data=encode_cb("session_plus", s=session_id, v=0.50)),
        create_button("Snooze 10m", callback_data=encode_cb("session_snooze", s=session_id, m=10)),
    ]
    keyboard.add_row(*row2)
    return keyboard


def session_paused_kb(session_id: str) -> Keyboard:
    """Create keyboard for paused session controls."""
    keyboard = Keyboard()
    row1 = [
        create_button("Resume ▶️", callback_data=encode_cb("session_resume", s=session_id)),
        create_button("Finish ✅", callback_data=encode_cb("session_finish_open", s=session_id)),
    ]
    keyboard.add_row(*row1)
    
    keyboard.add_row(create_button("Snooze 10m", callback_data=encode_cb("session_snooze", s=session_id, m=10)))
    return keyboard


def session_finish_confirm_kb(session_id: str, proposed_h: float) -> Keyboard:
    """Create keyboard for session finish confirmation."""
    keyboard = Keyboard()
    buttons = [
        create_button(
            f"Looks right ✅ ({beautify_time(proposed_h)})",
            callback_data=encode_cb("session_finish_confirm", s=session_id, v=proposed_h)
        ),
        create_button("Adjust…", callback_data=encode_cb("session_adjust_open", s=session_id, v=proposed_h)),
    ]
    keyboard.add_row(*buttons)
    return keyboard


def session_adjust_kb(session_id: str, base_h: float) -> Keyboard:
    """Create keyboard for session time adjustment."""
    keyboard = Keyboard()
    # e.g., chips: 15m · 30m · 45m · 1h
    chips = [0.25, 0.5, 0.75, 1.0]
    buttons = [
        create_button(beautify_time(h), callback_data=encode_cb("session_adjust_set", s=session_id, v=h))
        for h in chips
    ]
    keyboard.add_row(*buttons)
    return keyboard


def broadcast_confirmation_kb() -> Keyboard:
    """Create keyboard for broadcast confirmation (Schedule/Cancel)."""
    keyboard = Keyboard()
    buttons = [
        create_button("📅 Schedule", callback_data=encode_cb("broadcast_schedule")),
        create_button("❌ Cancel", callback_data=encode_cb("broadcast_cancel"))
    ]
    keyboard.add_row(*buttons)
    return keyboard


def session_controls_kb(session_running: bool) -> Keyboard:
    """Create keyboard for session controls."""
    keyboard = Keyboard()
    if session_running:
        buttons = [
            create_button("⏸️ Pause", callback_data=encode_cb("session_pause")),
            create_button("⏹️ Stop", callback_data=encode_cb("session_finish"))
        ]
    else:
        buttons = [
            create_button("▶️ Resume", callback_data=encode_cb("session_resume")),
            create_button("⏹️ Stop", callback_data=encode_cb("session_finish"))
        ]
    keyboard.add_row(*buttons)
    return keyboard


def delete_confirmation_kb(promise_id: str) -> Keyboard:
    """Create keyboard for delete confirmation."""
    keyboard = Keyboard()
    buttons = [
        create_button("Yes (delete)", callback_data=encode_cb("confirm_delete", promise_id)),
        create_button("No (cancel)", callback_data=encode_cb("cancel_delete", promise_id))
    ]
    keyboard.add_row(*buttons)
    return keyboard


def mini_app_kb(mini_app_url: str, button_text: str = "Open App") -> Keyboard:
    """Create keyboard with mini app button."""
    keyboard = Keyboard()
    button = create_button(button_text, web_app_url=mini_app_url)
    keyboard.add_row(button)
    return keyboard

