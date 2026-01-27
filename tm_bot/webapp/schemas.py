"""
Pydantic models for API request/response schemas.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel


# Weekly Report
class WeeklyReportResponse(BaseModel):
    """Response model for weekly report endpoint."""
    week_start: str
    week_end: str
    total_promised: float
    total_spent: float
    promises: Dict[str, Any]


# User Info
class UserInfoResponse(BaseModel):
    """Response model for user info endpoint."""
    user_id: int
    timezone: str
    language: str
    first_name: Optional[str] = None


class TimezoneUpdateRequest(BaseModel):
    """Request model for timezone update."""
    tz: str  # IANA timezone name (e.g., "America/New_York")
    offset_min: Optional[int] = None  # UTC offset in minutes (optional, for fallback)
    force: Optional[bool] = False  # If True, update timezone even if already set


# Public Users
class PublicUser(BaseModel):
    """Public user information for community page."""
    user_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None
    username: Optional[str] = None
    avatar_path: Optional[str] = None
    avatar_file_unique_id: Optional[str] = None
    activity_count: int = 0
    promise_count: int = 0
    last_seen_utc: Optional[str] = None


class PublicUsersResponse(BaseModel):
    """Response model for public users endpoint."""
    users: List[PublicUser]
    total: int


class PublicPromiseBadge(BaseModel):
    """Public promise badge with stats."""
    promise_id: str
    text: str
    hours_promised: float
    hours_spent: float
    weekly_hours: float
    streak: int
    progress_percentage: float
    metric_type: str = "hours"  # Default to hours for now
    target_value: float = 0.0
    achieved_value: float = 0.0


# Auth
class TelegramLoginRequest(BaseModel):
    """Request model for Telegram Login Widget authentication."""
    auth_data: Dict[str, Any]


class TelegramLoginResponse(BaseModel):
    """Response model for Telegram login."""
    session_token: str
    user_id: int
    expires_at: str


# Suggestions
class CreateSuggestionRequest(BaseModel):
    to_user_id: str
    template_id: Optional[str] = None
    freeform_text: Optional[str] = None
    message: Optional[str] = None


# Promises
class UpdateVisibilityRequest(BaseModel):
    visibility: str  # "private" or "public"


class UpdateRecurringRequest(BaseModel):
    recurring: bool


class UpdatePromiseRequest(BaseModel):
    text: Optional[str] = None
    hours_per_week: Optional[float] = None
    end_date: Optional[str] = None  # ISO date string (YYYY-MM-DD)


class LogActionRequest(BaseModel):
    promise_id: str
    time_spent: float
    action_datetime: Optional[str] = None  # ISO format datetime string
    notes: Optional[str] = None  # Optional notes for this action


class ScheduleSlotRequest(BaseModel):
    weekday: int  # 0-6
    start_local_time: str  # HH:MM:SS or HH:MM
    end_local_time: Optional[str] = None
    tz: Optional[str] = None
    start_date: Optional[str] = None  # ISO date
    end_date: Optional[str] = None  # ISO date


class UpdateScheduleRequest(BaseModel):
    slots: List[ScheduleSlotRequest]


class ReminderRequest(BaseModel):
    kind: str  # "slot_offset" or "fixed_time"
    slot_id: Optional[str] = None  # Required for slot_offset
    offset_minutes: Optional[int] = None  # For slot_offset
    weekday: Optional[int] = None  # For fixed_time (0-6)
    time_local: Optional[str] = None  # For fixed_time (HH:MM:SS or HH:MM)
    tz: Optional[str] = None
    enabled: Optional[bool] = True


class UpdateRemindersRequest(BaseModel):
    reminders: List[ReminderRequest]


class CheckinRequest(BaseModel):
    action_datetime: Optional[str] = None  # ISO datetime string


class WeeklyNoteRequest(BaseModel):
    week_start: str  # ISO date string
    note: Optional[str] = None


# Templates
class SubscribeTemplateRequest(BaseModel):
    start_date: Optional[str] = None  # ISO date string
    target_date: Optional[str] = None  # ISO date string
    target_value: Optional[float] = None  # Override template's target_value


# Distractions
class LogDistractionRequest(BaseModel):
    category: str
    minutes: float
    at_utc: Optional[str] = None  # ISO datetime string


# Admin
class AdminUser(BaseModel):
    """Admin user information."""
    user_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    last_seen_utc: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    promise_count: Optional[int] = None
    activity_count: Optional[int] = None


class AdminUsersResponse(BaseModel):
    """Response model for admin users endpoint."""
    users: List[AdminUser]
    total: int


class CreateBroadcastRequest(BaseModel):
    """Request model for creating a broadcast."""
    message: str
    target_user_ids: List[int]
    scheduled_time_utc: Optional[str] = None  # ISO format datetime string, None for immediate
    bot_token_id: Optional[str] = None  # Optional bot token ID to use for this broadcast


class UpdateBroadcastRequest(BaseModel):
    """Request model for updating a broadcast."""
    message: Optional[str] = None
    target_user_ids: Optional[List[int]] = None
    scheduled_time_utc: Optional[str] = None  # ISO format datetime string


class BroadcastResponse(BaseModel):
    """Response model for broadcast."""
    broadcast_id: str
    admin_id: str
    message: str
    target_user_ids: List[int]
    scheduled_time_utc: str
    status: str
    bot_token_id: Optional[str] = None
    created_at: str
    updated_at: str


class BotTokenResponse(BaseModel):
    """Response model for bot token."""
    bot_token_id: str
    bot_username: Optional[str] = None
    is_active: bool
    description: Optional[str] = None
    created_at_utc: str
    updated_at_utc: str


class ConversationMessage(BaseModel):
    """Response model for a conversation message."""
    id: int
    user_id: str
    chat_id: Optional[str] = None
    message_id: Optional[int] = None
    message_type: str  # 'user' or 'bot'
    content: str
    created_at_utc: str


class ConversationResponse(BaseModel):
    """Response model for conversation history."""
    messages: List[ConversationMessage]


class GenerateTemplateRequest(BaseModel):
    prompt: str


class DayReminder(BaseModel):
    weekday: int  # 0-6 (Monday-Sunday)
    time: str  # HH:MM format
    enabled: bool = True


class CreatePromiseForUserRequest(BaseModel):
    target_user_id: int
    text: str
    hours_per_week: float
    recurring: bool = True
    start_date: Optional[str] = None  # ISO date string (YYYY-MM-DD)
    end_date: Optional[str] = None  # ISO date string (YYYY-MM-DD)
    visibility: str = "private"  # 'private' | 'followers' | 'clubs' | 'public'
    description: Optional[str] = None
    reminders: Optional[List[DayReminder]] = None
