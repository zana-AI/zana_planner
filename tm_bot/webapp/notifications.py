"""
Helper functions for sending Telegram notifications.
"""

import os
import html
from datetime import datetime
from typing import Optional
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, TelegramError
from repositories.settings_repo import SettingsRepository
from utils.admin_utils import get_admin_ids
from utils.logger import get_logger
from cbdata import encode_cb, encode_session_cb

logger = get_logger(__name__)


async def send_club_telegram_setup_request(
    bot_token: str,
    club_id: str,
    club_name: str,
    creator_user_id: int,
    promise_text: str,
    miniapp_url: str,
) -> None:
    """Ask configured bot admins to manually create/connect a club Telegram group."""
    try:
        admin_ids = sorted(get_admin_ids())
        if not bot_token or not admin_ids:
            logger.info("Skipping club Telegram setup request: missing bot token or ADMIN_IDS")
            return

        creator_settings = SettingsRepository().get_settings(creator_user_id)
        creator_name = (
            creator_settings.first_name
            or (f"@{creator_settings.username}" if creator_settings.username else None)
            or str(creator_user_id)
        )
        setup_url = f"{miniapp_url.rstrip('/')}/admin?tab=clubs&club_id={club_id}"
        message = "\n".join([
            "New club needs Telegram group",
            "",
            f"Club: <code>{html.escape(club_name)}</code>",
            f"Creator: {html.escape(creator_name)}",
            f"Promise: {html.escape(promise_text)}",
            "",
            "Steps:",
            "1. Create a Telegram group named exactly as the club name above",
            "2. Add @xaana_bot and make it admin",
            "3. Open setup, paste the group invite link in Xaana, and save",
            "4. Optional: after confirming setup, you may leave the group if another human admin remains",
        ])
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Open setup", url=setup_url)]
        ])
        bot = Bot(token=bot_token)
        for admin_id in admin_ids:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            except TelegramError as e:
                logger.warning(f"Could not notify admin {admin_id} for club {club_id}: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error sending club Telegram setup request: {e}")


async def send_club_admin_reminder(
    bot_token: str,
    club_id: str,
    club_name: str,
    creator_user_id: int,
    promise_text: str,
    miniapp_url: str,
) -> None:
    """Remind admins that a pending club still needs Telegram setup."""
    try:
        admin_ids = sorted(get_admin_ids())
        if not bot_token or not admin_ids:
            logger.info("Skipping club Telegram reminder: missing bot token or ADMIN_IDS")
            return

        creator_settings = SettingsRepository().get_settings(creator_user_id)
        creator_name = (
            creator_settings.first_name
            or (f"@{creator_settings.username}" if creator_settings.username else None)
            or str(creator_user_id)
        )
        setup_url = f"{miniapp_url.rstrip('/')}/admin?tab=clubs&club_id={club_id}"
        message = "\n".join([
            "Reminder: club is still waiting for Telegram setup",
            "",
            f"Club: <code>{html.escape(club_name)}</code>",
            f"Creator: {html.escape(creator_name)}",
            f"Promise: {html.escape(promise_text)}",
            "",
            "Open setup, create/connect the Telegram group, and save the invite link.",
        ])
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Open setup", url=setup_url)]
        ])
        bot = Bot(token=bot_token)
        for admin_id in admin_ids:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            except TelegramError as e:
                logger.warning(f"Could not remind admin {admin_id} for club {club_id}: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error sending club Telegram reminder: {e}")


async def send_club_pending_notification(
    bot_token: str,
    user_id: int,
    club_id: str,
    club_name: str,
) -> None:
    """Tell the club creator that admin setup is pending and offer actions."""
    try:
        if not bot_token:
            return

        message = "\n".join([
            f"Nice, your club request is in: {club_name}",
            "",
            "Making a new club needs admin approval. It usually takes only a few minutes.",
            "",
            "When it is ready, you will get a Telegram group link. Join the group, then invite your friends in that group.",
            "",
            "You can cancel while it is waiting, or remind an admin after 1 hour.",
        ])
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Cancel request", callback_data=encode_cb("club_cancel", cid=club_id)),
                InlineKeyboardButton("Remind admin", callback_data=encode_cb("club_remind", cid=club_id)),
            ]
        ])
        bot = Bot(token=bot_token)
        await bot.send_message(
            chat_id=user_id,
            text=message,
            reply_markup=keyboard,
            parse_mode=None,
        )
    except TelegramError as e:
        error_msg = str(e).lower()
        if "blocked" in error_msg or "chat not found" in error_msg or "forbidden" in error_msg:
            logger.debug(f"Could not send pending club notification to user {user_id}: user blocked bot")
        else:
            logger.warning(f"Could not send pending club notification to user {user_id}: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error sending pending club notification: {e}")


async def send_club_telegram_ready_notification(
    bot_token: str,
    user_id: int,
    club_name: str,
    invite_link: str,
) -> None:
    """Notify the club creator that the Telegram group is ready."""
    try:
        if not bot_token or not invite_link:
            return

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Join Telegram group", url=invite_link)]
        ])
        message = "\n".join([
            f"Your club Telegram group is ready: {club_name}",
            "",
            "Use the button below to join it.",
        ])
        bot = Bot(token=bot_token)
        await bot.send_message(
            chat_id=user_id,
            text=message,
            reply_markup=keyboard,
            parse_mode=None,
        )
    except TelegramError as e:
        logger.warning(f"Could not notify club creator {user_id}: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error sending club Telegram ready notification: {e}")


def _language_name(language_code: str) -> str:
    names = {
        "en": "English",
        "fa": "Persian",
        "fr": "French",
    }
    return names.get((language_code or "").lower(), language_code)


def _voice_mode_name(voice_mode: str) -> str:
    labels = {
        "enabled": "enabled",
        "disabled": "disabled",
    }
    return labels.get((voice_mode or "").lower(), voice_mode)


async def send_settings_change_notification(
    bot_token: str,
    user_id: int,
    timezone: Optional[str] = None,
    language: Optional[str] = None,
    voice_mode: Optional[str] = None,
    user_language: Optional[str] = "en",
) -> None:
    """
    Send minimal settings-change notification(s) to the user chat.
    """
    try:
        if not bot_token:
            return

        from handlers.messages_store import get_message, Language

        lang_map = {"en": Language.EN, "fa": Language.FA, "fr": Language.FR}
        msg_lang = lang_map.get((user_language or "en").lower(), Language.EN)

        lines = []
        if language is not None:
            lines.append(
                get_message(
                    "settings_language_changed",
                    msg_lang,
                    lang_name=_language_name(language),
                )
            )
        if timezone is not None:
            lines.append(
                get_message(
                    "settings_timezone_changed",
                    msg_lang,
                    timezone=timezone,
                )
            )
        if voice_mode is not None:
            lines.append(
                get_message(
                    "settings_voice_mode_changed",
                    msg_lang,
                    voice_mode=_voice_mode_name(voice_mode),
                )
            )

        if not lines:
            return

        bot = Bot(token=bot_token)
        await bot.send_message(
            chat_id=user_id,
            text="\n".join(lines),
            parse_mode=None,
        )

        changed_fields = [
            name
            for name, value in (
                ("timezone", timezone),
                ("language", language),
                ("voice_mode", voice_mode),
            )
            if value is not None
        ]
        logger.info(
            f"Sent settings-change notification to user {user_id}: {', '.join(changed_fields)}"
        )
    except TelegramError as e:
        error_msg = str(e).lower()
        if "blocked" in error_msg or "chat not found" in error_msg or "forbidden" in error_msg:
            logger.debug(
                f"Could not send settings-change notification to user {user_id}: user blocked bot or chat not found"
            )
        else:
            logger.warning(f"Error sending settings-change notification to user {user_id}: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error sending settings-change notification to user {user_id}: {e}")


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


async def send_plan_session_reminder(
    bot_token: str,
    user_id: int,
    plan_session_id: int,
    promise_id: str,
    promise_text: str,
    title: Optional[str],
    planned_start: Optional[str],
    planned_duration_min: Optional[int],
) -> None:
    """
    Send a Telegram reminder when a planned session is about to start.

    Args:
        bot_token: Telegram bot token
        user_id: User ID
        plan_session_id: ID of the plan_session row
        promise_id: Human-readable promise ID (e.g. 'P5')
        promise_text: Promise text
        title: Optional session title
        planned_start: ISO datetime string for the planned start
        planned_duration_min: Duration in minutes (optional)
    """
    try:
        # Build reminder message
        session_label = (title or promise_text or "Session").strip()
        if len(session_label) > 60:
            session_label = session_label[:59] + "…"

        time_str = ""
        if planned_start:
            try:
                dt = datetime.fromisoformat(planned_start.replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M")
            except Exception:
                pass

        dur_str = ""
        if planned_duration_min:
            h, m = divmod(planned_duration_min, 60)
            if h and m:
                dur_str = f"{h}h {m}min"
            elif h:
                dur_str = f"{h}h"
            else:
                dur_str = f"{m}min"

        parts = [f"⏰ *Time to focus!*\n\n📌 {session_label}"]
        if time_str:
            parts.append(f"🕐 {time_str}" + (f"  ·  {dur_str}" if dur_str else ""))
        elif dur_str:
            parts.append(f"⏱ {dur_str}")
        message = "\n".join(parts)

        # Build inline keyboard (3 rows)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "▶️ Start Focus",
                    callback_data=encode_cb("psess_start", sid=str(plan_session_id), pid=promise_id),
                )
            ],
            [
                InlineKeyboardButton(
                    "⏰ Snooze 1h",
                    callback_data=encode_cb("psess_snooze", sid=str(plan_session_id), m=60),
                ),
                InlineKeyboardButton(
                    "🌙 Tomorrow",
                    callback_data=encode_cb("psess_snooze", sid=str(plan_session_id), m=1440),
                ),
            ],
            [
                InlineKeyboardButton(
                    "❌ Delete",
                    callback_data=encode_cb("psess_del", sid=str(plan_session_id)),
                )
            ],
        ])

        bot = Bot(token=bot_token)
        await bot.send_message(
            chat_id=user_id,
            text=message,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        logger.info(
            f"✓ Sent plan session reminder to user {user_id} for plan_session {plan_session_id}"
        )
    except TelegramError as e:
        error_msg = str(e).lower()
        if "blocked" in error_msg or "chat not found" in error_msg or "forbidden" in error_msg:
            logger.warning(
                f"Could not send plan session reminder to user {user_id}: user blocked bot or chat not found"
            )
        else:
            logger.error(
                f"TelegramError sending plan session reminder to user {user_id} "
                f"for plan_session {plan_session_id}: {e}",
                exc_info=True,
            )
            raise
    except Exception as e:
        logger.error(
            f"Unexpected error sending plan session reminder to user {user_id} "
            f"for plan_session {plan_session_id}: {e}",
            exc_info=True,
        )
        raise


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
        from utils.time_utils import beautify_time

        def build_focus_keyboard(include_actions: bool = True) -> InlineKeyboardMarkup:
            rows = []
            if include_actions:
                rows.extend([
                    [
                        InlineKeyboardButton(
                            f"✅ Confirm ({beautify_time(proposed_hours)})",
                            callback_data=encode_session_cb(
                                "session_finish_confirm",
                                session_id,
                                value=proposed_hours,
                            ),
                        ),
                        InlineKeyboardButton(
                            "Adjust…",
                            callback_data=encode_session_cb(
                                "session_adjust_open",
                                session_id,
                                value=proposed_hours,
                            ),
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "❌ Discard",
                            callback_data=encode_session_cb("session_abort", session_id),
                        )
                    ],
                ])
            rows.append([
                InlineKeyboardButton(
                    "📱 Open App",
                    web_app=WebAppInfo(url=f"{miniapp_url}/dashboard")
                )
            ])
            return InlineKeyboardMarkup(rows)

        # Get user language
        settings_repo = SettingsRepository()
        user_settings = settings_repo.get_settings(user_id)
        user_lang = user_settings.language if user_settings else "en"
        lang_map = {"en": Language.EN, "fa": Language.FA, "fr": Language.FR}
        lang = lang_map.get(user_lang, Language.EN)
        
        # Create encouraging message
        promise_label = (promise_text or "").replace("_", " ").strip()
        if not promise_label:
            promise_label = "your promise"
        duration_label = beautify_time(proposed_hours)
        message = get_message(
            "focus_session_complete",
            lang,
            promise_text=promise_label,
            duration=duration_label,
        )
        if not message or message == "focus_session_complete":
            message = (
                f"🎉 Great work! You completed {duration_label} for:\n\n"
                f"{promise_label}\n\n"
                "Log this time?"
            )
        if False:
            message = f"🎉 Great work! You completed a {beautify_time(proposed_hours)} focus session for:\n\n*{promise_text}*\n\nLog this time?"
        
        # Create inline keyboard with Confirm, Adjust, Discard buttons
        keyboard = build_focus_keyboard(include_actions=True)
        
        # Send message
        logger.info(f"Attempting to send Telegram notification to user {user_id} for session {session_id}")
        logger.debug(f"Bot token present: {bool(bot_token)}, token length: {len(bot_token) if bot_token else 0}")
        
        bot = Bot(token=bot_token)
        try:
            result = await bot.send_message(
                chat_id=user_id,
                text=message,
                reply_markup=keyboard,
                parse_mode=None
            )
        except BadRequest as e:
            if "button_data_invalid" not in str(e).lower():
                raise

            logger.warning(
                "Focus notification keyboard rejected for session %s; sending fallback notification without callback buttons",
                session_id,
            )
            result = await bot.send_message(
                chat_id=user_id,
                text=message,
                reply_markup=build_focus_keyboard(include_actions=False),
                parse_mode=None,
            )
        
        logger.info(f"✓ Successfully sent focus completion notification to user {user_id} for session {session_id}, message_id: {result.message_id}")
    except TelegramError as e:
        error_msg = str(e).lower()
        if "blocked" in error_msg or "chat not found" in error_msg or "forbidden" in error_msg:
            logger.warning(f"Could not send focus notification to user {user_id}: user blocked bot or chat not found - {e}")
        elif "button_data_invalid" in error_msg:
            logger.warning(
                "Focus notification had invalid callback data for session %s: %s",
                session_id,
                e,
            )
            raise
        else:
            logger.error(f"TelegramError sending focus notification to user {user_id} for session {session_id}: {e}", exc_info=True)
            raise  # Re-raise to be caught by sweeper
    except Exception as e:
        logger.error(f"Unexpected error sending focus notification to user {user_id} for session {session_id}: {e}", exc_info=True)
        raise  # Re-raise to be caught by sweeper
