"""
Mock platform adapter for unit testing.

This adapter simulates a platform without requiring actual connections,
allowing tests to run quickly and deterministically.
"""

from typing import Callable, Optional, Dict, Any
from datetime import datetime

from ..interfaces import (
    IPlatformAdapter,
    IResponseService,
    IJobScheduler,
    IKeyboardBuilder,
    IMessageHandler,
    ICallbackHandler,
)
from .test_response_service import TestResponseService
from .mock_scheduler import MockJobScheduler
from ..telegram.keyboard_adapter import TelegramKeyboardAdapter
from utils.logger import get_logger

logger = get_logger(__name__)


class MockPlatformAdapter(IPlatformAdapter):
    """Mock implementation of IPlatformAdapter for testing."""
    
    def __init__(self):
        """Initialize mock platform adapter."""
        self._response_service = TestResponseService()
        self._job_scheduler = MockJobScheduler()
        self._keyboard_builder = TelegramKeyboardAdapter()  # Can use Telegram adapter for keyboard conversion
        
        # Store handlers
        self._message_handlers: Dict[str, IMessageHandler] = {}
        self._callback_handlers: Dict[str, ICallbackHandler] = {}
        self._command_handlers: Dict[str, Callable] = {}
        
        # Mock user data
        self._users: Dict[int, Dict[str, Any]] = {}
    
    @property
    def response_service(self) -> IResponseService:
        """Get the response service for this platform."""
        return self._response_service
    
    @property
    def job_scheduler(self) -> IJobScheduler:
        """Get the job scheduler for this platform."""
        return self._job_scheduler
    
    @property
    def keyboard_builder(self) -> IKeyboardBuilder:
        """Get the keyboard builder for this platform."""
        return self._keyboard_builder
    
    def register_message_handler(self, handler: IMessageHandler) -> None:
        """Register a message handler."""
        self._message_handlers["default"] = handler
        logger.debug("Mock: Message handler registered")
    
    def register_callback_handler(self, handler: ICallbackHandler) -> None:
        """Register a callback handler."""
        self._callback_handlers["default"] = handler
        logger.debug("Mock: Callback handler registered")
    
    def register_command_handler(self, command: str, handler: Callable) -> None:
        """Register a command handler."""
        self._command_handlers[command] = handler
        logger.debug(f"Mock: Command handler registered for /{command}")
    
    async def start(self) -> None:
        """Start the platform bot (mock - no-op)."""
        logger.info("Mock platform adapter started")
    
    async def stop(self) -> None:
        """Stop the platform bot (mock - no-op)."""
        logger.info("Mock platform adapter stopped")
    
    def get_user_info(self, user_id: int) -> dict:
        """Get user information (mock)."""
        if user_id not in self._users:
            self._users[user_id] = {
                "user_id": user_id,
                "username": f"user_{user_id}",
                "first_name": f"User {user_id}",
                "platform": "mock"
            }
        return self._users[user_id]
    
    def set_user_info(self, user_id: int, info: Dict[str, Any]) -> None:
        """Set user information (for testing)."""
        self._users[user_id] = {**self._users.get(user_id, {}), **info}
    
    # Test helper methods
    def simulate_message(self, user_id: int, text: str, chat_id: Optional[int] = None) -> None:
        """Simulate receiving a message (for testing)."""
        from ..types import UserMessage, MessageType
        
        message = UserMessage(
            user_id=user_id,
            chat_id=chat_id or user_id,
            text=text,
            message_type=MessageType.TEXT,
            timestamp=datetime.now()
        )
        
        # Process through registered handlers
        if self._message_handlers:
            handler = list(self._message_handlers.values())[0]
            # This would need to be async, so we'll handle it in test code
            logger.debug(f"Mock: Simulated message from user {user_id}: {text}")

