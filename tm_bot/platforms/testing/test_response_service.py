"""
Test response service that captures responses for assertions.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from ..interfaces import IResponseService
from ..types import Keyboard, MediaFile
from utils.logger import get_logger

logger = get_logger(__name__)

# Type hint for Update (avoid circular import)
try:
    from telegram import Update, InlineKeyboardMarkup
    from telegram.ext import CallbackContext
except ImportError:
    Update = Any
    InlineKeyboardMarkup = Any
    CallbackContext = Any


class TestResponseService(IResponseService):
    """
    Test implementation of IResponseService that captures all responses
    for testing and assertions.
    """
    
    def __init__(self):
        """Initialize test response service."""
        self.sent_messages: List[Dict[str, Any]] = []
        self.sent_photos: List[Dict[str, Any]] = []
        self.sent_voices: List[Dict[str, Any]] = []
        self.edited_messages: List[Dict[str, Any]] = []
        self.deleted_messages: List[Dict[str, Any]] = []
        self.logged_messages: List[Dict[str, Any]] = []
    
    async def send_text(
        self,
        user_id: int,
        chat_id: int,
        text: str,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None,
        reply_to_message_id: Optional[int] = None,
        disable_web_page_preview: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Send a text message to the user (captured for testing)."""
        message = {
            "user_id": user_id,
            "chat_id": chat_id,
            "text": text,
            "keyboard": keyboard,
            "parse_mode": parse_mode,
            "reply_to_message_id": reply_to_message_id,
            "disable_web_page_preview": disable_web_page_preview,
            "timestamp": datetime.now(),
        }
        self.sent_messages.append(message)
        logger.debug(f"Test: Sent text to user {user_id}: {text[:50]}...")
        return message
    
    async def send_photo(
        self,
        user_id: int,
        chat_id: int,
        photo: Any,
        caption: Optional[str] = None,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Send a photo to the user (captured for testing)."""
        message = {
            "user_id": user_id,
            "chat_id": chat_id,
            "photo": photo,
            "caption": caption,
            "keyboard": keyboard,
            "parse_mode": parse_mode,
            "timestamp": datetime.now(),
        }
        self.sent_photos.append(message)
        logger.debug(f"Test: Sent photo to user {user_id}")
        return message
    
    async def send_voice(
        self,
        user_id: int,
        chat_id: int,
        voice: Any,
    ) -> Optional[Dict[str, Any]]:
        """Send a voice message to the user (captured for testing)."""
        message = {
            "user_id": user_id,
            "chat_id": chat_id,
            "voice": voice,
            "timestamp": datetime.now(),
        }
        self.sent_voices.append(message)
        logger.debug(f"Test: Sent voice to user {user_id}")
        return message
    
    async def edit_message(
        self,
        user_id: int,
        chat_id: int,
        message_id: int,
        text: str,
        keyboard: Optional[Keyboard] = None,
        parse_mode: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Edit an existing message (captured for testing)."""
        message = {
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "keyboard": keyboard,
            "parse_mode": parse_mode,
            "timestamp": datetime.now(),
        }
        self.edited_messages.append(message)
        logger.debug(f"Test: Edited message {message_id} for user {user_id}")
        return message
    
    async def delete_message(
        self,
        chat_id: int,
        message_id: int,
    ) -> bool:
        """Delete a message (captured for testing)."""
        self.deleted_messages.append({
            "chat_id": chat_id,
            "message_id": message_id,
            "timestamp": datetime.now(),
        })
        logger.debug(f"Test: Deleted message {message_id} in chat {chat_id}")
        return True
    
    def log_user_message(
        self,
        user_id: int,
        content: str,
        message_id: Optional[int] = None,
        chat_id: Optional[int] = None,
    ) -> None:
        """Log a user message for conversation history (captured for testing)."""
        self.logged_messages.append({
            "user_id": user_id,
            "content": content,
            "message_id": message_id,
            "chat_id": chat_id,
            "timestamp": datetime.now(),
        })
        logger.debug(f"Test: Logged message from user {user_id}")
    
    def clear(self) -> None:
        """Clear all captured messages (useful for test setup)."""
        self.sent_messages.clear()
        self.sent_photos.clear()
        self.sent_voices.clear()
        self.edited_messages.clear()
        self.deleted_messages.clear()
        self.logged_messages.clear()
    
    def get_last_message(self) -> Optional[Dict[str, Any]]:
        """Get the last sent text message."""
        return self.sent_messages[-1] if self.sent_messages else None
    
    def get_messages_for_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all messages sent to a specific user."""
        return [msg for msg in self.sent_messages if msg["user_id"] == user_id]
    
    async def reply_text(
        self,
        update: Any,
        text: str,
        user_id: Optional[int] = None,
        user_lang: Optional[Any] = None,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[Any] = None,
        disable_web_page_preview: Optional[bool] = None,
        log_conversation: bool = True,
        auto_translate: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Compatibility method for ResponseService.reply_text.
        
        Extracts user_id from Update and calls send_text.
        """
        # Extract user_id from update if not provided
        if user_id is None:
            if hasattr(update, 'effective_user') and update.effective_user:
                user_id = update.effective_user.id
            elif hasattr(update, 'message') and update.message:
                if hasattr(update.message, 'from_user') and update.message.from_user:
                    user_id = update.message.from_user.id
        
        if user_id is None:
            logger.error("Cannot reply: user_id is None")
            return None
        
        # Extract chat_id from update
        chat_id = user_id  # Default to user_id
        if hasattr(update, 'effective_chat') and update.effective_chat:
            chat_id = update.effective_chat.id
        elif hasattr(update, 'message') and update.message:
            if hasattr(update.message, 'chat') and update.message.chat:
                chat_id = update.message.chat.id
        
        # Convert Telegram keyboard to platform-agnostic Keyboard if needed
        keyboard = None
        if reply_markup and hasattr(reply_markup, 'inline_keyboard'):
            # Convert InlineKeyboardMarkup to Keyboard
            from ..types import Keyboard, KeyboardButton
            buttons = []
            for row in reply_markup.inline_keyboard:
                button_row = []
                for btn in row:
                    button_row.append(KeyboardButton(
                        text=btn.text,
                        callback_data=btn.callback_data,
                    ))
                buttons.append(button_row)
            keyboard = Keyboard(buttons=buttons)
        
        # Call send_text
        return await self.send_text(
            user_id=user_id,
            chat_id=chat_id,
            text=text,
            keyboard=keyboard,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview or False,
        )
    
    async def send_message(
        self,
        context: Any,
        chat_id: int,
        text: str,
        user_id: Optional[int] = None,
        user_lang: Optional[Any] = None,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[Any] = None,
        log_conversation: bool = True,
        auto_translate: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Compatibility method for ResponseService.send_message.
        """
        if user_id is None:
            logger.error("Cannot send message: user_id is None")
            return None
        
        # Convert Telegram keyboard to platform-agnostic Keyboard if needed
        keyboard = None
        if reply_markup and hasattr(reply_markup, 'inline_keyboard'):
            from ..types import Keyboard, KeyboardButton
            buttons = []
            for row in reply_markup.inline_keyboard:
                button_row = []
                for btn in row:
                    button_row.append(KeyboardButton(
                        text=btn.text,
                        callback_data=btn.callback_data,
                    ))
                buttons.append(button_row)
            keyboard = Keyboard(buttons=buttons)
        
        return await self.send_text(
            user_id=user_id,
            chat_id=chat_id,
            text=text,
            keyboard=keyboard,
            parse_mode=parse_mode,
        )
    
    async def send_processing_message(
        self,
        update: Any,
        user_id: Optional[int] = None,
        user_lang: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Compatibility method for ResponseService.send_processing_message.
        
        Send a quick 'processing...' message that will be edited later.
        """
        # Extract user_id from update if not provided
        if user_id is None:
            if hasattr(update, 'effective_user') and update.effective_user:
                user_id = update.effective_user.id
            elif hasattr(update, 'message') and update.message:
                if hasattr(update.message, 'from_user') and update.message.from_user:
                    user_id = update.message.from_user.id
        
        if user_id is None:
            logger.error("Cannot send processing message: user_id is None")
            return None
        
        # Extract chat_id from update
        chat_id = user_id  # Default to user_id
        if hasattr(update, 'effective_chat') and update.effective_chat:
            chat_id = update.effective_chat.id
        elif hasattr(update, 'message') and update.message:
            if hasattr(update.message, 'chat') and update.message.chat:
                chat_id = update.message.chat.id
        
        # Send processing message
        processing_text = "🔄 Processing..."
        return await self.send_text(
            user_id=user_id,
            chat_id=chat_id,
            text=processing_text,
        )
    
    async def edit_processing_message(
        self,
        context: Any,
        message: Any,
        final_text: str,
        user_id: Optional[int] = None,
        user_lang: Optional[Any] = None,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[Any] = None,
        log_conversation: bool = True,
        auto_translate: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Compatibility method for ResponseService.edit_processing_message.
        
        Edit a processing message with the final response.
        """
        if user_id is None:
            # Try to extract from message or context
            if hasattr(message, 'chat') and message.chat:
                chat_id = message.chat.id
                user_id = chat_id  # Assume chat_id == user_id for private chats
            else:
                logger.error("Cannot edit processing message: user_id is None")
                return None
        else:
            chat_id = user_id
        
        # Extract message_id from message
        message_id = None
        if hasattr(message, 'message_id'):
            message_id = message.message_id
        elif isinstance(message, dict):
            message_id = message.get('message_id')
        
        # Convert Telegram keyboard to platform-agnostic Keyboard if needed
        keyboard = None
        if reply_markup and hasattr(reply_markup, 'inline_keyboard'):
            from ..types import Keyboard, KeyboardButton
            buttons = []
            for row in reply_markup.inline_keyboard:
                button_row = []
                for btn in row:
                    button_row.append(KeyboardButton(
                        text=btn.text,
                        callback_data=btn.callback_data,
                    ))
                buttons.append(button_row)
            keyboard = Keyboard(buttons=buttons)
        
        # Edit the message (in test, we'll just send a new one or update the last one)
        if message_id:
            return await self.edit_message(
                user_id=user_id,
                chat_id=chat_id,
                message_id=message_id,
                text=final_text,
                keyboard=keyboard,
                parse_mode=parse_mode,
            )
        else:
            # If we can't edit, just send a new message
            return await self.send_text(
                user_id=user_id,
                chat_id=chat_id,
                text=final_text,
                keyboard=keyboard,
                parse_mode=parse_mode,
            )
    
    async def reply_voice(
        self,
        update: Any,
        voice: Any,
        user_id: Optional[int] = None,
        user_lang: Optional[Any] = None,
        log_conversation: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Compatibility method for ResponseService.reply_voice.
        """
        # Extract user_id from update if not provided
        if user_id is None:
            if hasattr(update, 'effective_user') and update.effective_user:
                user_id = update.effective_user.id
            elif hasattr(update, 'message') and update.message:
                if hasattr(update.message, 'from_user') and update.message.from_user:
                    user_id = update.message.from_user.id
        
        if user_id is None:
            logger.error("Cannot reply voice: user_id is None")
            return None
        
        # Extract chat_id from update
        chat_id = user_id  # Default to user_id
        if hasattr(update, 'effective_chat') and update.effective_chat:
            chat_id = update.effective_chat.id
        elif hasattr(update, 'message') and update.message:
            if hasattr(update.message, 'chat') and update.message.chat:
                chat_id = update.message.chat.id
        
        # Send voice message
        return await self.send_voice(
            user_id=user_id,
            chat_id=chat_id,
            voice=voice,
        )
    
    async def edit_message_text(
        self,
        query: Any,  # CallbackQuery
        text: str,
        user_id: Optional[int] = None,
        user_lang: Optional[Any] = None,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[Any] = None,
        log_conversation: bool = True,
        auto_translate: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Compatibility method for ResponseService.edit_message_text.
        """
        # Extract user_id from query if not provided
        if user_id is None:
            if hasattr(query, 'from_user') and query.from_user:
                user_id = query.from_user.id
        
        if user_id is None:
            logger.error("Cannot edit message: user_id is None")
            return None
        
        # Extract chat_id and message_id from query
        chat_id = user_id
        message_id = None
        if hasattr(query, 'message') and query.message:
            if hasattr(query.message, 'chat') and query.message.chat:
                chat_id = query.message.chat.id
            if hasattr(query.message, 'message_id'):
                message_id = query.message.message_id
        
        # Convert Telegram keyboard to platform-agnostic Keyboard if needed
        keyboard = None
        if reply_markup and hasattr(reply_markup, 'inline_keyboard'):
            from ..types import Keyboard, KeyboardButton
            buttons = []
            for row in reply_markup.inline_keyboard:
                button_row = []
                for btn in row:
                    button_row.append(KeyboardButton(
                        text=btn.text,
                        callback_data=btn.callback_data,
                    ))
                buttons.append(button_row)
            keyboard = Keyboard(buttons=buttons)
        
        # Edit the message
        if message_id:
            return await self.edit_message(
                user_id=user_id,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                keyboard=keyboard,
                parse_mode=parse_mode,
            )
        else:
            # If we can't edit, just send a new message
            return await self.send_text(
                user_id=user_id,
                chat_id=chat_id,
                text=text,
                keyboard=keyboard,
                parse_mode=parse_mode,
            )
    
    async def edit_message_reply_markup(
        self,
        query: Any,
        reply_markup: Optional[Any] = None,
        log_conversation: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Compatibility method for ResponseService.edit_message_reply_markup.
        """
        # Extract user_id from query
        user_id = None
        if hasattr(query, 'from_user') and query.from_user:
            user_id = query.from_user.id
        
        if user_id is None:
            logger.error("Cannot edit message markup: user_id is None")
            return None
        
        # Extract chat_id and message_id from query
        chat_id = user_id
        message_id = None
        if hasattr(query, 'message') and query.message:
            if hasattr(query.message, 'chat') and query.message.chat:
                chat_id = query.message.chat.id
            if hasattr(query.message, 'message_id'):
                message_id = query.message.message_id
        
        # Convert Telegram keyboard to platform-agnostic Keyboard if needed
        keyboard = None
        if reply_markup and hasattr(reply_markup, 'inline_keyboard'):
            from ..types import Keyboard, KeyboardButton
            buttons = []
            for row in reply_markup.inline_keyboard:
                button_row = []
                for btn in row:
                    button_row.append(KeyboardButton(
                        text=btn.text,
                        callback_data=btn.callback_data,
                    ))
                buttons.append(button_row)
            keyboard = Keyboard(buttons=buttons)
        
        # Edit the message (just the keyboard)
        if message_id:
            # Get the current message text (we'd need to store it, but for now just update keyboard)
            # In a real implementation, we'd fetch the current text, but for testing we'll just log
            logger.debug(f"Test: Editing message {message_id} keyboard for user {user_id}")
            return {
                "user_id": user_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "keyboard": keyboard,
                "timestamp": datetime.now(),
            }
        else:
            return None

