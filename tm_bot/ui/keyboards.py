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
    refresh_callback = encode_cb("refresh_weekly", t=str(int(ref_time.timestamp())))
    buttons = [[InlineKeyboardButton("🔄 Refresh", callback_data=refresh_callback)]]
    return InlineKeyboardMarkup(buttons)

def _adaptive_step_min(curr_h: float, base_day_h: float) -> int:
    """Return an adaptive step in minutes based on current/base size."""
    m = max(curr_h, base_day_h) * 60
    if m < 20:   return 5
    if m < 45:   return 10
    if m < 120:  return 15
    if m < 240:  return 30
    return 60

def time_options_kb(
    promise_id: str,
    curr_h: float,
    base_day_h: float,
    weekly_h: float | None = None,   # pass hours_per_week if you have it
    show_timer: bool = False,  # TODO: Implement show_timer functionality
) -> InlineKeyboardMarkup:
    """
    Row 1:  🙅 None | 🟢 <current> | 🏁 max
    Row 2:  Skip (wk) | -X | +2X   (X is adaptive)
    """
    # Robust inputs
    base_day_h = max(0.0, float(base_day_h or 0.0))
    weekly_h   = float(weekly_h) if weekly_h is not None else base_day_h * 7.0

    if curr_h <= 0.5:
        curr_h = max(0.0, round_time(curr_h, step_min=5))
    else:
        curr_h = round_time(curr_h, step_min=15)

    # Max: cap to 7h/day for big workloads; otherwise let small quotas reach their whole weekly target.
    # e.g. deep work 35h/wk -> max 7h; call family 1h/wk -> max 1h
    max_h = round_time(max(base_day_h, min(weekly_h, 7.0)), step_min=15)

    # Adaptive delta
    step_min   = _adaptive_step_min(curr_h, base_day_h)
    delta_h    = step_min / 60.0
    two_delta  = 2 * delta_h

    # Row 1 — one-tap logs
    row1 = [
        InlineKeyboardButton("🙅 None",                callback_data=encode_cb("time_spent", pid=promise_id, value=0.0)),
        InlineKeyboardButton(f"🟢 {beautify_time(curr_h)}",
                                                     callback_data=encode_cb("time_spent", pid=promise_id, value=curr_h)),
        InlineKeyboardButton(f"🏁 {beautify_time(max_h)}",
                                                     callback_data=encode_cb("time_spent", pid=promise_id, value=max_h)),
    ]

    # Row 2 — skip week (use your existing action) + adaptive −X / +2X
    row2 = [
        InlineKeyboardButton("⏭️ Skip (wk)",          callback_data=encode_cb("remind_next_week", pid=promise_id)),
        InlineKeyboardButton(f"-{int(step_min)}m",     callback_data=encode_cb("update_time_spent", pid=promise_id, value=-delta_h,  c=curr_h)),
        InlineKeyboardButton(f"+{int(2*step_min)}m",   callback_data=encode_cb("update_time_spent", pid=promise_id, value= two_delta, c=curr_h)),
    ]

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

def preping_kb(promise_id: str, snooze_min: int = 30):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Start ⏱",     callback_data=encode_cb("preping_start",  pid=promise_id)),
            InlineKeyboardButton(f"Snooze {snooze_min}m", callback_data=encode_cb("preping_snooze", pid=promise_id, m=snooze_min)),
            InlineKeyboardButton("Not today 🙅", callback_data=encode_cb("preping_skip",   pid=promise_id)),
        ],
        # [
        #     InlineKeyboardButton("More…",                  callback_data=encode_cb("open_time",      pid=promise_id)),
        # ],
    ])

def session_running_kb(session_id: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Pause ⏸️",  callback_data=encode_cb("session_pause",  s=session_id)),
            InlineKeyboardButton("Finish ✅", callback_data=encode_cb("session_finish_open", s=session_id)),
        ],
        [
            InlineKeyboardButton("+15m",      callback_data=encode_cb("session_plus",  s=session_id, v=0.25)),
            InlineKeyboardButton("+30m",      callback_data=encode_cb("session_plus",  s=session_id, v=0.50)),
            InlineKeyboardButton("Snooze 10m",callback_data=encode_cb("session_snooze",s=session_id, m=10)),
        ],
    ])

def session_paused_kb(session_id: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Resume ▶️", callback_data=encode_cb("session_resume", s=session_id)),
            InlineKeyboardButton("Finish ✅", callback_data=encode_cb("session_finish_open", s=session_id)),
        ],
        [
            InlineKeyboardButton("Snooze 10m", callback_data=encode_cb("session_snooze", s=session_id, m=10)),
        ],
    ])

def session_finish_confirm_kb(session_id: str, proposed_h: float):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"Looks right ✅ ({beautify_time(proposed_h)})",
                                 callback_data=encode_cb("session_finish_confirm", s=session_id, v=proposed_h)),
            InlineKeyboardButton("Adjust…",    callback_data=encode_cb("session_adjust_open", s=session_id, v=proposed_h)),
        ]
    ])

def session_adjust_kb(session_id: str, base_h: float):
    # e.g., chips: 15m · 30m · 45m · 1h  (+ Custom later)
    chips = [0.25, 0.5, 0.75, 1.0]
    row = [InlineKeyboardButton(beautify_time(h), callback_data=encode_cb("session_adjust_set", s=session_id, v=h)) for h in chips]
    return InlineKeyboardMarkup([row])


def language_selection_kb() -> InlineKeyboardMarkup:
    """Create keyboard for language selection."""
    buttons = [
        [InlineKeyboardButton("English", callback_data=encode_cb("set_language", lang="en"))],
        [InlineKeyboardButton("فارسی (Persian)", callback_data=encode_cb("set_language", lang="fa"))],
        [InlineKeyboardButton("Français (French)", callback_data=encode_cb("set_language", lang="fr"))]
    ]
    return InlineKeyboardMarkup(buttons)


def voice_mode_selection_kb() -> InlineKeyboardMarkup:
    """Create keyboard for voice mode preference selection."""
    buttons = [
        [
            InlineKeyboardButton("✅ Yes, enable voice mode", callback_data=encode_cb("voice_mode", enabled="true")),
        ],
        [
            InlineKeyboardButton("❌ No, text only", callback_data=encode_cb("voice_mode", enabled="false")),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def morning_calendar_kb() -> InlineKeyboardMarkup:
    """Create keyboard for morning calendar question."""
    buttons = [
        [
            InlineKeyboardButton("✅ Yes, add to calendar", callback_data=encode_cb("add_to_calendar_yes")),
            InlineKeyboardButton("❌ No, thanks", callback_data=encode_cb("add_to_calendar_no")),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


