"""
Platform-agnostic data types for bot communication.

These types abstract away platform-specific details (Telegram, Discord, etc.)
and provide a common interface for the core business logic.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class MessageType(Enum):
    """Type of message."""
    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"
    LOCATION = "location"
    POLL = "poll"
    COMMAND = "command"


@dataclass
class KeyboardButton:
    """Platform-agnostic keyboard button representation."""
    text: str
    callback_data: Optional[str] = None
    url: Optional[str] = None
    
    def __post_init__(self):
        """Validate button configuration."""
        if not self.callback_data and not self.url:
            raise ValueError("Button must have either callback_data or url")
        if self.callback_data and self.url:
            raise ValueError("Button cannot have both callback_data and url")


@dataclass
class Keyboard:
    """Platform-agnostic keyboard representation."""
    buttons: List[List[KeyboardButton]] = field(default_factory=list)
    
    def add_row(self, *buttons: KeyboardButton) -> None:
        """Add a row of buttons to the keyboard."""
        self.buttons.append(list(buttons))
    
    def add_button(self, button: KeyboardButton, row: int = -1) -> None:
        """Add a button to a specific row (default: last row)."""
        if row == -1:
            if not self.buttons:
                self.buttons.append([])
            self.buttons[-1].append(button)
        else:
            while len(self.buttons) <= row:
                self.buttons.append([])
            self.buttons[row].append(button)


@dataclass
class MediaFile:
    """Platform-agnostic media file representation."""
    file_path: Optional[str] = None
    file_id: Optional[str] = None
    file_url: Optional[str] = None
    file_bytes: Optional[bytes] = None
    mime_type: Optional[str] = None
    
    def __post_init__(self):
        """Validate that at least one file source is provided."""
        if not any([self.file_path, self.file_id, self.file_url, self.file_bytes]):
            raise ValueError("MediaFile must have at least one file source")


@dataclass
class UserMessage:
    """Platform-agnostic user message representation."""
    user_id: int
    chat_id: int
    text: Optional[str] = None
    message_type: MessageType = MessageType.TEXT
    message_id: Optional[int] = None
    timestamp: Optional[datetime] = None
    media: Optional[MediaFile] = None
    location: Optional[Dict[str, float]] = None  # {"latitude": float, "longitude": float}
    metadata: Dict[str, Any] = field(default_factory=dict)  # Platform-specific data
    
    def __post_init__(self):
        """Set default timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class BotResponse:
    """Platform-agnostic bot response representation."""
    text: Optional[str] = None
    keyboard: Optional[Keyboard] = None
    photo: Optional[MediaFile] = None
    voice: Optional[MediaFile] = None
    parse_mode: Optional[str] = None  # "Markdown", "HTML", etc.
    disable_web_page_preview: bool = False
    reply_to_message_id: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)  # Platform-specific data
    
    def __post_init__(self):
        """Validate that at least one response type is provided."""
        if not any([self.text, self.photo, self.voice]):
            raise ValueError("BotResponse must have at least text, photo, or voice")


@dataclass
class CallbackQuery:
    """Platform-agnostic callback query representation."""
    user_id: int
    chat_id: int
    message_id: int
    data: str  # Callback data string
    query_id: Optional[str] = None  # Platform-specific query ID
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)  # Platform-specific data
    
    def __post_init__(self):
        """Set default timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class JobContext:
    """Platform-agnostic job context for scheduled tasks."""
    job_name: str
    user_id: Optional[int] = None
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)  # Platform-specific data

