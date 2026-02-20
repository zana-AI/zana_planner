"""
Refactored bot for the planner application.
This version uses platform abstraction to support multiple platforms (Telegram, Discord, etc.).
The web app runs as a separate process; this module runs the Telegram (or other platform) bot only.
"""
import asyncio
import os
import subprocess
import sys
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
from telegram import error as telegram_error
from sqlalchemy.exc import OperationalError as SQLOperationalError

from llms.llm_handler import LLMHandler
from services.planner_api_adapter import PlannerAPIAdapter
from services.response_service import ResponseService
from handlers.message_handlers import MessageHandlers
from handlers.callback_handlers import CallbackHandlers
from handlers.messages_store import initialize_message_store, get_user_language
from router_types import InputContext
from utils.bot_utils import BotUtils
from utils.logger import get_logger

logger = get_logger(__name__)

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

            if getattr(msg, "pinned_message", None):
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
        ctx = self._build_input_context(update, context)
        if context and hasattr(context, "user_data") and context.user_data is not None:
            context.user_data["_input_context"] = ctx

        # Cross-cutting: update user info and avatar (for any input with a user)
        effective_user = self._get_effective_user(update)
        if ctx.user_id and effective_user:
            self.message_handlers._update_user_info(ctx.user_id, effective_user)
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

        # Ack policy: send "Thinking..." only for LLM-bound types when response will be editable text
        processing_msg = None
        llm_bound = ctx.input_type in ("text", "voice", "image")
        if llm_bound and ctx.user_id:
            settings = self.plan_keeper.settings_service.get_settings(ctx.user_id)
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

        logger.warning("dispatch: unhandled input_type=%s", ctx.input_type)
        await self._route_to_agent(ctx)

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
        await self.callback_handlers.handle_promise_callback(
            ctx.platform_update, ctx.platform_context
        )

    async def _route_to_agent(self, ctx: InputContext) -> None:
        """Route text to the LLM agent pipeline."""
        await self.message_handlers.handle_message(
            ctx.platform_update, ctx.platform_context
        )

    async def _on_message_edited(self, ctx: InputContext) -> None:
        """Log edited message; update last_seen. No reply."""
        if ctx.user_id:
            self._log_structured_event(
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
            self._log_structured_event(
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
            self._log_structured_event(
                event_type="pinned_message",
                user_id=ctx.user_id,
                chat_id=ctx.chat_id,
                source_message_id=ctx.message_id,
                content_preview=None,
                payload=dict(ctx.metadata),
            )

    async def _on_chat_member(self, ctx: InputContext) -> None:
        """Log chat member update; update last_seen. No reply."""
        if ctx.user_id:
            self._log_structured_event(
                event_type="chat_member",
                user_id=ctx.user_id,
                chat_id=ctx.chat_id,
                source_message_id=None,
                content_preview=None,
                payload=dict(ctx.metadata),
            )

    def _log_structured_event(
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
            settings = self.plan_keeper.settings_service.get_settings(user_id)
            if hasattr(settings, "last_seen"):
                settings.last_seen = datetime.now()
                self.plan_keeper.settings_service.save_settings(settings)
        except Exception as e:
            logger.debug("Could not update last_seen for event %s: %s", event_type, e)
        event_content = f"[{event_type}]"
        if content_preview:
            event_content += " " + content_preview[:100]
        try:
            self._original_response_service.log_user_message(
                user_id=user_id,
                content=event_content,
                message_id=source_message_id,
                chat_id=chat_id,
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
                rows = session.execute(text("SELECT user_id FROM users;")).fetchall()

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
                    logger.info(f"bootstrap: ✓ scheduled all reminders for user {user_id} (tz: {tzname})")
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
    application = Application.builder().token(BOT_TOKEN).request(request).build()

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
        bot.bootstrap_schedule_existing_users()
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
