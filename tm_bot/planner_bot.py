"""
Refactored bot for the planner application.
This version uses platform abstraction to support multiple platforms (Telegram, Discord, etc.).
The web app runs as a separate process; this module runs the Telegram (or other platform) bot only.
"""
import asyncio
import os
import subprocess
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

from llms.llm_handler import LLMHandler
from services.planner_api_adapter import PlannerAPIAdapter
from services.response_service import ResponseService
from handlers.message_handlers import MessageHandlers
from handlers.callback_handlers import CallbackHandlers
from handlers.messages_store import initialize_message_store
from utils.bot_utils import BotUtils
from utils.logger import get_logger

logger = get_logger(__name__)

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
        
        # For CLI adapter, set handlers so it can process input
        if hasattr(platform_adapter, 'set_handlers') and self.message_handlers:
            platform_adapter.set_handlers(self.message_handlers, self.callback_handlers)

    def _register_handlers(self) -> None:
        """Register all command and message handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.message_handlers.start))
        self.application.add_handler(CommandHandler("me", self.message_handlers.cmd_me))
        self.application.add_handler(CommandHandler("promises", self.message_handlers.list_promises))
        self.application.add_handler(CommandHandler("nightly", self.message_handlers.nightly_reminders))
        self.application.add_handler(CommandHandler("morning", self.message_handlers.morning_reminders))
        self.application.add_handler(CommandHandler("weekly", self.message_handlers.weekly_report))
        self.application.add_handler(CommandHandler("zana", self.message_handlers.plan_by_zana))
        self.application.add_handler(CommandHandler("pomodoro", self.message_handlers.pomodoro))
        self.application.add_handler(CommandHandler("settimezone", self.message_handlers.cmd_settimezone))
        self.application.add_handler(CommandHandler("language", self.message_handlers.cmd_language))
        self.application.add_handler(CommandHandler("version", self.message_handlers.cmd_version))
        self.application.add_handler(CommandHandler("broadcast", self.message_handlers.cmd_broadcast))
        self.application.add_handler(CommandHandler("club", self.message_handlers.cmd_club))
        self.application.add_handler(CommandHandler("admin", self.message_handlers.cmd_admin))

        # Message handlers
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handlers.handle_message))
        self.application.add_handler(MessageHandler(filters.LOCATION, self.message_handlers.on_location_shared))

        # Callback query handler
        self.application.add_handler(CallbackQueryHandler(self.callback_handlers.handle_promise_callback))

        # Voice messages (PTT / voice notes)
        self.application.add_handler(MessageHandler(filters.VOICE, self.message_handlers.on_voice))

        # Images (photos + image docs like PNG/JPG sent as files)
        self.application.add_handler(MessageHandler(filters.PHOTO | (filters.Document.MimeType("image/")),
                self.message_handlers.on_image))

        # Polls (receive poll messages in chats)
        self.application.add_handler(MessageHandler(filters.POLL, self.message_handlers.on_poll_created))

        # Poll answers (when users vote)
        from telegram.ext import PollAnswerHandler
        self.application.add_handler(PollAnswerHandler(self.message_handlers.on_poll_answer))

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
        The web app is run separately (e.g. via run_server.py or another process).
        """
        if hasattr(self.platform_adapter, "application"):
            self.application.run_polling()
        else:
            asyncio.run(self.platform_adapter.start())


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
            import sentry_sdk
            from sentry_sdk.integrations.logging import LoggingIntegration
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
        if isinstance(context.error, telegram_error.NetworkError):
            logger.warning("Telegram network error (will retry): %s", context.error)
            return
        logger.exception("Update %s caused error %s", update, context.error)

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
    
    bot.bootstrap_schedule_existing_users()
    bot.run()


if __name__ == '__main__':
    main()
