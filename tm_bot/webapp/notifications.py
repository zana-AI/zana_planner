"""
Helper functions for sending Telegram notifications.
"""

import os
from typing import Optional
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from repositories.settings_repo import SettingsRepository
from utils.logger import get_logger
from cbdata import encode_cb

logger = get_logger(__name__)


async def send_follow_notification(bot_token: str, follower_id: int, followee_id: int, root_dir: str) -> None:
    """
    Send a Telegram notification to the followee when someone follows them.
    
    Args:
        bot_token: Telegram bot token
        follower_id: User ID of the person who followed
        followee_id: User ID of the person being followed
        root_dir: Root directory for accessing repositories
    """
    try:
        # Get follower's name
        settings_repo = SettingsRepository(root_dir)
        follower_settings = settings_repo.get_settings(follower_id)
        
        # Determine follower's display name
        follower_name = follower_settings.first_name or follower_settings.username or f"User {follower_id}"
        if follower_settings.username:
            follower_name = f"@{follower_settings.username}"
        elif follower_settings.first_name:
            follower_name = follower_settings.first_name
        
        # Get mini app URL for community link
        miniapp_url = os.getenv("MINIAPP_URL", "https://xaana.club")
        community_url = f"{miniapp_url}/community"
        
        # Create bot instance
        bot = Bot(token=bot_token)
        
        # Construct notification message with profile link if username exists
        if follower_settings.username:
            message = (
                f"👤 [@{follower_settings.username}](t.me/{follower_settings.username}) started following you!\n\n"
                f"See your Xaana community from here [Community]({community_url})"
            )
            parse_mode = "Markdown"
        else:
            message = (
                f"👤 {follower_name} started following you!\n\n"
                f"See your Xaana community from here [Community]({community_url})"
            )
            parse_mode = "Markdown"
        
        # Send notification
        await bot.send_message(
            chat_id=followee_id,
            text=message,
            parse_mode=parse_mode
        )
        
        logger.info(f"Sent follow notification to user {followee_id} from follower {follower_id}")
    except TelegramError as e:
        # Handle cases where user blocked bot or other Telegram errors
        error_msg = str(e).lower()
        if "blocked" in error_msg or "chat not found" in error_msg or "forbidden" in error_msg:
            logger.debug(f"Could not send follow notification to user {followee_id}: user blocked bot or chat not found")
        else:
            logger.warning(f"Error sending follow notification to user {followee_id}: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error sending follow notification to user {followee_id}: {e}")


async def send_suggestion_notifications(
    bot_token: str,
    sender_id: int,
    receiver_id: int,
    suggestion_id: str,
    template_title: Optional[str],
    freeform_text: Optional[str],
    message: Optional[str],
    root_dir: str
) -> None:
    """
    Send Telegram notifications for a promise suggestion.
    
    Args:
        bot_token: Telegram bot token
        sender_id: User ID of the person who sent the suggestion
        receiver_id: User ID of the person receiving the suggestion
        suggestion_id: ID of the suggestion for callback buttons
        template_title: Title of the template if template-based suggestion
        freeform_text: Freeform text if custom suggestion
        message: Optional personal message
        root_dir: Root directory for accessing repositories
    """
    try:
        settings_repo = SettingsRepository(root_dir)
        sender_settings = settings_repo.get_settings(sender_id)
        receiver_settings = settings_repo.get_settings(receiver_id)
        
        # Get names
        sender_name = sender_settings.first_name or sender_settings.username or f"User {sender_id}"
        if sender_settings.username:
            sender_display = f"@{sender_settings.username}"
        else:
            sender_display = sender_name
            
        receiver_name = receiver_settings.first_name or receiver_settings.username or f"User {receiver_id}"
        
        # Determine what was suggested
        if template_title:
            suggestion_text = f"📋 Template: {template_title}"
        elif freeform_text:
            suggestion_text = f"✍️ {freeform_text[:100]}{'...' if len(freeform_text) > 100 else ''}"
        else:
            suggestion_text = "a promise"
        
        bot = Bot(token=bot_token)
        
        # 1. Send notification to RECEIVER with Accept/Decline buttons
        receiver_message = f"💡 {sender_display} suggested a promise for you!\n\n{suggestion_text}"
        if message:
            receiver_message += f"\n\n💬 Message: \"{message}\""
        
        # Create inline keyboard with Accept/Decline buttons
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Accept", callback_data=encode_cb("suggest_accept", sid=suggestion_id)),
                InlineKeyboardButton("❌ Decline", callback_data=encode_cb("suggest_decline", sid=suggestion_id))
            ]
        ])
        
        try:
            await bot.send_message(
                chat_id=receiver_id,
                text=receiver_message,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            logger.info(f"Sent suggestion notification to receiver {receiver_id}")
        except TelegramError as e:
            error_msg = str(e).lower()
            if "blocked" in error_msg or "chat not found" in error_msg or "forbidden" in error_msg:
                logger.debug(f"Could not send suggestion notification to receiver {receiver_id}: user blocked bot")
            else:
                logger.warning(f"Error sending suggestion notification to receiver {receiver_id}: {e}")
        
        # 2. Send confirmation to SENDER
        sender_message = f"✅ Your suggestion was sent to {receiver_name}!\n\n{suggestion_text}"
        if message:
            sender_message += f"\n\n💬 Your message: \"{message}\""
        sender_message += "\n\nThey'll be notified and can accept or decline."
        
        try:
            await bot.send_message(
                chat_id=sender_id,
                text=sender_message,
                parse_mode="Markdown"
            )
            logger.info(f"Sent suggestion confirmation to sender {sender_id}")
        except TelegramError as e:
            error_msg = str(e).lower()
            if "blocked" in error_msg or "chat not found" in error_msg or "forbidden" in error_msg:
                logger.debug(f"Could not send suggestion confirmation to sender {sender_id}: user blocked bot")
            else:
                logger.warning(f"Error sending suggestion confirmation to sender {sender_id}: {e}")
                
    except Exception as e:
        logger.warning(f"Unexpected error sending suggestion notifications: {e}")
