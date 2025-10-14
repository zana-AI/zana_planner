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


def community_kb() -> InlineKeyboardMarkup:
    """Create keyboard for main community menu."""
    buttons = [
        [InlineKeyboardButton("🌟 Browse Ideas", callback_data=encode_cb("browse_ideas"))],
        [InlineKeyboardButton("🏆 Recent Achievements", callback_data=encode_cb("view_achievements"))],
        [InlineKeyboardButton("⚙️ Sharing Settings", callback_data=encode_cb("sharing_settings"))]
    ]
    return InlineKeyboardMarkup(buttons)


def promise_ideas_list_kb(ideas, page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    """Create keyboard for promise ideas list with pagination."""
    buttons = []
    start_idx = page * per_page
    end_idx = start_idx + per_page
    
    for i, idea in enumerate(ideas[start_idx:end_idx], start_idx):
        button_text = f"{i+1}. {idea.text[:30]}{'...' if len(idea.text) > 30 else ''}"
        buttons.append([InlineKeyboardButton(
            button_text, 
            callback_data=encode_cb("adopt_idea", idea_id=idea.id)
        )])
    
    # Pagination buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=encode_cb("ideas_page", page=page-1)))
    if end_idx < len(ideas):
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=encode_cb("ideas_page", page=page+1)))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # Back button
    buttons.append([InlineKeyboardButton("🔙 Back to Community", callback_data=encode_cb("community_menu"))])
    
    return InlineKeyboardMarkup(buttons)


def sharing_prompt_kb(promise_id: str, hours_spent: float) -> InlineKeyboardMarkup:
    """Create keyboard for sharing prompt after time logging."""
    buttons = [
        [
            InlineKeyboardButton("✅ Share Achievement", callback_data=encode_cb("share_achievement", pid=promise_id, hours=hours_spent)),
            InlineKeyboardButton("❌ Not Now", callback_data=encode_cb("skip_sharing"))
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def sharing_settings_kb(share_data: bool) -> InlineKeyboardMarkup:
    """Create keyboard for sharing settings."""
    status_text = "✅ Enabled" if share_data else "❌ Disabled"
    toggle_text = "Disable Sharing" if share_data else "Enable Sharing"
    
    buttons = [
        [InlineKeyboardButton(f"Sharing: {status_text}", callback_data=encode_cb("toggle_sharing"))],
        [InlineKeyboardButton("Set Display Name", callback_data=encode_cb("set_display_name"))],
        [InlineKeyboardButton("🔙 Back to Community", callback_data=encode_cb("community_menu"))]
    ]
    return InlineKeyboardMarkup(buttons)


def category_filter_kb() -> InlineKeyboardMarkup:
    """Create keyboard for filtering promise ideas by category."""
    buttons = [
        [InlineKeyboardButton("All Categories", callback_data=encode_cb("filter_ideas", category="all"))],
        [InlineKeyboardButton("🏃 Health & Fitness", callback_data=encode_cb("filter_ideas", category="health"))],
        [InlineKeyboardButton("📚 Learning", callback_data=encode_cb("filter_ideas", category="learning"))],
        [InlineKeyboardButton("💼 Productivity", callback_data=encode_cb("filter_ideas", category="productivity"))],
        [InlineKeyboardButton("🎨 Hobbies", callback_data=encode_cb("filter_ideas", category="hobbies"))],
        [InlineKeyboardButton("🧘 Wellness", callback_data=encode_cb("filter_ideas", category="wellness"))],
        [InlineKeyboardButton("👨‍👩‍👧‍👦 Relationships", callback_data=encode_cb("filter_ideas", category="relationships"))],
        [InlineKeyboardButton("🔙 Back", callback_data=encode_cb("browse_ideas"))]
    ]
    return InlineKeyboardMarkup(buttons)


