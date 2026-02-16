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


async def send_follow_notification(bot_token: str, follower_id: int, followee_id: int) -> None:
    """
    Send a Telegram notification to the followee when someone follows them.

    Args:
        bot_token: Telegram bot token
        follower_id: User ID of the person who followed
        followee_id: User ID of the person being followed
    """
    try:
        # Get follower's name
        settings_repo = SettingsRepository()
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
    """
    try:
        settings_repo = SettingsRepository()
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


async def send_focus_finished_notification(
    bot_token: str,
    user_id: int,
    session_id: str,
    promise_text: str,
    proposed_hours: float,
    miniapp_url: str,
) -> None:
    """
    Send a Telegram notification when a focus session completes.

    Args:
        bot_token: Telegram bot token
        user_id: User ID
        session_id: Session ID
        promise_text: Promise text
        proposed_hours: Proposed hours to log (from planned duration)
        miniapp_url: Mini app URL
    """
    try:
        from handlers.messages_store import get_message, Language
        from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
        from cbdata import encode_cb
        from utils.time_utils import beautify_time

        # Get user language
        settings_repo = SettingsRepository()
        user_settings = settings_repo.get_settings(user_id)
        user_lang = user_settings.language if user_settings else "en"
        lang_map = {"en": Language.EN, "fa": Language.FA, "fr": Language.FR}
        lang = lang_map.get(user_lang, Language.EN)
        
        # Create encouraging message
        message = get_message("focus_session_complete", lang, promise_text=promise_text.replace('_', ' '))
        if not message or message == "focus_session_complete":  # Fallback if message not found
            message = f"🎉 Great work! You completed a {beautify_time(proposed_hours)} focus session for:\n\n*{promise_text}*\n\nLog this time?"
        
        # Create inline keyboard with Confirm, Adjust, Discard buttons
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    f"✅ Confirm ({beautify_time(proposed_hours)})",
                    callback_data=encode_cb("session_finish_confirm", s=session_id, v=proposed_hours)
                ),
                InlineKeyboardButton(
                    "Adjust…",
                    callback_data=encode_cb("session_adjust_open", s=session_id, v=proposed_hours)
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Discard",
                    callback_data=encode_cb("session_abort", s=session_id)
                )
            ],
            [
                InlineKeyboardButton(
                    "📱 Open App",
                    web_app=WebAppInfo(url=f"{miniapp_url}/dashboard")
                )
            ]
        ])
        
        # Send message
        logger.info(f"Attempting to send Telegram notification to user {user_id} for session {session_id}")
        logger.debug(f"Bot token present: {bool(bot_token)}, token length: {len(bot_token) if bot_token else 0}")
        
        bot = Bot(token=bot_token)
        result = await bot.send_message(
            chat_id=user_id,
            text=message,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        logger.info(f"✓ Successfully sent focus completion notification to user {user_id} for session {session_id}, message_id: {result.message_id}")
    except TelegramError as e:
        error_msg = str(e).lower()
        if "blocked" in error_msg or "chat not found" in error_msg or "forbidden" in error_msg:
            logger.warning(f"Could not send focus notification to user {user_id}: user blocked bot or chat not found - {e}")
        else:
            logger.error(f"TelegramError sending focus notification to user {user_id} for session {session_id}: {e}", exc_info=True)
            raise  # Re-raise to be caught by sweeper
    except Exception as e:
        logger.error(f"Unexpected error sending focus notification to user {user_id} for session {session_id}: {e}", exc_info=True)
        raise  # Re-raise to be caught by sweeper