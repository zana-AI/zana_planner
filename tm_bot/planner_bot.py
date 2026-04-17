"""
Refactored bot for the planner application.
This version uses platform abstraction to support multiple platforms (Telegram, Discord, etc.).
The web app runs as a separate process; this module runs the Telegram (or other platform) bot only.
"""
import asyncio
import os
import subprocess
import sys
import threading
from typing import Optional
from unittest.mock import Mock

# Platform abstraction imports
from platforms.interfaces import IPlatformAdapter
from platforms.telegram.adapter import TelegramPlatformAdapter

# Telegram-specific imports (for backward compatibility during transition)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)
from telegram.request import HTTPXRequest
from telegram import error as telegram_error, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.exc import OperationalError as SQLOperationalError
from sqlalchemy import text

from llms.llm_handler import LLMHandler
from services.planner_api_adapter import PlannerAPIAdapter
from services.response_service import ResponseService
from handlers.message_handlers import MessageHandlers
from handlers.callback_handlers import CallbackHandlers
from handlers.messages_store import initialize_message_store, get_user_language
from webapp.notifications import send_club_telegram_ready_notification
from router_types import InputContext
from utils.bot_utils import BotUtils
from utils.admin_utils import get_admin_ids, is_admin
from utils.logger import get_logger, configure_admin_error_notifications
from db.postgres_db import get_db_session, utc_now_iso
from repositories.clubs_repo import ensure_club_telegram_columns, get_club_columns

logger = get_logger(__name__)
CLUB_TELEGRAM_CONFIRM_PREFIX = "clubtg_confirm:"


def _is_staging_or_test_mode() -> bool:
    env = (os.getenv("ENV", "") or os.getenv("ENVIRONMENT", "")).lower()
    if env in {"staging", "stage", "test", "testing"}:
        return True
    return os.getenv("PYTEST_CURRENT_TEST") is not None


# Command name -> MessageHandlers method for central routing
COMMAND_ROUTE_MAP = {
    "start": "start",
    "me": "cmd_me",
    "promises": "list_promises",
    "nightly": "nightly_reminders",
    "morning": "morning_reminders",
    "weekly": "weekly_report",
    "zana": "plan_by_zana",
    "pomodoro": "pomodoro",
    "settimezone": "cmd_settimezone",
    "language": "cmd_language",
    "version": "cmd_version",
    "broadcast": "cmd_broadcast",
    "club": "cmd_club",
    "admin": "cmd_admin",
}

class PlannerBot:
    """
    Main bot class with platform abstraction.
    
    This class is platform-agnostic and works with any IPlatformAdapter implementation.
    For Telegram, use TelegramPlatformAdapter. For other platforms, provide appropriate adapters.
    """

    def __init__(self, platform_adapter: IPlatformAdapter, root_dir: str, miniapp_url: str = "https://xaana.club"):
        """
        Initialize the bot with a platform adapter.

        Args:
            platform_adapter: Platform adapter implementing IPlatformAdapter
            root_dir: Root directory for user data
            miniapp_url: URL for the Telegram mini app
        """
        self.platform_adapter = platform_adapter
        self.root_dir = root_dir
        self.miniapp_url = miniapp_url
        
        # Initialize core components
        self.llm_handler = LLMHandler()
        self.plan_keeper = PlannerAPIAdapter(root_dir)
        
        # Get response service from platform adapter
        self.response_service = platform_adapter.response_service
        
        # For backward compatibility, also store original response service if available
        if hasattr(self.response_service, 'original'):
            self._original_response_service = self.response_service.original
        else:
            # For non-Telegram platforms (like CLI), use the adapter's response service directly
            # if it implements the compatibility methods (reply_text, send_message)
            if hasattr(self.response_service, 'reply_text'):
                # The adapter's response service can handle Update objects (e.g., TestResponseService)
                self._original_response_service = self.response_service
            else:
                # Fallback: create a response service if adapter doesn't provide one
                self._original_response_service = ResponseService(
                    settings_repo=self.plan_keeper.settings_repo
                )
        
        # Set LLM handler on response service for translation review
        if hasattr(self._original_response_service, 'set_llm_handler'):
            self._original_response_service.set_llm_handler(self.llm_handler)

        # Initialize handlers (still using Telegram-specific handlers for now)
        # In Phase 5, these will be refactored to use base handlers
        if hasattr(platform_adapter, 'application'):
            # Telegram-specific initialization
            self.application = platform_adapter.application
            self.message_handlers = MessageHandlers(
                self.plan_keeper,
                self.llm_handler,
                self.root_dir,
                self.application,
                self._original_response_service,
                self.miniapp_url
            )
            self.callback_handlers = CallbackHandlers(
                self.plan_keeper,
                self.application,
                self._original_response_service,
                self.miniapp_url
            )
            
            # Store plan_keeper, llm_handler, and response_service in bot_data
            self.application.bot_data['plan_keeper'] = self.plan_keeper
            self.application.bot_data['llm_handler'] = self.llm_handler
            self.application.bot_data['response_service'] = self._original_response_service
        else:
            # For non-Telegram platforms, initialize handlers with mock application
            # Create a minimal mock application for handlers that need it
            # Create mock job queue that works with the platform adapter's scheduler
            mock_job_queue = Mock()
            # Make job_queue methods work with our scheduler
            # Note: jobs are actually managed by platform adapter's scheduler,
            # so we return empty list to indicate no Telegram jobs exist
            def get_jobs_by_name(_name):
                # Return empty list - jobs are managed by platform adapter's scheduler
                return []
            mock_job_queue.get_jobs_by_name = get_jobs_by_name
            
            mock_application = Mock()
            mock_application.job_queue = mock_job_queue
            mock_application.bot_data = {}
            mock_application.bot = Mock()  # Some handlers may need bot
            
            self.application = mock_application
            self.message_handlers = MessageHandlers(
                self.plan_keeper,
                self.llm_handler,
                self.root_dir,
                mock_application,
                self._original_response_service,
                self.miniapp_url
            )
            self.callback_handlers = CallbackHandlers(
                self.plan_keeper,
                mock_application,
                self._original_response_service,
                self.miniapp_url
            )
            
            # Store in bot_data for handlers
            mock_application.bot_data['plan_keeper'] = self.plan_keeper
            mock_application.bot_data['llm_handler'] = self.llm_handler
            mock_application.bot_data['response_service'] = self._original_response_service
        
        # Set LLM handler in plan_keeper for time estimation service
        self.plan_keeper.set_llm_handler(self.llm_handler)

        # Initialize message store with settings repository
        initialize_message_store(self.plan_keeper.settings_repo)

        # Register all handlers
        if self.application:
            self._register_handlers()
        
        # For CLI adapter, set bot so input is routed through dispatch()
        if hasattr(platform_adapter, 'set_handlers') and self.message_handlers:
            platform_adapter.set_handlers(self)

    def _build_input_context(self, update, context) -> InputContext:
        """
        Build a platform-agnostic InputContext from a Telegram Update.
        Used by dispatch() to classify and route all incoming inputs.
        """
        from telegram import MessageEntity
        user_id = 0
        chat_id = 0
        input_type = "unknown"
        raw_text = None
        command = None
        command_args = []
        callback_data = None
        message_id = None
        metadata = {}

        if getattr(update, "callback_query", None):
            cq = update.callback_query
            user_id = cq.from_user.id if cq.from_user else 0
            chat_id = cq.message.chat_id if cq.message else user_id
            input_type = "callback"
            callback_data = cq.data
            message_id = cq.message.message_id if cq.message else None
        elif getattr(update, "poll_answer", None):
            pa = update.poll_answer
            user_id = pa.user.id if pa.user else 0
            chat_id = user_id
            if getattr(pa, "voter_chat", None) and hasattr(pa.voter_chat, "id"):
                chat_id = pa.voter_chat.id
            input_type = "poll_answer"
            metadata["poll_id"] = getattr(pa, "poll_id", None)
            metadata["option_ids"] = getattr(pa, "option_ids", [])
        elif getattr(update, "message_reaction", None):
            mr = update.message_reaction
            user_id = mr.user.id if getattr(mr, "user", None) and mr.user else 0
            chat_id = getattr(mr, "chat", None)
            if chat_id and hasattr(chat_id, "id"):
                chat_id = chat_id.id
            chat_id = chat_id or user_id
            input_type = "reaction"
            metadata["message_id"] = getattr(mr, "message_id", None)
            metadata["old_reaction"] = getattr(mr, "old_reaction", None)
            metadata["new_reaction"] = getattr(mr, "new_reaction", None)
        elif getattr(update, "message_reaction_count", None):
            mrc = update.message_reaction_count
            chat_id = getattr(mrc, "chat", None)
            if chat_id and hasattr(chat_id, "id"):
                chat_id = chat_id.id
            else:
                chat_id = 0
            input_type = "reaction"
            metadata["message_id"] = getattr(mrc, "message_id", None)
            metadata["reactions"] = getattr(mrc, "reactions", None)
        elif getattr(update, "my_chat_member", None) or getattr(update, "chat_member", None):
            cm = update.my_chat_member or update.chat_member
            user_id = cm.from_user.id if cm.from_user else 0
            chat_id = cm.chat.id if cm.chat else user_id
            input_type = "chat_member"
            metadata["old_chat_member"] = getattr(cm, "old_chat_member", None)
            metadata["new_chat_member"] = getattr(cm, "new_chat_member", None)
        elif getattr(update, "edited_message", None):
            msg = update.edited_message
            user_id = msg.from_user.id if msg.from_user else 0
            chat_id = msg.chat.id if msg.chat else user_id
            message_id = msg.message_id
            input_type = "edited_message"
            raw_text = (msg.text or msg.caption or "").strip() or None
        elif getattr(update, "effective_message", None):
            msg = update.effective_message
            user_id = update.effective_user.id if update.effective_user else 0
            chat_id = update.effective_chat.id if update.effective_chat else user_id
            message_id = msg.message_id if msg else None
            if update.effective_chat:
                metadata["chat_type"] = getattr(update.effective_chat, "type", None)

            if getattr(msg, "new_chat_members", None):
                input_type = "new_chat_members"
                metadata["new_chat_members"] = msg.new_chat_members
            elif getattr(msg, "left_chat_member", None):
                input_type = "left_chat_member"
                metadata["left_chat_member"] = msg.left_chat_member
            elif getattr(msg, "pinned_message", None):
                input_type = "pinned_message"
                metadata["pinned_message"] = msg.pinned_message
            elif getattr(msg, "voice", None):
                input_type = "voice"
            elif getattr(msg, "photo", None) or (
                getattr(msg, "document", None)
                and getattr(msg.document, "mime_type", None)
                and (msg.document.mime_type or "").startswith("image/")
            ):
                input_type = "image"
            elif getattr(msg, "location", None):
                input_type = "location"
                metadata["latitude"] = msg.location.latitude
                metadata["longitude"] = msg.location.longitude
            elif getattr(msg, "poll", None):
                input_type = "poll"
            elif getattr(msg, "text", None):
                text = msg.text or ""
                entities = getattr(msg, "entities", None) or []
                is_command = any(
                    getattr(e, "type", None) == MessageEntity.BOT_COMMAND
                    for e in entities
                )
                if is_command and text.startswith("/"):
                    parts = text.lstrip("/").split(maxsplit=1)
                    command = parts[0].lower() if parts else None
                    command_args = parts[1].split() if len(parts) > 1 and parts[1] else []
                    input_type = "command"
                    raw_text = text
                else:
                    input_type = "text"
                    raw_text = text
            else:
                input_type = "unknown"
                raw_text = getattr(msg, "caption", None) or ""

        language = get_user_language(user_id) if user_id else None
        return InputContext(
            user_id=user_id,
            chat_id=chat_id,
            input_type=input_type,
            raw_text=raw_text,
            command=command,
            command_args=command_args,
            language=language,
            platform_update=update,
            platform_context=context,
            callback_data=callback_data,
            metadata=metadata,
            message_id=message_id,
        )

    def _get_effective_user(self, update):
        """Extract Telegram User from any update type (message, callback, poll_answer)."""
        if getattr(update, "callback_query", None) and update.callback_query.from_user:
            return update.callback_query.from_user
        if getattr(update, "poll_answer", None) and update.poll_answer.user:
            return update.poll_answer.user
        if getattr(update, "my_chat_member", None) and update.my_chat_member.from_user:
            return update.my_chat_member.from_user
        if getattr(update, "chat_member", None) and update.chat_member.from_user:
            return update.chat_member.from_user
        return getattr(update, "effective_user", None)

    async def dispatch(self, update, context) -> None:
        """
        Single entry point for all incoming inputs (commands, text, voice, image, callback, etc.).
        Builds InputContext, applies cross-cutting concerns, then routes.
        """
        try:
            ctx = self._build_input_context(update, context)
            if context and hasattr(context, "user_data") and context.user_data is not None:
                context.user_data["_input_context"] = ctx

            # Cross-cutting: heal invalid persisted timezone values (e.g., DISABLED)
            # Fire-and-forget: offload to thread pool so it never blocks the event loop.
            if ctx.user_id:
                asyncio.create_task(asyncio.to_thread(
                    BotUtils.heal_invalid_timezone, self.plan_keeper, ctx.user_id
                ))

            # Cross-cutting: update user info and avatar (for any input with a user)
            # Fire-and-forget: offload to thread pool so DB writes don't block the event loop.
            effective_user = self._get_effective_user(update)
            if ctx.user_id and effective_user:
                asyncio.create_task(asyncio.to_thread(
                    self.message_handlers._update_user_info, ctx.user_id, effective_user
                ))
            if ctx.user_id and context:
                await self.message_handlers._update_user_avatar_async(context, ctx.user_id)

            # Cross-cutting: log inbound message (command, text, or placeholder for voice/image)
            content_to_log = None
            if ctx.input_type == "command" and ctx.command:
                content_to_log = "/" + ctx.command
                if ctx.command_args:
                    content_to_log += " " + " ".join(ctx.command_args)
            elif ctx.raw_text and ctx.input_type == "text":
                content_to_log = ctx.raw_text
            elif ctx.input_type == "voice":
                content_to_log = "[voice]"
            elif ctx.input_type == "image":
                content_to_log = "[image]"
            if content_to_log is not None and ctx.user_id:
                self._original_response_service.log_user_message(
                    user_id=ctx.user_id,
                    content=content_to_log,
                    message_id=ctx.message_id,
                    chat_id=ctx.chat_id,
                )

            if self._is_group_chat(ctx) and ctx.input_type in {
                "command",
                "text",
                "voice",
                "image",
                "location",
                "poll",
                "new_chat_members",
                "left_chat_member",
            }:
                await self._handle_group_input(ctx)
                return

            # Ack policy: send "Thinking..." only for LLM-bound types when response will be editable text
            processing_msg = None
            llm_bound = ctx.input_type in ("text", "voice", "image")
            if llm_bound and ctx.user_id:
                settings = await self.plan_keeper.async_get_settings(ctx.user_id)
                voice_mode_enabled = bool(settings and getattr(settings, "voice_mode", None) == "enabled")
                if ctx.input_type == "text" or not voice_mode_enabled:
                    processing_msg = await self._original_response_service.send_processing_message(
                        update, user_id=ctx.user_id, user_lang=ctx.language
                    )
                    if processing_msg and context and hasattr(context, "user_data") and context.user_data is not None:
                        context.user_data["_processing_msg"] = processing_msg
            ctx.processing_msg = processing_msg

            # Route by input_type
            if ctx.input_type == "callback":
                await self._route_callback(ctx)
                return
            if ctx.input_type == "command" and ctx.command:
                await self._route_command(ctx)
                return
            if ctx.input_type == "text":
                await self._route_to_agent(ctx)
                return
            if ctx.input_type == "voice":
                await self.message_handlers.on_voice(update, context)
                return
            if ctx.input_type == "image":
                await self.message_handlers.on_image(update, context)
                return
            if ctx.input_type == "location":
                await self.message_handlers.on_location_shared(update, context)
                return
            if ctx.input_type == "poll":
                await self.message_handlers.on_poll_created(update, context)
                return
            if ctx.input_type == "poll_answer":
                await self.message_handlers.on_poll_answer(update, context)
                return
            if ctx.input_type == "edited_message":
                await self._on_message_edited(ctx)
                return
            if ctx.input_type == "reaction":
                await self._on_reaction(ctx)
                return
            if ctx.input_type == "pinned_message":
                await self._on_message_pinned(ctx)
                return
            if ctx.input_type == "chat_member":
                await self._on_chat_member(ctx)
                return
            if ctx.input_type in {"new_chat_members", "left_chat_member"}:
                return

            logger.warning("dispatch: unhandled input_type=%s", ctx.input_type)
            await self._route_to_agent(ctx)
        finally:
            await self._cleanup_orphan_processing_message(context)

    def _is_group_chat(self, ctx: InputContext) -> bool:
        chat_type = ctx.metadata.get("chat_type")
        if chat_type in {"group", "supergroup"}:
            return True
        chat = getattr(ctx.platform_update, "effective_chat", None)
        if chat and getattr(chat, "type", None) in {"group", "supergroup"}:
            return True
        return bool(ctx.chat_id and ctx.chat_id < 0)

    async def _handle_group_input(self, ctx: InputContext) -> None:
        """Keep group behavior club-scoped and avoid personal assistant routing."""
        if ctx.input_type == "new_chat_members":
            await self._welcome_group_members(ctx)
            return

        if ctx.input_type == "command":
            command = (ctx.command or "").split("@", 1)[0].lower()
            if command in {"start", "club", "promise", "status"}:
                await self._reply_with_group_club_summary(ctx)
            return

        text_value = (ctx.raw_text or "").strip().lower()
        if text_value in {"club", "promise", "status"}:
            await self._reply_with_group_club_summary(ctx)
            return
        if await self._message_addresses_bot(ctx):
            await self._handle_group_llm_message(ctx)

    async def _welcome_group_members(self, ctx: InputContext) -> None:
        members = ctx.metadata.get("new_chat_members") or []
        human_names = []
        for member in members:
            if getattr(member, "is_bot", False):
                continue
            name = (getattr(member, "first_name", "") or getattr(member, "username", "") or "").strip()
            if name:
                human_names.append(name)
        if not human_names:
            return

        club = self._get_club_for_group_chat(ctx.chat_id)
        if not club:
            return

        promise_line = f"Shared promise: {club['promise_text']}" if club.get("promise_text") else "Shared promise is being set up."
        message = "\n".join([
            f"Welcome {', '.join(human_names)}.",
            f"This group is connected to {club['club_name']} on Xaana.",
            promise_line,
            "Use /club to see the club promise here.",
        ])
        await ctx.platform_context.bot.send_message(chat_id=ctx.chat_id, text=message, parse_mode=None)

    async def _reply_with_group_club_summary(self, ctx: InputContext) -> None:
        club = self._get_club_for_group_chat(ctx.chat_id)
        if not club:
            club = self._link_ready_club_for_group_chat(ctx)
        if not club:
            await self._reply_with_group_setup_help(ctx)
            return

        lines = [f"Club: {club['club_name']}"]
        if club.get("promise_text"):
            lines.append(f"Promise: {club['promise_text']}")
        if club.get("target_count_per_week") is not None:
            target = float(club["target_count_per_week"])
            target_text = str(int(target)) if target.is_integer() else str(target)
            lines.append(f"Target: {target_text} times/week")
        lines.append("I only share club-level promise info in this group.")
        await self._reply_to_group_message(ctx, "\n".join(lines), parse_mode=None)

    async def _reply_with_group_setup_help(self, ctx: InputContext) -> None:
        message = "\n".join([
            "I can help here after this Telegram group is connected to a Xaana club.",
            "",
            "If you just created the club, wait for admin approval and the group link.",
            "If you are setting up the group, add me as an admin, then ask a Xaana admin to confirm the link.",
            "",
            "After it is connected, use /club here.",
        ])
        await self._reply_to_group_message(ctx, message, parse_mode=None)

    async def _handle_group_llm_message(self, ctx: InputContext) -> None:
        club = self._get_club_for_group_chat(ctx.chat_id)
        if not club:
            club = self._link_ready_club_for_group_chat(ctx)
        if not club:
            await self._reply_with_group_setup_help(ctx)
            return

        user_message = await self._clean_group_user_message(ctx)
        target_text = ""
        if club.get("target_count_per_week") is not None:
            target = float(club["target_count_per_week"])
            target_text = str(int(target)) if target.is_integer() else str(target)
            target_text = f"{target_text} times/week"

        processing_msg = await self._reply_to_group_message(ctx, "Thinking...", parse_mode=None)
        response_text = await asyncio.to_thread(
            self.llm_handler.get_response_group_safe,
            user_message,
            {
                "chat_id": ctx.chat_id,
                "club_name": club.get("club_name"),
                "promise_text": club.get("promise_text"),
                "target_text": target_text,
            },
            ctx.language.value if ctx.language else None,
        )
        response_text = str(response_text or "").strip() or "I am having trouble right now. Please try again in a moment."

        if processing_msg:
            try:
                await processing_msg.edit_text(text=response_text, parse_mode=None)
                return
            except Exception as e:
                logger.debug("Could not edit group processing reply: %s", e)

        await self._reply_to_group_message(ctx, response_text, parse_mode=None)

    async def _reply_to_group_message(self, ctx: InputContext, text: str, **kwargs):
        message = getattr(ctx.platform_update, "effective_message", None)
        if message:
            try:
                return await message.reply_text(text=text, **kwargs)
            except Exception as e:
                logger.debug("Could not reply to group message directly: %s", e)

        bot = getattr(ctx.platform_context, "bot", None)
        if not bot:
            return None
        return await bot.send_message(chat_id=ctx.chat_id, text=text, **kwargs)

    async def _clean_group_user_message(self, ctx: InputContext) -> str:
        message = getattr(ctx.platform_update, "effective_message", None)
        text_value = (
            getattr(message, "text", None)
            or getattr(message, "caption", None)
            or ctx.raw_text
            or ""
        )
        username, _bot_id = await self._resolve_bot_identity(ctx)
        cleaned = str(text_value or "").strip()
        if username:
            cleaned = cleaned.replace(f"@{username}", "").replace(f"@{username.lower()}", "")

        command = (ctx.command or "").split("@", 1)[0].lower()
        if command:
            cleaned = cleaned.replace(f"/{ctx.command}", "", 1).strip()

        return cleaned.strip() or "The user addressed you in the group."

    async def _message_addresses_bot(self, ctx: InputContext) -> bool:
        message = getattr(ctx.platform_update, "effective_message", None)
        if not message:
            return False

        text_value = (getattr(message, "text", None) or getattr(message, "caption", None) or ctx.raw_text or "")
        entities = list(getattr(message, "entities", None) or getattr(message, "caption_entities", None) or [])
        reply_to_message = getattr(message, "reply_to_message", None)

        needs_bot_identity = bool(
            "@" in text_value
            or entities
            or reply_to_message
        )
        if not needs_bot_identity:
            return False

        username, bot_id = await self._resolve_bot_identity(ctx)

        if username and f"@{username}" in text_value.lower():
            return True

        if reply_to_message:
            reply_author = getattr(reply_to_message, "from_user", None)
            if bot_id and getattr(reply_author, "id", None) == bot_id:
                return True

        for entity in entities:
            entity_type = getattr(entity, "type", None)
            if entity_type == "text_mention":
                mentioned_user = getattr(entity, "user", None)
                if bot_id and getattr(mentioned_user, "id", None) == bot_id:
                    return True
            if entity_type == "mention" and username:
                try:
                    mention_text = entity.extract_from(text_value)
                except Exception:
                    offset = int(getattr(entity, "offset", 0) or 0)
                    length = int(getattr(entity, "length", 0) or 0)
                    mention_text = text_value[offset:offset + length]
                if mention_text.strip().lower() == f"@{username}":
                    return True

        return False

    async def _resolve_bot_identity(self, ctx: InputContext) -> tuple[Optional[str], Optional[int]]:
        bot = getattr(ctx.platform_context, "bot", None)
        if not bot:
            return None, None

        username = (getattr(bot, "username", "") or "").strip().lower() or None
        bot_id = getattr(bot, "id", None)
        if username and bot_id:
            return username, bot_id

        try:
            me = await bot.get_me()
        except Exception as e:
            logger.debug("Could not resolve bot identity for group mention detection: %s", e)
            return username, bot_id

        username = (getattr(me, "username", "") or "").strip().lower()
        bot_id = getattr(me, "id", bot_id)
        return username or None, bot_id

    def _get_group_title(self, ctx: InputContext) -> str:
        chat = getattr(ctx.platform_update, "effective_chat", None)
        return (getattr(chat, "title", "") or "").strip()

    def _link_ready_club_for_group_chat(self, ctx: InputContext) -> Optional[dict]:
        if not ctx.chat_id or not ctx.user_id:
            return None

        group_title = self._get_group_title(ctx)
        if not group_title:
            return None

        now = utc_now_iso()
        with get_db_session() as session:
            ensure_club_telegram_columns(session)
            club_columns = get_club_columns(session)
            if not {"telegram_status", "telegram_chat_id"}.issubset(club_columns):
                return None

            rows = session.execute(
                text("""
                    SELECT club_id
                    FROM clubs
                    WHERE owner_user_id = :owner_user_id
                      AND COALESCE(status, 'active') = 'active'
                      AND telegram_status = 'ready'
                      AND NULLIF(trim(COALESCE(telegram_chat_id, '')), '') IS NULL
                      AND lower(trim(name)) = lower(trim(:group_name))
                    ORDER BY COALESCE(telegram_ready_at_utc, created_at_utc) DESC;
                """),
                {
                    "owner_user_id": str(ctx.user_id),
                    "group_name": group_title,
                },
            ).mappings().fetchall()
            if len(rows) != 1:
                return None

            session.execute(
                text("""
                    UPDATE clubs
                    SET telegram_chat_id = :telegram_chat_id,
                        updated_at_utc = :updated_at
                    WHERE club_id = :club_id
                      AND telegram_status = 'ready'
                      AND NULLIF(trim(COALESCE(telegram_chat_id, '')), '') IS NULL;
                """),
                {
                    "club_id": str(rows[0]["club_id"]),
                    "telegram_chat_id": str(ctx.chat_id),
                    "updated_at": now,
                },
            )

        return self._get_club_for_group_chat(ctx.chat_id)

    def _get_club_for_group_chat(self, chat_id: int) -> Optional[dict]:
        if not chat_id:
            return None
        with get_db_session() as session:
            ensure_club_telegram_columns(session)
            row = session.execute(
                text("""
                    SELECT
                        c.club_id,
                        c.name AS club_name,
                        p.text AS promise_text,
                        pi.target_value AS target_count_per_week
                    FROM clubs c
                    LEFT JOIN promise_club_shares pcs ON pcs.club_id = c.club_id
                    LEFT JOIN promises p
                        ON p.promise_uuid = pcs.promise_uuid
                       AND p.is_deleted = 0
                    LEFT JOIN promise_instances pi
                        ON pi.promise_uuid = p.promise_uuid
                       AND pi.user_id = p.user_id
                       AND pi.status = 'active'
                    WHERE c.telegram_chat_id = :chat_id
                      AND c.telegram_status IN ('ready', 'connected')
                    ORDER BY COALESCE(c.telegram_ready_at_utc, c.created_at_utc) DESC
                    LIMIT 1;
                """),
                {"chat_id": str(chat_id)},
            ).mappings().fetchone()
        return dict(row) if row else None

    async def _cleanup_orphan_processing_message(self, context) -> None:
        """Delete a leftover processing message that was not consumed by handlers."""
        if not context or not hasattr(context, "user_data") or context.user_data is None:
            return
        msg = context.user_data.pop("_processing_msg", None)
        if not msg:
            return
        try:
            await msg.delete()
        except Exception as e:
            logger.debug("cleanup orphan processing message failed: %s", e)

    async def _route_command(self, ctx: InputContext) -> None:
        """Route command to the corresponding MessageHandlers method."""
        handler_name = COMMAND_ROUTE_MAP.get(ctx.command)
        if not handler_name:
            logger.warning("Unknown command: %s", ctx.command)
            return
        handler = getattr(self.message_handlers, handler_name, None)
        if not handler:
            logger.warning("Handler not found for command %s: %s", ctx.command, handler_name)
            return
        await handler(ctx.platform_update, ctx.platform_context)

    async def _route_callback(self, ctx: InputContext) -> None:
        """Delegate callback to CallbackHandlers."""
        if (ctx.callback_data or "").startswith(CLUB_TELEGRAM_CONFIRM_PREFIX):
            await self._handle_club_telegram_confirm_callback(ctx)
            return
        await self.callback_handlers.handle_promise_callback(
            ctx.platform_update, ctx.platform_context
        )

    async def _handle_club_telegram_confirm_callback(self, ctx: InputContext) -> None:
        query = getattr(ctx.platform_update, "callback_query", None)
        if not query:
            return

        if not is_admin(ctx.user_id):
            await query.answer("Only Xaana admins can confirm this.", show_alert=True)
            return

        club_id = (ctx.callback_data or "").replace(CLUB_TELEGRAM_CONFIRM_PREFIX, "", 1).strip()
        if not club_id:
            await query.answer("Missing club id.", show_alert=True)
            return

        confirmed = await self._confirm_pending_club_telegram_link(
            club_id=club_id,
            admin_user_id=ctx.user_id,
            bot_token=os.getenv("BOT_TOKEN", ""),
        )
        if not confirmed:
            await query.answer("Could not confirm. Open Club Setup and link it manually.", show_alert=True)
            return

        await query.answer("Club Telegram group confirmed.")
        text_value = "\n".join([
            "Club Telegram group confirmed.",
            f"Club: {confirmed['club_name']}",
            f"Chat ID: {confirmed['telegram_chat_id']}",
        ])
        try:
            await query.edit_message_text(text=text_value, parse_mode=None)
        except Exception as e:
            logger.debug("Could not edit club Telegram confirmation message: %s", e)

    async def _route_to_agent(self, ctx: InputContext) -> None:
        """Route text to the LLM agent pipeline."""
        await self.message_handlers.handle_message(
            ctx.platform_update, ctx.platform_context
        )

    async def _on_message_edited(self, ctx: InputContext) -> None:
        """Log edited message; update last_seen. No reply."""
        if ctx.user_id:
            await self._log_structured_event(
                event_type="edited_message",
                user_id=ctx.user_id,
                chat_id=ctx.chat_id,
                source_message_id=ctx.message_id,
                content_preview=(ctx.raw_text or "")[:200] if ctx.raw_text else None,
                payload={"raw_text_length": len(ctx.raw_text or "")},
            )

    async def _on_reaction(self, ctx: InputContext) -> None:
        """Log message reaction; update last_seen. No reply (or optional lightweight response later)."""
        if ctx.user_id:
            await self._log_structured_event(
                event_type="message_reaction",
                user_id=ctx.user_id,
                chat_id=ctx.chat_id,
                source_message_id=ctx.metadata.get("message_id"),
                content_preview=None,
                payload=dict(ctx.metadata),
            )

    async def _on_message_pinned(self, ctx: InputContext) -> None:
        """Log pinned message; update last_seen. No reply."""
        if ctx.user_id:
            await self._log_structured_event(
                event_type="pinned_message",
                user_id=ctx.user_id,
                chat_id=ctx.chat_id,
                source_message_id=ctx.message_id,
                content_preview=None,
                payload=dict(ctx.metadata),
            )

    async def _on_chat_member(self, ctx: InputContext) -> None:
        """Handle chat member updates and auto-connect club Telegram links when possible."""
        if ctx.user_id:
            await self._log_structured_event(
                event_type="chat_member",
                user_id=ctx.user_id,
                chat_id=ctx.chat_id,
                source_message_id=None,
                content_preview=None,
                payload=dict(ctx.metadata),
            )

        update = ctx.platform_update
        my_chat_member = getattr(update, "my_chat_member", None)
        if not my_chat_member:
            return

        chat = getattr(my_chat_member, "chat", None)
        if not chat or getattr(chat, "type", None) not in ("group", "supergroup"):
            return

        new_member = getattr(my_chat_member, "new_chat_member", None)
        new_status = getattr(new_member, "status", None)
        if new_status != "administrator":
            return

        old_member = getattr(my_chat_member, "old_chat_member", None)
        old_status = getattr(old_member, "status", None)
        if old_status == "administrator":
            return

        bot = getattr(ctx.platform_context, "bot", None)
        if not bot:
            return

        chat_id = getattr(chat, "id", None)
        chat_title = (getattr(chat, "title", "") or "").strip()
        actor_id = ctx.user_id
        if not chat_id:
            return

        invite_link = None
        try:
            created_invite = await bot.create_chat_invite_link(chat_id=chat_id)
            invite_link = (getattr(created_invite, "invite_link", "") or "").strip()
        except Exception as e:
            logger.warning("Could not create invite link for chat %s: %s", chat_id, e)

        if not invite_link:
            await self._notify_admins_about_group_setup(
                bot=bot,
                message=(
                    "Club group detected but invite-link creation failed.\n"
                    f"Group: \"{chat_title or chat_id}\"\n"
                    f"Chat ID: {chat_id}\n"
                    "Please ensure @xaana_bot has 'Invite users via link' permission."
                ),
            )
            return

        proposed = await self._stage_club_group_candidate(
            chat_id=chat_id,
            chat_title=chat_title,
            actor_user_id=actor_id,
            invite_link=invite_link,
        )

        if proposed:
            setup_state = str(proposed.get("telegram_status") or "")
            intro = (
                "Telegram group detected for an approved club.\n"
                if setup_state == "ready"
                else "Telegram group detected for a pending club.\n"
            )
            await self._notify_admins_about_group_setup(
                bot=bot,
                message=(
                    intro +
                    "Please confirm before Xaana links it.\n"
                    f"Suggested club: \"{proposed.get('club_name', chat_title)}\"\n"
                    f"Group: \"{chat_title or chat_id}\"\n"
                    f"Chat ID: {chat_id}\n"
                    f"Invite: {invite_link}"
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "Confirm club link",
                        callback_data=f"{CLUB_TELEGRAM_CONFIRM_PREFIX}{proposed['club_id']}",
                    )
                ]]),
            )
            return

        await self._notify_admins_about_group_setup(
            bot=bot,
            message=(
                "Group invite link was created but no pending club could be auto-matched.\n"
                f"Group: \"{chat_title or chat_id}\"\n"
                f"Chat ID: {chat_id}\n"
                f"Invite: {invite_link}\n"
                "Please connect it manually in Admin > Clubs Telegram Setup."
            ),
        )

    async def _notify_admins_about_group_setup(self, bot, message: str, reply_markup=None) -> None:
        """Send operational club-group setup updates to configured admins."""
        admin_ids = sorted(get_admin_ids())
        if not admin_ids:
            return
        for admin_id in admin_ids:
            try:
                await bot.send_message(chat_id=admin_id, text=message, reply_markup=reply_markup, parse_mode=None)
            except Exception as e:
                logger.debug("Could not notify admin %s about group setup: %s", admin_id, e)

    async def _stage_club_group_candidate(
        self,
        chat_id: int,
        chat_title: str,
        actor_user_id: int,
        invite_link: str,
    ) -> Optional[dict]:
        """Best-effort mapping from group title to one unlinked club, waiting for admin confirmation."""
        normalized_title = (chat_title or "").strip()
        if not normalized_title:
            return None

        now = utc_now_iso()
        with get_db_session() as session:
            ensure_club_telegram_columns(session)
            club_columns = get_club_columns(session)

            required = {"telegram_status", "telegram_invite_link", "telegram_chat_id"}
            if not required.issubset(club_columns):
                return None

            pending_rows = session.execute(
                text("""
                    SELECT club_id, owner_user_id, name, telegram_status
                    FROM clubs
                    WHERE (
                        telegram_status = 'pending_admin_setup'
                        OR (
                            telegram_status = 'ready'
                            AND NULLIF(trim(COALESCE(telegram_chat_id, '')), '') IS NULL
                        )
                    )
                      AND lower(trim(name)) = lower(trim(:group_name))
                    ORDER BY COALESCE(telegram_requested_at_utc, created_at_utc) DESC;
                """),
                {"group_name": normalized_title},
            ).mappings().fetchall()

            # Only propose an unambiguous exact name match. Admin must still confirm.
            if len(pending_rows) != 1:
                return None

            row = pending_rows[0]
            set_parts = [
                "telegram_invite_link = :invite_link",
                "telegram_chat_id = :telegram_chat_id",
                "updated_at_utc = :updated_at",
            ]
            params = {
                "club_id": str(row["club_id"]),
                "invite_link": invite_link,
                "telegram_chat_id": str(chat_id),
                "updated_at": now,
            }

            if "telegram_setup_by_admin_id" in club_columns and actor_user_id:
                set_parts.append("telegram_setup_by_admin_id = :setup_by_admin_id")
                params["setup_by_admin_id"] = str(actor_user_id)

            session.execute(
                text(f"""
                    UPDATE clubs
                    SET {", ".join(set_parts)}
                    WHERE club_id = :club_id;
                """),
                params,
            )

            return {
                "club_id": str(row["club_id"]),
                "club_name": str(row["name"]),
                "telegram_status": str(row["telegram_status"]),
            }

    async def _confirm_pending_club_telegram_link(
        self,
        club_id: str,
        admin_user_id: int,
        bot_token: str,
    ) -> Optional[dict]:
        """Mark a staged Telegram group candidate as ready after admin confirmation."""
        now = utc_now_iso()
        with get_db_session() as session:
            ensure_club_telegram_columns(session)
            row = session.execute(
                text("""
                    SELECT club_id, owner_user_id, name, telegram_invite_link, telegram_chat_id
                    FROM clubs
                    WHERE club_id = :club_id
                    LIMIT 1;
                """),
                {"club_id": club_id},
            ).mappings().fetchone()
            if not row or not row["telegram_invite_link"] or not row["telegram_chat_id"]:
                return None

            session.execute(
                text("""
                    UPDATE clubs
                    SET telegram_status = 'ready',
                        telegram_ready_at_utc = :ready_at,
                        telegram_setup_by_admin_id = :admin_id,
                        updated_at_utc = :updated_at
                    WHERE club_id = :club_id;
                """),
                {
                    "club_id": club_id,
                    "ready_at": now,
                    "admin_id": str(admin_user_id),
                    "updated_at": now,
                },
            )

            result = {
                "club_id": str(row["club_id"]),
                "club_name": str(row["name"]),
                "owner_user_id": int(row["owner_user_id"]),
                "telegram_invite_link": str(row["telegram_invite_link"]),
                "telegram_chat_id": str(row["telegram_chat_id"]),
            }

        if bot_token:
            asyncio.create_task(
                send_club_telegram_ready_notification(
                    bot_token=bot_token,
                    user_id=result["owner_user_id"],
                    club_name=result["club_name"],
                    invite_link=result["telegram_invite_link"],
                )
            )
        return result

    async def _log_structured_event(
        self,
        event_type: str,
        user_id: int,
        chat_id: int,
        source_message_id: Optional[int],
        content_preview: Optional[str],
        payload: dict,
    ) -> None:
        """Log a structured event for non-text interactions (edits, reactions, pins, chat_member)."""
        from datetime import datetime
        try:
            settings = await self.plan_keeper.async_get_settings(user_id)
            if hasattr(settings, "last_seen"):
                settings.last_seen = datetime.now()
                await self.plan_keeper.async_save_settings(settings)
        except Exception as e:
            logger.debug("Could not update last_seen for event %s: %s", event_type, e)
        event_content = f"[{event_type}]"
        if content_preview:
            event_content += " " + content_preview[:100]
        try:
            await asyncio.to_thread(
                lambda: self._original_response_service.log_user_message(
                    user_id=user_id,
                    content=event_content,
                    message_id=source_message_id,
                    chat_id=chat_id,
                )
            )
        except Exception as e:
            logger.warning("Could not log structured event %s: %s", event_type, e)

    def _register_handlers(self) -> None:
        """Register all command and message handlers. All inputs land on dispatch()."""
        # All commands go through central dispatch
        for cmd in COMMAND_ROUTE_MAP:
            self.application.add_handler(CommandHandler(cmd, self.dispatch))

        # Message handlers (text, location, voice, image, poll) -> dispatch
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.dispatch)
        )
        self.application.add_handler(MessageHandler(filters.LOCATION, self.dispatch))
        self.application.add_handler(MessageHandler(filters.VOICE, self.dispatch))
        self.application.add_handler(
            MessageHandler(
                filters.PHOTO | (filters.Document.MimeType("image/")),
                self.dispatch,
            )
        )
        self.application.add_handler(MessageHandler(filters.POLL, self.dispatch))

        # Edited messages -> dispatch
        self.application.add_handler(
            MessageHandler(filters.UpdateType.EDITED_MESSAGE, self.dispatch)
        )
        # Pinned message (service message) -> dispatch
        self.application.add_handler(
            MessageHandler(filters.StatusUpdate.PINNED_MESSAGE, self.dispatch)
        )
        self.application.add_handler(
            MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, self.dispatch)
        )
        self.application.add_handler(
            MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, self.dispatch)
        )

        # Callback query handler -> dispatch
        self.application.add_handler(CallbackQueryHandler(self.dispatch))

        # Poll answers (when users vote) -> dispatch
        from telegram.ext import PollAnswerHandler
        self.application.add_handler(PollAnswerHandler(self.dispatch))

        # Message reactions -> dispatch
        from telegram.ext import MessageReactionHandler
        self.application.add_handler(MessageReactionHandler(self.dispatch))

        # Chat member updates -> dispatch
        from telegram.ext import ChatMemberHandler
        self.application.add_handler(ChatMemberHandler(self.dispatch, ChatMemberHandler.MY_CHAT_MEMBER))
        self.application.add_handler(ChatMemberHandler(self.dispatch, ChatMemberHandler.CHAT_MEMBER))

        # “Todo list” style texts (checkboxes / markdown lists)
        # Option A: keep your general TEXT handler and route inside it
        # # Option B: add a thin filter for todo-like lines:
        # from telegram.ext import MessageFilter
        # class TodoFilter(MessageFilter):
        #     def filter(self, message) -> bool:
        #         t = (message.text or "").strip()
        #         if not t: return False
        #         # Common todo patterns: Markdown checkboxes or checkbox emojis
        #         return any(p in t for p in ("- [ ]", "- [x]", "☐", "✅", "☑️"))
        # todo_filter = TodoFilter()
        # self.application.add_handler(MessageHandler(todo_filter & ~filters.COMMAND, self.message_handlers.on_todo_text))

    def get_user_timezone(self, user_id: int) -> str:
        """Get user timezone using the settings repository."""
        return BotUtils.get_user_timezone(self.plan_keeper, user_id)

    def set_user_timezone(self, user_id: int, tzname: str) -> None:
        """Set user timezone using the settings repository."""
        BotUtils.set_user_timezone(self.plan_keeper, user_id, tzname)

    def bootstrap_schedule_existing_users(self) -> None:
        """
        On bot startup, (re)schedule reminder jobs for all existing users.
        
        Source of truth is PostgreSQL (users table). The prior filesystem scan was legacy
        (older SQLite/YAML versions created per-user directories). With PostgreSQL, many
        users may not have a directory, so scanning root_dir would miss them and reminders
        would not be scheduled.
        """
        job_scheduler = self.platform_adapter.job_scheduler
        
        # Fetch user ids from Postgres (user_id stored as TEXT)
        user_ids: list[int] = []
        try:
            from sqlalchemy import text
            from db.postgres_db import get_db_session

            with get_db_session() as session:
                rows = session.execute(
                    text("SELECT user_id FROM users WHERE timezone IS DISTINCT FROM 'DISABLED';")
                ).fetchall()

            for r in rows:
                try:
                    user_ids.append(int(r[0]))
                except Exception:
                    continue

            logger.info(f"bootstrap_schedule_existing_users: found {len(user_ids)} users in DB")
        except Exception as e:
            logger.exception(f"bootstrap_schedule_existing_users: failed to fetch users from DB: {e}")
            return

        # Schedule per-user jobs. If one user fails, continue.
        scheduled_count = 0
        is_quiet_mode = _is_staging_or_test_mode()
        if is_quiet_mode:
            logger.info(
                "bootstrap_schedule_existing_users: quiet mode enabled (staging/test); per-user scheduler logs suppressed"
            )
        for user_id in user_ids:
            try:
                tzname = self.get_user_timezone(user_id) or "UTC"
                logger.debug(f"bootstrap: scheduling reminders for user {user_id} (tz: {tzname})")

                if self.message_handlers:
                    # Morning reminders
                    job_scheduler.schedule_daily(
                        user_id=user_id,
                        tz=tzname,
                        callback=self.message_handlers.scheduled_morning_reminders_for_one,
                        hh=8,
                        mm=30,
                        name_prefix="morning",
                    )

                    # Noon cleanup
                    job_scheduler.schedule_daily(
                        user_id=user_id,
                        tz=tzname,
                        callback=self.message_handlers.scheduled_noon_cleanup_for_one,
                        hh=12,
                        mm=0,
                        name_prefix="noon_cleanup",
                    )

                    # Nightly reminders
                    job_scheduler.schedule_daily(
                        user_id=user_id,
                        tz=tzname,
                        callback=self.message_handlers.scheduled_nightly_reminders_for_one,
                        hh=22,
                        mm=59,
                        name_prefix="nightly",
                    )
                    scheduled_count += 1
                    if is_quiet_mode:
                        if scheduled_count % 100 == 0:
                            logger.info(
                                "bootstrap_schedule_existing_users: progress %s/%s users scheduled",
                                scheduled_count,
                                len(user_ids),
                            )
                    else:
                        logger.info(f"bootstrap: scheduled all reminders for user {user_id} (tz: {tzname})")
            except Exception as e:
                logger.exception(f"bootstrap_schedule_existing_users: failed scheduling for user {user_id}: {e}")
                continue
        
        logger.info(f"bootstrap_schedule_existing_users: successfully scheduled reminders for {scheduled_count}/{len(user_ids)} users")

    def run(self) -> None:
        """
        Start the bot. For Telegram this runs polling; for other platforms, their event loop.
        """
        try:
            if hasattr(self.platform_adapter, "application"):
                # Request update types needed for dispatch (messages, edits, reactions, pins, chat_member)
                allowed = [
                    "message", "edited_message", "channel_post", "edited_channel_post",
                    "callback_query", "poll", "poll_answer",
                    "my_chat_member", "chat_member",
                    "message_reaction", "message_reaction_count",
                ]
                logger.info("run_polling with allowed_updates: %s", allowed)
                self.application.run_polling(allowed_updates=allowed)
            else:
                asyncio.run(self.platform_adapter.start())
        except BaseException as e:
            logger.exception("Bot run loop failed: %s", e)
            raise


def main():
    """Main entry point for the bot."""
    from dotenv import load_dotenv
    load_dotenv()

    ROOT_DIR = os.getenv("ROOT_DIR")
    if not ROOT_DIR:
        logger.error("ROOT_DIR environment variable is not set")
        raise ValueError("ROOT_DIR environment variable is required")
    
    # In Docker, ROOT_DIR should already be an absolute path
    # For local development, resolve it
    if not os.path.isabs(ROOT_DIR):
        try:
            ROOT_DIR = os.path.abspath(subprocess.check_output(f'echo {ROOT_DIR}', shell=True).decode().strip())
        except Exception:
            ROOT_DIR = os.path.abspath(ROOT_DIR)
    
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable is not set")
        raise ValueError("BOT_TOKEN environment variable is required")
    configure_admin_error_notifications(bot_token=BOT_TOKEN)

    MINIAPP_URL = os.getenv("MINIAPP_URL", "https://xaana.club")

    # Optional Sentry initialization (if DSN is provided). Web app has its own Sentry if needed.
    SENTRY_DSN = os.getenv("SENTRY_DSN")
    if SENTRY_DSN:
        try:
            import sentry_sdk  # pylint: disable=import-error
            from sentry_sdk.integrations.logging import LoggingIntegration  # pylint: disable=import-error
            import logging as std_logging
            sentry_logging = LoggingIntegration(
                level=std_logging.INFO,  # capture >= INFO as breadcrumbs
                event_level=std_logging.ERROR  # send >= ERROR as full Sentry events
            )
            sentry_sdk.init(
                dsn=SENTRY_DSN,
                send_default_pii=True,
                integrations=[sentry_logging],
                traces_sample_rate=1.0,
            )
            logger.info("Sentry initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize Sentry (optional): {str(e)}")

    # Configure httpx logger to reduce noise
    import logging as std_logging
    httpx_logger = std_logging.getLogger("httpx")
    httpx_logger.setLevel(std_logging.WARNING)
    
    # Configure apscheduler logger to reduce noise
    apscheduler_logger = std_logging.getLogger("apscheduler.scheduler")
    apscheduler_logger.setLevel(std_logging.WARNING)

    logger.info(f"Starting Xaana AI bot with ROOT_DIR={ROOT_DIR}")

    # Create Telegram platform adapter
    request = HTTPXRequest(connect_timeout=10, read_timeout=20)
    application = Application.builder().token(BOT_TOKEN).request(request).concurrent_updates(True).build()

    async def error_handler(update, context):
        err = context.error
        if isinstance(err, telegram_error.NetworkError):
            logger.warning("Telegram network error (will retry): %s", err)
            return
        if isinstance(err, SQLOperationalError):
            logger.warning("Database connection error (check Cloud SQL / authorized networks): %s", err)
            return
        logger.exception("Update %s caused error %s", update, err)

    application.add_error_handler(error_handler)

    # Create plan_keeper first to get settings_repo
    plan_keeper = PlannerAPIAdapter(ROOT_DIR)
    
    # Initialize response service with settings_repo
    response_service = ResponseService(
        settings_repo=plan_keeper.settings_repo
    )
    
    # Create platform adapter
    platform_adapter = TelegramPlatformAdapter(application, response_service)
    
    # Create and run bot
    bot = PlannerBot(platform_adapter, ROOT_DIR, MINIAPP_URL)
    
    try:
        # Bootstrap can take a while for large user bases; run it in the background so
        # polling starts immediately. Set BOOTSTRAP_SCHEDULER_SYNC=1 to keep old behavior.
        if os.getenv("BOOTSTRAP_SCHEDULER_SYNC", "0") == "1":
            bot.bootstrap_schedule_existing_users()
        else:
            def _bootstrap_wrapper() -> None:
                try:
                    bot.bootstrap_schedule_existing_users()
                except Exception as exc:
                    logger.exception("bootstrap background thread failed: %s", exc)

            bootstrap_thread = threading.Thread(
                target=_bootstrap_wrapper,
                name="bootstrap-scheduler",
                daemon=True,
            )
            bootstrap_thread.start()
            logger.info("bootstrap_schedule_existing_users: started background bootstrap thread")

        bot.run()
    except BaseException as e:
        logger.exception("Planner bot failed: %s", e)
        raise

    logger.info("Planner bot stopped normally")


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise  # allow sys.exit() to pass through
    except KeyboardInterrupt:
        logger.info("Planner bot interrupted by user")
        sys.exit(0)
    except BaseException as e:
        logger.exception("Unhandled exception in planner bot: %s", e)
        sys.exit(1)
