"""
Platform abstraction layer for multi-platform bot support.

This module provides interfaces and types that allow the bot to work
with different platforms (Telegram, Discord, CLI, etc.) without
platform-specific code in the core business logic.
"""

from .types import (
    UserMessage,
    BotResponse,
    CallbackQuery,
    Keyboard,
    KeyboardButton,
    MediaFile,
    JobContext,
)
from .interfaces import (
    IPlatformAdapter,
    IResponseService,
    IJobScheduler,
    IKeyboardBuilder,
    IMessageHandler,
    ICallbackHandler,
)

__all__ = [
    "UserMessage",
    "BotResponse",
    "CallbackQuery",
    "Keyboard",
    "KeyboardButton",
    "MediaFile",
    "JobContext",
    "IPlatformAdapter",
    "IResponseService",
    "IJobScheduler",
    "IKeyboardBuilder",
    "IMessageHandler",
    "ICallbackHandler",
]

