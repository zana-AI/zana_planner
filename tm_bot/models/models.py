from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional


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
    share_data: bool = False
    display_name: str = "Anonymous"  # for sharing


@dataclass
class PromiseIdea:
    id: str
    text: str
    category: str
    popularity: int  # number of users who adopted it
    avg_hours_per_week: float
    created_at: datetime


@dataclass
class SharedAchievement:
    id: str
    username: str  # can be "Anonymous" or real username
    promise_text: str
    hours_spent: float
    period: str  # "this week", "today", etc
    shared_at: datetime


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
