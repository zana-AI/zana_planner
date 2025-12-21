"""
Refactored Telegram bot for the planner application.
This version uses separated concerns with internationalization support.
"""
import datetime
import os
import subprocess

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
        self.application = Application.builder().token(token).build()
        self.llm_handler = LLMHandler()
        self.plan_keeper = PlannerAPIAdapter(root_dir)
        self.root_dir = root_dir

        # Initialize handlers
        self.message_handlers = MessageHandlers(
            self.plan_keeper,
            self.llm_handler,
            self.root_dir,
            self.application
        )
        self.callback_handlers = CallbackHandlers(
            self.plan_keeper,
            self.application
        )

        # Store plan_keeper and llm_handler in bot_data for access by handlers
        self.application.bot_data['plan_keeper'] = self.plan_keeper
        self.application.bot_data['llm_handler'] = self.llm_handler
        
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
        self.application.add_handler(CommandHandler("promises", self.message_handlers.list_promises))
        self.application.add_handler(CommandHandler("nightly", self.message_handlers.nightly_reminders))
        self.application.add_handler(CommandHandler("morning", self.message_handlers.morning_reminders))
        self.application.add_handler(CommandHandler("weekly", self.message_handlers.weekly_report))
        self.application.add_handler(CommandHandler("zana", self.message_handlers.plan_by_zana))
        self.application.add_handler(CommandHandler("pomodoro", self.message_handlers.pomodoro))
        self.application.add_handler(CommandHandler("settimezone", self.message_handlers.cmd_settimezone))
        self.application.add_handler(CommandHandler("language", self.message_handlers.cmd_language))
        self.application.add_handler(CommandHandler("version", self.message_handlers.cmd_version))

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

            # Make it idempotent
            job_name = f"nightly-{user_id}"
            for j in jq.get_jobs_by_name(job_name):
                j.schedule_removal()

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

    def run(self) -> None:
        """Start the bot."""
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

    logger.info(f"Starting Zana AI bot with ROOT_DIR={ROOT_DIR}")

    # Create and run bot
    bot = PlannerTelegramBot(BOT_TOKEN, ROOT_DIR)
    bot.bootstrap_schedule_existing_users()
    bot.run()


if __name__ == '__main__':
    main()
