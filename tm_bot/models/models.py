from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


@dataclass
class Promise:
    user_id: str
    id: str
    text: str
    hours_per_week: float
    recurring: bool = False
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    # Optional viz fields (keep if already present in CSVs)
    angle_deg: int = 0
    radius: Optional[int] = 0
    visibility: str = "private"  # 'private' | 'followers' | 'clubs' | 'public'
    # Future: pinned/focus flags, tags


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
    timezone: str = "Europe/Paris"
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
