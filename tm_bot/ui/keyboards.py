from typing import List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from models.models import Promise
from utils.time_utils import beautify_time, round_time
from cbdata import encode_cb


def nightly_card_kb(promises_top3: List[Promise], has_more: bool = False) -> InlineKeyboardMarkup:
    """Create keyboard for nightly reminder card."""
    buttons = []
    
    for promise in promises_top3:
        button = InlineKeyboardButton(
            f"Log time for #{promise.id}",
            callback_data=encode_cb("session_start", promise.id)
        )
        buttons.append([button])
    
    if has_more:
        more_button = InlineKeyboardButton(
            "Show more promises",
            callback_data=encode_cb("show_more")
        )
        buttons.append([more_button])
    
    return InlineKeyboardMarkup(buttons)


def session_controls_kb(session_running: bool) -> InlineKeyboardMarkup:
    """Create keyboard for session controls."""
    if session_running:
        buttons = [
            [
                InlineKeyboardButton("⏸️ Pause", callback_data=encode_cb("session_pause")),
                InlineKeyboardButton("⏹️ Stop", callback_data=encode_cb("session_finish"))
            ]
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton("▶️ Resume", callback_data=encode_cb("session_resume")),
                InlineKeyboardButton("⏹️ Stop", callback_data=encode_cb("session_finish"))
            ]
        ]
    
    return InlineKeyboardMarkup(buttons)


def weekly_report_kb(ref_time) -> InlineKeyboardMarkup:
    """Create keyboard for weekly report with refresh button."""
    refresh_callback = encode_cb("refresh_weekly", str(int(ref_time.timestamp())))
    buttons = [[InlineKeyboardButton("🔄 Refresh", callback_data=refresh_callback)]]
    return InlineKeyboardMarkup(buttons)


def time_options_kb(promise_id: str, hpd_base: float, latest_record: float) -> InlineKeyboardMarkup:
    """Create time selection keyboard for promise actions."""
    # First row buttons
    button_zero = InlineKeyboardButton("0 hrs", callback_data=encode_cb("time_spent", promise_id, 0.0))
    button_latest = InlineKeyboardButton(
        beautify_time(latest_record),
        callback_data=encode_cb("time_spent", promise_id, latest_record)
    )
    hpd_base_rounded = round_time(hpd_base)
    button_default = InlineKeyboardButton(
        beautify_time(hpd_base_rounded),
        callback_data=encode_cb("time_spent", promise_id, hpd_base_rounded)
    )

    # Second row: adjustment buttons for the third option (latest_record)
    adjust_minus = InlineKeyboardButton(
        "-5 min",
        callback_data=encode_cb("update_time_spent", promise_id, -5/60)
    )
    adjust_plus = InlineKeyboardButton(
        "+10 min",
        callback_data=encode_cb("update_time_spent", promise_id, 10/60)
    )
    remind_next_week = InlineKeyboardButton(
        "Remind next week",
        callback_data=encode_cb("remind_next_week", promise_id)
    )
    delete_promise = InlineKeyboardButton(
        "Delete",
        callback_data=encode_cb("delete_promise", promise_id)
    )
    report_button = InlineKeyboardButton(
        "Report",
        callback_data=encode_cb("report_promise", promise_id)
    )

    row1 = [button_zero, button_default, adjust_minus, adjust_plus]
    row2 = [remind_next_week, delete_promise, report_button]

    return InlineKeyboardMarkup([row1, row2])


def pomodoro_kb() -> InlineKeyboardMarkup:
    """Create keyboard for Pomodoro timer."""
    buttons = [
        [
            InlineKeyboardButton("Start", callback_data=encode_cb("pomodoro_start")),
            InlineKeyboardButton("Pause", callback_data=encode_cb("pomodoro_pause")),
            InlineKeyboardButton("Stop", callback_data=encode_cb("pomodoro_stop"))
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def delete_confirmation_kb(promise_id: str) -> InlineKeyboardMarkup:
    """Create keyboard for delete confirmation."""
    buttons = [
        [
            InlineKeyboardButton("Yes (delete)", callback_data=encode_cb("confirm_delete", promise_id)),
            InlineKeyboardButton("No (cancel)", callback_data=encode_cb("cancel_delete", promise_id))
        ]
    ]
    return InlineKeyboardMarkup(buttons)
