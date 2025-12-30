"""
Type converters between Telegram types and platform-agnostic types.
"""

from typing import Optional
from datetime import datetime
from telegram import Update
from telegram.ext import CallbackContext

from ..types import UserMessage, CallbackQuery, MessageType, MediaFile


def telegram_update_to_user_message(update: Update) -> UserMessage:
    """Convert Telegram Update to platform-agnostic UserMessage."""
    user = update.effective_user
    chat = update.effective_chat
    message = update.effective_message
    
    if not user or not chat:
        raise ValueError("Update must have effective_user and effective_chat")
    
    user_id = user.id
    chat_id = chat.id
    message_id = message.message_id if message else None
    text = message.text if message else None
    timestamp = message.date if message else datetime.now()
    
    # Determine message type
    message_type = MessageType.TEXT
    media = None
    location = None
    
    if message:
        if message.voice:
            message_type = MessageType.VOICE
            media = MediaFile(file_id=message.voice.file_id)
        elif message.photo:
            message_type = MessageType.IMAGE
            # Get largest photo
            photo = message.photo[-1] if message.photo else None
            if photo:
                media = MediaFile(file_id=photo.file_id)
        elif message.location:
            message_type = MessageType.LOCATION
            location = {
                "latitude": message.location.latitude,
                "longitude": message.location.longitude
            }
        elif message.poll:
            message_type = MessageType.POLL
        elif message.text and message.text.startswith('/'):
            message_type = MessageType.COMMAND
    
    # Store original Update in metadata for backward compatibility
    metadata = {
        "update": update,
        "original_message": message,
    }
    
    return UserMessage(
        user_id=user_id,
        chat_id=chat_id,
        text=text,
        message_type=message_type,
        message_id=message_id,
        timestamp=timestamp,
        media=media,
        location=location,
        metadata=metadata,
    )


def telegram_callback_to_callback_query(
    update: Update,
    context: Optional[CallbackContext] = None
) -> CallbackQuery:
    """Convert Telegram callback query to platform-agnostic CallbackQuery."""
    query = update.callback_query
    if not query:
        raise ValueError("Update must have a callback_query")
    
    user = query.from_user
    message = query.message
    
    return CallbackQuery(
        user_id=user.id if user else 0,
        chat_id=message.chat.id if message else 0,
        message_id=message.message_id if message else 0,
        data=query.data or "",
        query_id=str(query.id) if query.id else None,
        timestamp=query.message.date if message else datetime.now(),
        metadata={
            "original_query": query,
            "context": context,
        }
    )

