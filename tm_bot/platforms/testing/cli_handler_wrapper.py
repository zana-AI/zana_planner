"""
CLI handler wrapper to connect CLI adapter with existing Telegram handlers.

This wrapper adapts the existing MessageHandlers and CallbackHandlers
to work with CLI input by creating mock Update and CallbackContext objects.
"""

from typing import Optional, Dict, Any
from datetime import datetime
from unittest.mock import Mock

from telegram import Update, Message, User, Chat
from telegram.ext import CallbackContext

from platforms.types import UserMessage, CallbackQuery
from handlers.message_handlers import MessageHandlers
from handlers.callback_handlers import CallbackHandlers
from utils.logger import get_logger

logger = get_logger(__name__)


class CLIHandlerWrapper:
    """Wrapper to adapt CLI input to Telegram handler format."""
    
    def __init__(self, message_handlers: MessageHandlers, callback_handlers: CallbackHandlers):
        """Initialize CLI handler wrapper."""
        self.message_handlers = message_handlers
        self.callback_handlers = callback_handlers
        self._user_data: Dict[int, Dict[str, Any]] = {}  # Store user_data per user
    
    def _create_mock_update(self, user_message: UserMessage) -> Update:
        """Create a mock Telegram Update from platform-agnostic UserMessage."""
        # Create mock user
        mock_user = Mock(spec=User)
        mock_user.id = user_message.user_id
        mock_user.first_name = f"User {user_message.user_id}"
        mock_user.username = f"user_{user_message.user_id}"
        mock_user.language_code = "en"
        mock_user.is_bot = False
        
        # Create mock chat
        mock_chat = Mock(spec=Chat)
        mock_chat.id = user_message.chat_id
        mock_chat.type = "private"
        
        # Create mock message
        mock_message = Mock(spec=Message)
        mock_message.message_id = user_message.message_id or 1
        mock_message.text = user_message.text
        mock_message.date = user_message.timestamp or datetime.now()
        mock_message.chat = mock_chat
        mock_message.from_user = mock_user
        
        # Create mock update
        mock_update = Mock(spec=Update)
        mock_update.effective_user = mock_user
        mock_update.effective_chat = mock_chat
        mock_update.effective_message = mock_message
        mock_update.message = mock_message
        
        return mock_update
    
    def _create_mock_context(self, user_id: int) -> CallbackContext:
        """Create a mock CallbackContext."""
        mock_context = Mock(spec=CallbackContext)
        mock_context.user_data = self._user_data.get(user_id, {})
        mock_context.job = None
        mock_context.job_queue = None
        
        # Store reference so we can update it
        if user_id not in self._user_data:
            self._user_data[user_id] = {}
        
        return mock_context
    
    async def handle_command(self, command: str, user_id: int, args: list = None) -> Optional[str]:
        """Handle a command through the message handlers."""
        args = args or []
        
        # Map command to handler method
        command_map = {
            "start": self.message_handlers.start,
            "me": self.message_handlers.cmd_me,
            "promises": self.message_handlers.list_promises,
            "nightly": self.message_handlers.nightly_reminders,
            "morning": self.message_handlers.morning_reminders,
            "weekly": self.message_handlers.weekly_report,
            "zana": self.message_handlers.plan_by_zana,
            "pomodoro": self.message_handlers.pomodoro,
            "settimezone": self.message_handlers.cmd_settimezone,
            "language": self.message_handlers.cmd_language,
            "version": self.message_handlers.cmd_version,
            "broadcast": self.message_handlers.cmd_broadcast,
        }
        
        if command not in command_map:
            return None
        
        # Create mock update and context
        user_message = UserMessage(
            user_id=user_id,
            chat_id=user_id,
            text=f"/{command} {' '.join(args)}" if args else f"/{command}",
            message_type="command",
            timestamp=datetime.now()
        )
        
        update = self._create_mock_update(user_message)
        context = self._create_mock_context(user_id)
        
        # Add args to context for commands that need them
        context.args = args
        
        try:
            # Call the handler
            handler = command_map[command]
            await handler(update, context)
            
            # Get response from response service
            # The handler should have sent a response through response_service
            # We'll need to check the response service for the last message
            return "Command executed (check response service for output)"
        except Exception as e:
            logger.error(f"Error handling command /{command}: {e}", exc_info=True)
            return f"Error: {str(e)}"
    
    async def handle_message(self, text: str, user_id: int) -> Optional[str]:
        """Handle a text message through the message handlers."""
        user_message = UserMessage(
            user_id=user_id,
            chat_id=user_id,
            text=text,
            message_type="text",
            timestamp=datetime.now()
        )
        
        update = self._create_mock_update(user_message)
        context = self._create_mock_context(user_id)
        
        try:
            await self.message_handlers.handle_message(update, context)
            return "Message processed (check response service for output)"
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            return f"Error: {str(e)}"

