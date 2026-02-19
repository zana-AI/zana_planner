"""
Platform-agnostic types for the central router/dispatcher.
Used by PlannerBot.dispatch() to normalize all incoming inputs before routing.
"""
from dataclasses import dataclass, field
from typing import Any, Optional

from handlers.messages_store import Language


@dataclass
class InputContext:
    """
    Platform-agnostic envelope for every incoming event.
    Built from Telegram Update, FastAPI request, or CLI input before routing.
    """
    user_id: int
    chat_id: int
    input_type: str  # "command", "text", "voice", "image", "callback", "location", "poll"
    raw_text: Optional[str] = None  # original or transcribed text
    command: Optional[str] = None  # e.g. "start", "weekly", None for non-commands
    command_args: list = field(default_factory=list)
    language: Optional[Language] = None
    platform_update: Any = None  # original Telegram Update / FastAPI request
    platform_context: Any = None  # original CallbackContext / None
    voice_file_path: Optional[str] = None
    image_file_path: Optional[str] = None
    callback_data: Optional[str] = None
    metadata: dict = field(default_factory=dict)  # extensible (location coords, poll data, etc.)
    message_id: Optional[int] = None  # for conversation logging
