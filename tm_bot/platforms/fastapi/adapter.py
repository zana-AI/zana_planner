"""
FastAPI platform adapter implementation.

This adapter enables the bot to work through FastAPI endpoints,
making it suitable for Telegram Mini Apps and other web integrations.
"""

from typing import Callable, Optional, Dict, Any
from fastapi import FastAPI

from ..interfaces import (
    IPlatformAdapter,
    IResponseService,
    IJobScheduler,
    IKeyboardBuilder,
    IMessageHandler,
    ICallbackHandler,
)
from .response_service import FastAPIResponseService
from .scheduler import FastAPIJobScheduler
from ..telegram.keyboard_adapter import TelegramKeyboardAdapter
from utils.logger import get_logger

logger = get_logger(__name__)


class FastAPIPlatformAdapter(IPlatformAdapter):
    """
    FastAPI implementation of IPlatformAdapter.
    
    This adapter allows the bot to work through HTTP/WebSocket APIs,
    suitable for Telegram Mini Apps and web integrations.
    """
    
    def __init__(self, app: Optional[FastAPI] = None):
        """
        Initialize FastAPI platform adapter.
        
        Args:
            app: Optional FastAPI app instance. If not provided, will be created.
        """
        self._app = app
        self._response_service = FastAPIResponseService()
        self._job_scheduler = FastAPIJobScheduler()
        self._keyboard_builder = TelegramKeyboardAdapter()  # Reuse Telegram keyboard format
        
        # Store handlers
        self._message_handlers: Dict[str, IMessageHandler] = {}
        self._callback_handlers: Dict[str, ICallbackHandler] = {}
        self._command_handlers: Dict[str, Callable] = {}
    
    @property
    def app(self) -> Optional[FastAPI]:
        """Get the FastAPI app instance."""
        return self._app
    
    @app.setter
    def app(self, app: FastAPI) -> None:
        """Set the FastAPI app instance."""
        self._app = app
    
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
        logger.info("Message handler registered for FastAPI")
    
    def register_callback_handler(self, handler: ICallbackHandler) -> None:
        """Register a callback handler."""
        self._callback_handlers["default"] = handler
        logger.info("Callback handler registered for FastAPI")
    
    def register_command_handler(self, command: str, handler: Callable) -> None:
        """Register a command handler."""
        self._command_handlers[command] = handler
        logger.info(f"Command handler registered for /{command}")
    
    async def start(self) -> None:
        """Start the platform bot."""
        logger.info("FastAPI platform adapter started")
        # FastAPI app is started separately via uvicorn
    
    async def stop(self) -> None:
        """Stop the platform bot."""
        logger.info("FastAPI platform adapter stopped")
    
    def get_user_info(self, user_id: int) -> dict:
        """Get user information."""
        # This would typically fetch from database
        return {
            "user_id": user_id,
            "platform": "fastapi"
        }


