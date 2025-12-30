"""
Telegram platform adapter.

This is the main adapter that implements IPlatformAdapter for Telegram,
connecting the platform-agnostic bot logic with Telegram-specific implementation.
"""

from typing import Callable, Optional, Dict, Any
from telegram import Update, Bot
from telegram.ext import Application, CallbackContext, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from ..interfaces import (
    IPlatformAdapter,
    IResponseService,
    IJobScheduler,
    IKeyboardBuilder,
    IMessageHandler,
    ICallbackHandler,
)
from .response_service import TelegramResponseService
from .scheduler import TelegramJobScheduler
from .keyboard_adapter import TelegramKeyboardAdapter
from .type_converters import telegram_update_to_user_message, telegram_callback_to_callback_query
from services.response_service import ResponseService as OriginalResponseService
from utils.logger import get_logger

logger = get_logger(__name__)


class TelegramPlatformAdapter(IPlatformAdapter):
    """Telegram implementation of IPlatformAdapter."""
    
    def __init__(self, application: Application, original_response_service: OriginalResponseService):
        """
        Initialize Telegram platform adapter.
        
        Args:
            application: Telegram Application instance
            original_response_service: Original ResponseService for backward compatibility
        """
        self._application = application
        self._bot = application.bot
        
        # Initialize platform services
        self._response_service = TelegramResponseService(original_response_service, self._bot)
        self._response_service.set_bot(self._bot)
        
        self._job_scheduler = TelegramJobScheduler(application.job_queue)
        self._keyboard_builder = TelegramKeyboardAdapter()
        
        # Store handlers
        self._message_handlers: Dict[str, Callable] = {}
        self._callback_handlers: Dict[str, Callable] = {}
        self._command_handlers: Dict[str, Callable] = {}
    
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
    
    @property
    def application(self) -> Application:
        """Get the Telegram Application (for backward compatibility)."""
        return self._application
    
    def register_message_handler(self, handler: IMessageHandler) -> None:
        """Register a message handler."""
        # For now, we'll store it and let the bot class register it with Telegram
        # In Phase 6, we'll fully integrate this
        logger.info("Message handler registered (integration in Phase 6)")
    
    def register_callback_handler(self, handler: ICallbackHandler) -> None:
        """Register a callback handler."""
        # For now, we'll store it and let the bot class register it with Telegram
        logger.info("Callback handler registered (integration in Phase 6)")
    
    def register_command_handler(self, command: str, handler: Callable) -> None:
        """Register a command handler."""
        # Store handler for later registration
        self._command_handlers[command] = handler
        # Register with Telegram Application
        self._application.add_handler(CommandHandler(command, handler))
    
    async def start(self) -> None:
        """Start the platform bot."""
        await self._application.initialize()
        await self._application.start()
        await self._application.updater.start_polling()
        logger.info("Telegram bot started")
    
    async def stop(self) -> None:
        """Stop the platform bot."""
        await self._application.updater.stop()
        await self._application.stop()
        await self._application.shutdown()
        logger.info("Telegram bot stopped")
    
    def get_user_info(self, user_id: int) -> dict:
        """Get user information (name, username, etc.)."""
        # This would require async bot.get_chat() call
        # For now, return minimal info
        return {
            "user_id": user_id,
            "platform": "telegram"
        }
    
    def convert_update_to_user_message(self, update: Update) -> 'UserMessage':
        """Convert Telegram Update to platform-agnostic UserMessage."""
        return telegram_update_to_user_message(update)
    
    def convert_callback_to_query(self, update: Update, context: Optional[CallbackContext] = None) -> 'CallbackQuery':
        """Convert Telegram callback query to platform-agnostic CallbackQuery."""
        return telegram_callback_to_callback_query(update, context)

