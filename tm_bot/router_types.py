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
    input_type: str  # "command"|"text"|"voice"|"image"|"callback"|"location"|"poll"|"poll_answer"|"edited_message"|"reaction"|"pinned_message"|"chat_member"
    raw_text: Optional[str] = None
    command: Optional[str] = None
    command_args: list = field(default_factory=list)
    language: Optional[Language] = None
    platform_update: Any = None
    platform_context: Any = None
    callback_data: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    message_id: Optional[int] = None
    processing_msg: Optional[Any] = None  # "Thinking..." message handle
