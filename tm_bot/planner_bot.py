"""
Refactored Telegram bot for the planner application.
This version uses separated concerns with internationalization support.
"""
import asyncio
import datetime
import os
import subprocess
import threading
from typing import Optional

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
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
from infra.scheduler import schedule_user_daily
from utils.logger import get_logger
from utils.version import get_version_info

logger = get_logger(__name__)

class PlannerTelegramBot:
    """Main Telegram bot class with separated concerns."""

    def __init__(self, token: str, root_dir: str):
        # Initialize core components
        request = HTTPXRequest(connect_timeout=10, read_timeout=20)
        self.application = Application.builder().token(token).request(request).build()
        self.llm_handler = LLMHandler()
        self.plan_keeper = PlannerAPIAdapter(root_dir)
        self.root_dir = root_dir
        self.token = token
        # self.webapp_server: Optional[threading.Thread] = None  # Web app disabled

        # Initialize ResponseService
        self.response_service = ResponseService(
            root_dir=self.root_dir,
            settings_repo=self.plan_keeper.settings_repo
        )

        # Initialize handlers
        self.message_handlers = MessageHandlers(
            self.plan_keeper,
            self.llm_handler,
            self.root_dir,
            self.application,
            self.response_service
        )
        self.callback_handlers = CallbackHandlers(
            self.plan_keeper,
            self.application,
            self.response_service
        )

        # Store plan_keeper, llm_handler, and response_service in bot_data for access by handlers
        self.application.bot_data['plan_keeper'] = self.plan_keeper
        self.application.bot_data['llm_handler'] = self.llm_handler
        self.application.bot_data['response_service'] = self.response_service
        
        # Set LLM handler in plan_keeper for time estimation service
        self.plan_keeper.set_llm_handler(self.llm_handler)

        # Initialize message store with settings repository
        initialize_message_store(self.plan_keeper.settings_repo)

        # Register all handlers
        self._register_handlers()

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
        jq = self.application.job_queue

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
            schedule_user_daily(
                jq, user_id=user_id, tz=tzname,
                callback=self.message_handlers.scheduled_morning_reminders_for_one,
                hh=8, mm=30, name_prefix="morning",
            )

            now = datetime.datetime.now()
            # Schedule noon cleanup 
            schedule_user_daily(
                jq, user_id=user_id, tz=tzname,
                callback=self.message_handlers.scheduled_noon_cleanup_for_one,
                # hh=23, mm=2, name_prefix="noon_cleanup",
                hh=12, mm=00, name_prefix="noon_cleanup",
            )

            # Schedule nightly reminders
            schedule_user_daily(
                jq, user_id=user_id, tz=tzname,
                callback=self.message_handlers.scheduled_nightly_reminders_for_one,
                hh=22, mm=59, name_prefix="nightly",
            )

    # Web app server disabled - commented out to prevent issues with Telegram bot
    # def _start_webapp_server(self, host: str = "0.0.0.0", port: int = 8080) -> None:
    #     """Start the FastAPI web app server in a background thread."""
    #     try:
    #         import uvicorn
    #         from webapp.api import create_webapp_api
    #         
    #         # Determine static files directory (React build output)
    #         static_dir = os.path.join(os.path.dirname(__file__), "..", "webapp_frontend", "dist")
    #         if not os.path.isdir(static_dir):
    #             static_dir = None
    #             logger.info("Web app static files not found, API-only mode")
    #         else:
    #             logger.info(f"Serving web app static files from {static_dir}")
    #         
    #         # Create FastAPI app
    #         webapp = create_webapp_api(
    #             root_dir=self.root_dir,
    #             bot_token=self.token,
    #             static_dir=static_dir
    #         )
    #         
    #         # Run uvicorn in a separate thread
    #         config = uvicorn.Config(
    #             webapp,
    #             host=host,
    #             port=port,
    #             log_level="info",
    #             access_log=True
    #         )
    #         server = uvicorn.Server(config)
    #         
    #         def run_server():
    #             asyncio.run(server.serve())
    #         
    #         self.webapp_server = threading.Thread(target=run_server, daemon=True)
    #         self.webapp_server.start()
    #         logger.info(f"Web app server started on http://{host}:{port}")
    #         
    #     except ImportError as e:
    #         logger.warning(f"Web app server dependencies not installed: {e}")
    #     except Exception as e:
    #         logger.error(f"Failed to start web app server: {e}")

    def run(self, enable_webapp: bool = True, webapp_port: int = 8080) -> None:
        """
        Start the bot and optionally the web app server.
        
        Args:
            enable_webapp: Whether to start the FastAPI web app server (currently disabled)
            webapp_port: Port for the web app server (default: 8080, currently unused)
        """
        # Web app server disabled - commented out to prevent issues
        # if enable_webapp:
        #     self._start_webapp_server(port=webapp_port)
        
        # Start Telegram bot polling (blocking)
        self.application.run_polling()


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

    # Web app configuration - DISABLED
    # WEBAPP_ENABLED = os.getenv("WEBAPP_ENABLED", "false").lower() in ("true", "1", "yes")  # Disabled by default
    # WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8080"))

    # Create and run bot
    bot = PlannerTelegramBot(BOT_TOKEN, ROOT_DIR)
    bot.bootstrap_schedule_existing_users()
    logger.debug(f"Starting telegram bot")
    # logger.debug(f"Web app enabled: {WEBAPP_ENABLED} | Web app port: {WEBAPP_PORT}")  # Web app disabled
    bot.run(enable_webapp=False, webapp_port=8080)  # Web app disabled - always False


if __name__ == '__main__':
    main()
