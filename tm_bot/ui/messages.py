from typing import List
from datetime import datetime

from models.models import Promise, Session
from utils.time_utils import beautify_time


def nightly_card_text(user_id: int, promises: List[Promise], now: datetime) -> str:
    """Generate text for nightly reminder card."""
    if not promises:
        return "No active promises to remind you about today."
    
    text = "🌙 *Nightly Reminders*\n\n"
    for i, promise in enumerate(promises, 1):
        text += f"{i}. *{promise.text.replace('_', ' ')}*\n"
        text += f"   Target: {promise.hours_per_week:.1f}h/week\n\n"
    
    text += "How much time did you spend today on these promises?"
    return text


def session_status_text(session: Session, elapsed_str: str) -> str:
    """Generate text for session status display."""
    status_emoji = {
        'running': '▶️',
        'paused': '⏸️',
        'finished': '✅',
        'aborted': '❌'
    }
    
    emoji = status_emoji.get(session.status, '❓')
    text = f"{emoji} *Session #{session.session_id}*\n"
    text += f"Promise: {session.promise_id}\n"
    text += f"Status: {session.status.title()}\n"
    text += f"Elapsed: {elapsed_str}\n"
    
    if session.paused_seconds_total > 0:
        paused_hours = session.paused_seconds_total / 3600
        text += f"Paused: {beautify_time(paused_hours)}\n"
    
    return text


def weekly_report_text(summary: dict) -> str:
    """Generate text for weekly report."""
    if not summary:
        return "No data available for this week."
    
    text = "📊 *Weekly Report*\n\n"
    
    for promise_id, data in summary.items():
        hours_promised = data['hours_promised']
        hours_spent = data['hours_spent']
        progress = min(100, int((hours_spent / hours_promised) * 100)) if hours_promised > 0 else 0
        
        # Progress bar
        bar_width = 10
        filled_length = (progress * bar_width) // 100
        empty_length = bar_width - filled_length
        progress_bar = f"{'█' * filled_length}{'_' * empty_length}"
        
        # Status emoji
        if progress < 30:
            emoji = "🔴"
        elif progress < 60:
            emoji = "🟠"
        elif progress < 90:
            emoji = "🟡"
        else:
            emoji = "✅"
        
        text += f"{emoji} #{promise_id} *{data['text'][:36].replace('_', ' ')}*:\n"
        text += f" └── `[{progress_bar}] {progress:2d}%` ({hours_spent:.1f}/{hours_promised:.1f} h)\n\n"
    
    return text


def promise_report_text(promise: Promise, weekly_hours: float, total_hours: float, streak: int) -> str:
    """Generate text for individual promise report."""
    progress = min(100, int((weekly_hours / promise.hours_per_week) * 100)) if promise.hours_per_week > 0 else 0
    
    if streak < 0:
        streak_str = f"{-streak} days since last action"
    elif streak == 0:
        streak_str = "🆕 No actions yet"
    else:
        streak_str = f"🔥 {streak} day{'s' if streak > 1 else ''} in a row"
    
    text = f"**Report #{promise.id}**\n"
    text += f"*{promise.text.replace('_', ' ')}*\n"
    text += f"**You promised:** {promise.hours_per_week:.1f} hours/week\n"
    text += f"**This week:** {weekly_hours:.1f}/{promise.hours_per_week:.1f} hours "
    text += f"**Total {total_hours:.1f} hours spent** since {promise.start_date}\n"
    text += f"({progress}%)\n"
    text += f"**Streak:** {streak_str}"
    
    return text
