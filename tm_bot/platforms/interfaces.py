"""
Abstract interfaces for platform abstraction.

These interfaces define the contract that platform implementations
must follow, allowing the core business logic to be platform-independent.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Callable, Any
from datetime import datetime, time

from .types import (
    UserMessage,
    BotResponse,
    CallbackQuery,
    Keyboard,
    JobContext,
)


class IResponseService(ABC):
    """Abstract interface for sending responses to users."""
    
    @abstractmethod
    async def send_text(
        self,
        user_id: int,
        chat_id: int,
        text: str,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        disable_web_page_preview: bool = False,
    ) -> Optional[Any]:
        """Send a text message to the user."""
        pass
    
    @abstractmethod
    async def send_photo(
        self,
        user_id: int,
        chat_id: int,
        photo: Any,  # Platform-specific photo type
        caption: Optional[str] = None,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None,
    ) -> Optional[Any]:
        """Send a photo to the user."""
        pass
    
    @abstractmethod
    async def send_voice(
        self,
        user_id: int,
        chat_id: int,
        voice: Any,  # Platform-specific voice type
    ) -> Optional[Any]:
        """Send a voice message to the user."""
        pass
    
    @abstractmethod
    async def edit_message(
        self,
        user_id: int,
        chat_id: int,
        message_id: int,
        text: str,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None,
    ) -> Optional[Any]:
        """Edit an existing message."""
        pass
    
    @abstractmethod
    async def delete_message(
        self,
        chat_id: int,
        message_id: int,
    ) -> bool:
        """Delete a message."""
        pass
    
    @abstractmethod
    def log_user_message(
        self,
        user_id: int,
        content: str,
        message_id: Optional[int] = None,
        chat_id: Optional[int] = None,
    ) -> None:
        """Log a user message for conversation history."""
        pass


class IJobScheduler(ABC):
    """Abstract interface for scheduling jobs/tasks."""
    
    @abstractmethod
    def schedule_daily(
        self,
        user_id: int,
        tz: str,
        callback: Callable,
        hh: int = 22,
        mm: int = 0,
        name_prefix: str = "job",
    ) -> None:
        """Schedule a daily recurring job for a user."""
        pass
    
    @abstractmethod
    def schedule_once(
        self,
        name: str,
        callback: Callable,
        when_dt: datetime,
        data: Optional[dict] = None,
    ) -> None:
        """Schedule a one-time job."""
        pass
    
    @abstractmethod
    def schedule_repeating(
        self,
        name: str,
        callback: Callable,
        seconds: int,
        data: Optional[dict] = None,
    ) -> None:
        """Schedule a repeating job."""
        pass
    
    @abstractmethod
    def cancel_job(self, name: str) -> None:
        """Cancel a job by name."""
        pass


class IKeyboardBuilder(ABC):
    """Abstract interface for building keyboards."""
    
    @abstractmethod
    def build_keyboard(self, keyboard: Keyboard) -> Any:
        """Convert a platform-agnostic Keyboard to platform-specific format."""
        pass


class IMessageHandler(ABC):
    """Abstract interface for message handlers."""
    
    @abstractmethod
    async def handle_message(self, message: UserMessage) -> BotResponse:
        """Handle a user message and return a response."""
        pass
    
    @abstractmethod
    async def handle_command(self, message: UserMessage, command: str, args: List[str]) -> BotResponse:
        """Handle a command message."""
        pass


class ICallbackHandler(ABC):
    """Abstract interface for callback handlers."""
    
    @abstractmethod
    async def handle_callback(self, query: CallbackQuery) -> Optional[BotResponse]:
        """Handle a callback query and optionally return a response."""
        pass


class IPlatformAdapter(ABC):
    """Main platform adapter interface."""
    
    @property
    @abstractmethod
    def response_service(self) -> IResponseService:
        """Get the response service for this platform."""
        pass
    
    @property
    @abstractmethod
    def job_scheduler(self) -> IJobScheduler:
        """Get the job scheduler for this platform."""
        pass
    
    @property
    @abstractmethod
    def keyboard_builder(self) -> IKeyboardBuilder:
        """Get the keyboard builder for this platform."""
        pass
    
    @abstractmethod
    def register_message_handler(self, handler: IMessageHandler) -> None:
        """Register a message handler."""
        pass
    
    @abstractmethod
    def register_callback_handler(self, handler: ICallbackHandler) -> None:
        """Register a callback handler."""
        pass
    
    @abstractmethod
    def register_command_handler(self, command: str, handler: Callable) -> None:
        """Register a command handler."""
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """Start the platform bot."""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the platform bot."""
        pass
    
    @abstractmethod
    def get_user_info(self, user_id: int) -> dict:
        """Get user information (name, username, etc.)."""
        pass

