from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


@dataclass
class Promise:
    user_id: str
    id: str
    text: str
    hours_per_week: float
    recurring: bool = True
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    # Optional viz fields (keep if already present in CSVs)
    angle_deg: int = 0
    radius: Optional[int] = 0
    visibility: str = "private"  # 'private' | 'followers' | 'clubs' | 'public'
    description: Optional[str] = None  # Additional description/content (URLs, notes, etc.)
    parent_id: Optional[str] = None  # ID of parent promise (for subtasks)
    # Future: pinned/focus flags, tags

    def is_check_based(self) -> bool:
        """
        Check if this promise is check-based (habit) rather than time-based.
        Convention: hours_per_week <= 0 indicates a check-based promise.
        """
        return self.hours_per_week <= 0.0

    def is_time_based(self) -> bool:
        """
        Check if this promise is time-based (requires hours tracking).
        Convention: hours_per_week > 0 indicates a time-based promise.
        """
        return self.hours_per_week > 0.0

    def promise_type(self) -> str:
        """
        Get the promise type as a string: 'check_based' or 'time_based'.
        """
        return "check_based" if self.is_check_based() else "time_based"


@dataclass
class Action:
    user_id: str
    promise_id: str
    action: str           # e.g., "log_time", "skip", "delete", etc.
    time_spent: float     # hours (can be 0 for skip/delete)
    at: datetime          # action timestamp


@dataclass
class UserSettings:
    user_id: str
    timezone: str = "DEFAULT"
    nightly_hh: int = 22
    nightly_mm: int = 0
    language: str = "en"  # "en", "fa", "fr"
    voice_mode: Optional[str] = None  # None (NOTSET), "enabled", "disabled"
    first_name: Optional[str] = None
    username: Optional[str] = None
    last_seen: Optional[datetime] = None


@dataclass
class Session:
    session_id: str
    user_id: str
    promise_id: str
    status: str              # "running" | "paused" | "finished" | "aborted"
    started_at: datetime
    ended_at: Optional[datetime] = None
    paused_seconds_total: int = 0
    last_state_change_at: Optional[datetime] = None
    message_id: Optional[int] = None
    chat_id: Optional[int] = None


@dataclass
class Broadcast:
    broadcast_id: str
    admin_id: str
    message: str
    target_user_ids: list[int]  # List of user IDs as integers
    scheduled_time_utc: datetime
    status: str = "pending"  # "pending" | "completed" | "cancelled"
    bot_token_id: Optional[str] = None  # ID of the bot token to use for this broadcast
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class AuthSession:
    """Authentication session for browser-based login (distinct from work Session)."""
    session_token: str  # Unique token (UUID)
    user_id: int
    created_at: datetime
    expires_at: datetime
    telegram_auth_date: int  # Original auth_date from Telegram
