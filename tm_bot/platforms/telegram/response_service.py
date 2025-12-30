"""
Telegram response service adapter.

Wraps the existing ResponseService to implement the IResponseService interface
while maintaining backward compatibility. This adapter bridges between the
platform-agnostic interface and Telegram-specific implementation.
"""

from typing import Optional, Any
from telegram import Update, Message, InlineKeyboardMarkup, Bot
from telegram.ext import CallbackContext

from ..interfaces import IResponseService
from ..types import Keyboard
from .keyboard_adapter import TelegramKeyboardAdapter
from services.response_service import ResponseService as OriginalResponseService
from handlers.messages_store import Language
from utils.logger import get_logger

logger = get_logger(__name__)


class TelegramResponseService(IResponseService):
    """
    Telegram implementation of IResponseService.
    
    This adapter wraps the original ResponseService and provides
    platform-agnostic methods while maintaining backward compatibility.
    """
    
    def __init__(self, original_service: OriginalResponseService, bot: Optional[Bot] = None):
        """
        Initialize with the original ResponseService.
        
        Args:
            original_service: The original Telegram ResponseService
            bot: Optional Telegram Bot instance for direct sending
        """
        self._original = original_service
        self._keyboard_adapter = TelegramKeyboardAdapter()
        self._bot = bot
    
    async def send_text(
        self,
        user_id: int,
        chat_id: int,
        text: str,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        disable_web_page_preview: bool = False,
    ) -> Optional[Message]:
        """Send a text message to the user."""
        # Convert keyboard if provided
        telegram_keyboard = None
        if keyboard:
            telegram_keyboard = self._keyboard_adapter.build_keyboard(keyboard)
        
        # Use bot directly if available, otherwise we need Update/CallbackContext
        # This is a limitation during transition - we'll improve this in Phase 5
        if self._bot:
            try:
                message = await self._bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=telegram_keyboard,
                    disable_web_page_preview=disable_web_page_preview,
                    reply_to_message_id=reply_to_message_id,
                )
                # Log the message
                self.log_user_message(user_id, text, message.message_id if message else None, chat_id)
                return message
            except Exception as e:
                logger.error(f"Error sending message to user {user_id}: {e}")
                return None
        else:
            # Fallback: log but cannot send without Update/CallbackContext
            logger.warning(
                f"Cannot send message to user {user_id} without bot instance. "
                "Use original ResponseService methods with Update/CallbackContext."
            )
            return None
    
    async def send_photo(
        self,
        user_id: int,
        chat_id: int,
        photo: Any,
        caption: Optional[str] = None,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None,
    ) -> Optional[Message]:
        """Send a photo to the user."""
        telegram_keyboard = None
        if keyboard:
            telegram_keyboard = self._keyboard_adapter.build_keyboard(keyboard)
        
        if self._bot:
            try:
                message = await self._bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    parse_mode=parse_mode,
                    reply_markup=telegram_keyboard,
                )
                # Log the message
                content = caption or "[Photo sent]"
                self.log_user_message(user_id, content, message.message_id if message else None, chat_id)
                return message
            except Exception as e:
                logger.error(f"Error sending photo to user {user_id}: {e}")
                return None
        else:
            logger.warning(
                f"Cannot send photo to user {user_id} without bot instance. "
                "Use original ResponseService methods with Update/CallbackContext."
            )
            return None
    
    async def send_voice(
        self,
        user_id: int,
        chat_id: int,
        voice: Any,
    ) -> Optional[Message]:
        """Send a voice message to the user."""
        if self._bot:
            try:
                message = await self._bot.send_voice(
                    chat_id=chat_id,
                    voice=voice,
                )
                # Log the message
                self.log_user_message(user_id, "[Voice message sent]", message.message_id if message else None, chat_id)
                return message
            except Exception as e:
                logger.error(f"Error sending voice to user {user_id}: {e}")
                return None
        else:
            logger.warning(
                f"Cannot send voice to user {user_id} without bot instance. "
                "Use original ResponseService methods with Update/CallbackContext."
            )
            return None
    
    async def edit_message(
        self,
        user_id: int,
        chat_id: int,
        message_id: int,
        text: str,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None,
    ) -> Optional[Message]:
        """Edit an existing message."""
        telegram_keyboard = None
        if keyboard:
            telegram_keyboard = self._keyboard_adapter.build_keyboard(keyboard)
        
        if self._bot:
            try:
                message = await self._bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=telegram_keyboard,
                )
                return message
            except Exception as e:
                logger.warning(f"Error editing message for user {user_id}: {e}")
                return None
        else:
            logger.warning(
                f"Cannot edit message for user {user_id} without bot instance. "
                "Use original ResponseService methods with Update/CallbackContext."
            )
            return None
    
    async def delete_message(
        self,
        chat_id: int,
        message_id: int,
    ) -> bool:
        """Delete a message."""
        if self._bot:
            try:
                await self._bot.delete_message(chat_id=chat_id, message_id=message_id)
                return True
            except Exception as e:
                logger.debug(f"Failed to delete message {message_id}: {e}")
                return False
        else:
            logger.warning("Cannot delete message without bot instance.")
            return False
    
    def log_user_message(
        self,
        user_id: int,
        content: str,
        message_id: Optional[int] = None,
        chat_id: Optional[int] = None,
    ) -> None:
        """Log a user message for conversation history."""
        self._original.log_user_message(user_id, content, message_id, chat_id)
    
    # Expose original service methods for backward compatibility
    @property
    def original(self) -> OriginalResponseService:
        """Access to the original ResponseService for backward compatibility."""
        return self._original
    
    def set_bot(self, bot: Bot) -> None:
        """Set the bot instance for direct message sending."""
        self._bot = bot

