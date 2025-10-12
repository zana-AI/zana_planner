"""
Refactored Telegram bot for the planner application.
This version uses separated concerns with internationalization support.
"""
import datetime
import os
import subprocess
import logging
import logging.config

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
from utils.bot_utils import BotUtils
from infra.scheduler import schedule_user_daily

logger = logging.getLogger(__name__)


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

        # Store plan_keeper in bot_data for access by handlers
        self.application.bot_data['plan_keeper'] = self.plan_keeper

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

        # Message handlers
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handlers.handle_message))
        self.application.add_handler(MessageHandler(filters.LOCATION, self.message_handlers.on_location_shared))

        # Callback query handler
        self.application.add_handler(CallbackQueryHandler(self.callback_handlers.handle_promise_callback))

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
                hh=now.hour, mm=now.minute + 1, name_prefix="noon_cleanup",
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
    ROOT_DIR = os.path.abspath(subprocess.check_output(f'echo {ROOT_DIR}', shell=True).decode().strip())
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    LOG_FILE = os.getenv("LOG_FILE", os.path.abspath(os.path.join(__file__, '../..', 'bot.log')))

    # Enable logging
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            },
        },
        'handlers': {
            'default': {
                'level': 'INFO',
                'formatter': 'standard',
                'class': 'logging.StreamHandler',
            },
            'file': {
                'level': 'INFO',
                'formatter': 'standard',
                'class': 'logging.FileHandler',
                'filename': LOG_FILE,
                'mode': 'a',
            },
        },
        'loggers': {
            '': {  # root logger
                'handlers': ['default', 'file'],
                'level': 'INFO',
                'propagate': True
            },
            'httpx': {  # httpx logger
                'handlers': ['default', 'file'],
                'level': 'WARNING',
                'propagate': True
            }
        }
    })

    # Create and run bot
    bot = PlannerTelegramBot(BOT_TOKEN, ROOT_DIR)
    bot.bootstrap_schedule_existing_users()
    bot.run()


if __name__ == '__main__':
    main()
