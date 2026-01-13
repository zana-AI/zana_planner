"""
Refactored bot for the planner application.
This version uses platform abstraction to support multiple platforms (Telegram, Discord, etc.).
"""
import asyncio
import os
import subprocess
import threading
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
                    root_dir=self.root_dir,
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
        On bot startup, (re)schedule nightly jobs for all existing users found under root_dir.
        Safe to run multiple times; it removes any prior job with the same name first.
        """
        job_scheduler = self.platform_adapter.job_scheduler

        for entry in os.listdir(self.root_dir):
            user_path = os.path.join(self.root_dir, entry)
            if not os.path.isdir(user_path):
                continue

            try:
                user_id = int(entry)
            except ValueError:
                continue

            tzname = self.get_user_timezone(user_id) or "UTC"

            # Schedule morning reminders
            if self.message_handlers:
                job_scheduler.schedule_daily(
                    user_id=user_id, tz=tzname,
                    callback=self.message_handlers.scheduled_morning_reminders_for_one,
                    hh=8, mm=30, name_prefix="morning",
                )

                # Schedule noon cleanup 
                job_scheduler.schedule_daily(
                    user_id=user_id, tz=tzname,
                    callback=self.message_handlers.scheduled_noon_cleanup_for_one,
                    hh=12, mm=00, name_prefix="noon_cleanup",
                )

                # Schedule nightly reminders
                job_scheduler.schedule_daily(
                    user_id=user_id, tz=tzname,
                    callback=self.message_handlers.scheduled_nightly_reminders_for_one,
                    hh=22, mm=59, name_prefix="nightly",
                )

    def _start_webapp_server(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        """Start the FastAPI web app server in a background thread."""
        logger.info(f"[DEBUG] Starting webapp server on {host}:{port}")
        try:
            import uvicorn
            from webapp.api import create_webapp_api
            
            # Determine static files directory (React build output)
            static_dir = os.path.join(os.path.dirname(__file__), "..", "webapp_frontend", "dist")
            if not os.path.isdir(static_dir):
                static_dir = None
                logger.info("Web app static files not found, API-only mode")
            else:
                logger.info(f"Serving web app static files from {static_dir}")
            
            # Get bot token from environment variable
            bot_token = os.getenv("BOT_TOKEN")
            if not bot_token:
                logger.error("BOT_TOKEN environment variable is not set, cannot start webapp server")
                return
            
            logger.info("[DEBUG] Creating FastAPI app...")
            # Create FastAPI app
            webapp = create_webapp_api(
                root_dir=self.root_dir,
                bot_token=bot_token,
                static_dir=static_dir
            )
            
            logger.info("[DEBUG] Starting uvicorn server...")
            # Run uvicorn in a separate thread
            config = uvicorn.Config(
                webapp,
                host=host,
                port=port,
                log_level="info",
                access_log=True
            )
            server = uvicorn.Server(config)
            
            def run_server():
                try:
                    asyncio.run(server.serve())
                except Exception as e:
                    logger.error(f"[DEBUG] Exception in uvicorn thread: {e}", exc_info=True)
            
            self.webapp_server = threading.Thread(target=run_server, daemon=True)
            self.webapp_server.start()
            logger.info(f"Web app server started on http://{host}:{port}")
            
        except ImportError as e:
            logger.warning(f"Web app server dependencies not installed: {e}")
        except Exception as e:
            logger.error(f"Failed to start web app server: {e}", exc_info=True)

    def run(self, enable_webapp: bool = True, webapp_port: int = 8080) -> None:
        """
        Start the bot and optionally the web app server.
        
        Args:
            enable_webapp: Whether to start the FastAPI web app server
            webapp_port: Port for the web app server (default: 8080)
        """
        logger.info(f"[DEBUG] run() called with enable_webapp={enable_webapp}, webapp_port={webapp_port}")
        if enable_webapp:
            self._start_webapp_server(port=webapp_port)
        
        # Start platform bot (blocking)
        # For Telegram, this calls application.run_polling()
        # For other platforms, this will start their respective event loops
        if hasattr(self.platform_adapter, 'application'):
            # Telegram-specific: use run_polling for backward compatibility
            self.application.run_polling()
        else:
            # For other platforms, use async start
            import asyncio
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

    # Optional Sentry initialization (if DSN is provided)
    SENTRY_DSN = os.getenv("SENTRY_DSN")
    if SENTRY_DSN:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.logging import LoggingIntegration
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            import logging as std_logging
            sentry_logging = LoggingIntegration(
                level=std_logging.INFO,  # capture >= INFO as breadcrumbs
                event_level=std_logging.ERROR  # send >= ERROR as full Sentry events
            )
            sentry_sdk.init(
                dsn=SENTRY_DSN,
                send_default_pii=True,
                integrations=[sentry_logging, FastApiIntegration()],
                traces_sample_rate=1.0
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

    logger.info(f"Starting Zana AI bot with ROOT_DIR={ROOT_DIR}")

    # Web app configuration
    WEBAPP_ENABLED = os.getenv("WEBAPP_ENABLED", "false").lower() in ("true", "1", "yes")
    WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8080"))

    # Create Telegram platform adapter
    request = HTTPXRequest(connect_timeout=10, read_timeout=20)
    application = Application.builder().token(BOT_TOKEN).request(request).build()
    
    # Create plan_keeper first to get settings_repo
    plan_keeper = PlannerAPIAdapter(ROOT_DIR)
    
    # Initialize response service with settings_repo
    response_service = ResponseService(
        root_dir=ROOT_DIR,
        settings_repo=plan_keeper.settings_repo
    )
    
    # Create platform adapter
    platform_adapter = TelegramPlatformAdapter(application, response_service)
    
    # Create and run bot
    bot = PlannerBot(platform_adapter, ROOT_DIR, MINIAPP_URL)
    
    bot.bootstrap_schedule_existing_users()
    logger.debug(f"Starting bot with platform adapter")
    bot.run(enable_webapp=WEBAPP_ENABLED, webapp_port=WEBAPP_PORT)


if __name__ == '__main__':
    main()
