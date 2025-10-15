from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict


@dataclass
class Promise:
    id: str
    text: str
    hours_per_week: float
    recurring: bool = False
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    # Optional viz fields (keep if already present in CSVs)
    angle_deg: int = 0
    radius: Optional[int] = 0
    # Future: pinned/focus flags, tags


@dataclass
class Action:
    user_id: int
    promise_id: str
    action: str           # e.g., "log_time", "skip", "delete", etc.
    time_spent: float     # hours (can be 0 for skip/delete)
    at: datetime          # action timestamp


@dataclass
class UserSettings:
    user_id: int
    timezone: str = "Europe/Paris"
    nightly_hh: int = 22
    nightly_mm: int = 0
    language: str = "en"  # "en", "fa", "fr"
    # List of groups the user interacts in; each entry: {id: int, title: str|None, last_seen: ISO8601 str}
    groups: List[Dict] = field(default_factory=list)


@dataclass
class Session:
    session_id: str
    user_id: int
    promise_id: str
    status: str              # "running" | "paused" | "finished" | "aborted"
    started_at: datetime
    ended_at: Optional[datetime] = None
    paused_seconds_total: int = 0
    last_state_change_at: Optional[datetime] = None
    message_id: Optional[int] = None
    chat_id: Optional[int] = None
