import os
import csv
from urllib.parse import uses_relative
import asyncio
from datetime import datetime
import yaml
import logging
import logging.config

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    filters,
    CallbackQueryHandler,
)
from telegram.request import HTTPXRequest
from llm_handler import LLMHandler
from planner_api import PlannerAPI


class PlannerAPIBot:
    def __init__(self, token: str):
        request = HTTPXRequest(connect_timeout=10, read_timeout=20)
        self.application = Application.builder().token(token).build()
        self.llm_handler = LLMHandler()  # Instantiate the LLM handler
        self.plan_keeper = PlannerAPI(ROOT_DIR)  # Instantiate the PlannerAPI class

        # Register handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("promises", self.list_promises))  # Add list_promises command handler
        self.application.add_handler(CommandHandler("nightly", self.nightly_reminders))  # Add nightly command handler
        self.application.add_handler(CommandHandler("weekly", self.weekly_report))  # Add weekly command handler
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(CallbackQueryHandler(self.handle_time_selection))

        # try:
        #     # Schedule nightly reminders if job queue is available
        #     if self.application.job_queue:
        #         self.application.job_queue.run_daily(
        #             self.send_nightly_reminders,
        #             time=time(22, 59),  # 11:15 PM
        #             days=(0, 1, 2, 3, 4, 5, 6)  # Run every day
        #         )
        #     else:
        #         logger.warning("JobQueue not available. Install PTB with job-queue extra to use scheduled reminders.")
        # except Exception as e:
        #     logger.error(f"Failed to set up job queue: {str(e)}")

    async def handle_time_selection(self, update: Update, context: CallbackContext) -> None:
        """Handle the callback when user selects time spent."""
        query = update.callback_query
        await query.answer()
        
        # Parse the callback data (format: "time_spent:promise_id:hours")
        _, promise_id, hours = query.data.split(":")
        
        # Add the action using PlannerAPI
        current_date = datetime.now()
        self.plan_keeper.add_action(
            user_id=query.from_user.id,
            date=current_date.date(),
            time=current_date.strftime("%H:%M"),
            promise_id=promise_id,
            time_spent=float(hours)
        )
        
        await query.edit_message_text(
            text=f"Recorded {hours} hours spent on your promise.",
            parse_mode='Markdown'
        )

    def create_time_options(self, promise_id: str, hours_per_day: float):
        """Create inline keyboard with time options."""
        def format_time_option(hours):
            if hours == 0:
                return "0 hrs", "🚫"
            elif hours < 1:
                minutes = round(hours * 60 / 5) * 5
                return f"{minutes} min", "⏳"
            else:
                rounded_hours = round(hours * 2) / 2  # Round to nearest 0.5 hours
                return f"{rounded_hours:.1f} hrs", "🎉"

        time_options = [0, hours_per_day * 0.5, hours_per_day, hours_per_day * 1.5, hours_per_day * 2, hours_per_day * 2.5]
        keyboard = [
            [
                InlineKeyboardButton(f"{format_time_option(option)[1]} {format_time_option(option)[0]}", callback_data=f"time_spent:{promise_id}:{option:.2f}")
                for option in time_options[i:i + 3]
            ]
            for i in range(0, len(time_options), 3)
        ]
        return InlineKeyboardMarkup(keyboard)

    async def send_nightly_reminders(self, context: CallbackContext) -> None:
        """Send nightly reminders to users about their promises."""
        # Get all user directories
        user_dirs = [d for d in os.listdir(ROOT_DIR) if os.path.isdir(os.path.join(ROOT_DIR, d))]
        
        for user_id in user_dirs:
            # Get user's promises
            promises = self.plan_keeper.get_promises(user_id)
            
            if not promises:
                continue
                
            # Send reminder for each promise
            for promise in promises:
                question = f"How many hours did you spend today on your promise: {promise['text'].replace('_', ' ')}?"
                
                # Calculate suggested hours based on the number of hours promised per week
                hours_per_day = promise['hours_per_week'] / 7
                
                # Create inline keyboard with time options
                reply_markup = self.create_time_options(promise['id'], hours_per_day)
                
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=question,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    # Wait for the user's response before sending the next question
                    await self.wait_for_response(user_id)
                except Exception as e:
                    logger.error(f"Failed to send reminder to user {user_id}: {str(e)}")

    async def wait_for_response(self, user_id: str) -> None:
        """Wait for the user's response before sending the next question."""
        while True:
            # Check if there is a response from the user
            user_responses = self.plan_keeper.get_user_responses(user_id)
            if user_responses:
                break
            await asyncio.sleep(1)

    async def start(self, update: Update, _context: CallbackContext) -> None:
        """Send a message when the command /start is issued."""
        user_id = update.effective_user.id
        created = self.create_user_directory(user_id)
        if created:
            await update.message.reply_text('Hi! Welcome to plan keeper. Your user directory has been created.')
        else:
            await update.message.reply_text('Hi! Welcome back.')

    async def list_promises(self, update: Update, _context: CallbackContext) -> None:
        """Send a message listing all promises for the user."""
        user_id = update.effective_user.id
        promises = self.plan_keeper.get_promises(user_id)
        if not promises:
            await update.message.reply_text("You have no promises.")
        else:
            formatted_promises = "\n".join([f"- {promise['text'].replace('_', ' ')}" for promise in promises])
            await update.message.reply_text(f"Your promises:\n{formatted_promises}")

    async def nightly_reminders(self, update: Update, _context: CallbackContext) -> None:
        """Handle the /nightly command to send nightly reminders."""
        await self.send_nightly_reminders(_context)
        await update.message.reply_text("Nightly reminders sent!")

    async def weekly_report(self, update: Update, _context: CallbackContext) -> None:
        """Handle the /weekly command to send a weekly report."""
        user_id = update.effective_user.id
        report = self.plan_keeper.get_weekly_report(user_id)
        await update.message.reply_text(f"Weekly report:\n{report}")

    async def handle_message(self, update: Update, _context: CallbackContext) -> None:
        try:
            user_message = update.message.text
            user_id = update.effective_user.id

            # Check if user exists, if not, call start
            user_dir = os.path.join(ROOT_DIR, str(user_id))
            if not os.path.exists(user_dir):
                await self.start(update, _context)

            # Get the response from the LLM
            llm_response = self.llm_handler.get_response(user_message, user_id)

            # Check for errors in LLM response
            if "error" in llm_response:
                await update.message.reply_text(
                    llm_response["response_to_user"],
                    parse_mode='Markdown'
                )
                return

            # Process the LLM response
            try:
                func_call_response = self.call_planner_api(user_id, llm_response)
                formatted_response = self._format_response(llm_response, func_call_response)
                await update.message.reply_text(
                    formatted_response,
                    parse_mode='Markdown'
                )
            except ValueError as e:
                await update.message.reply_text(
                    f"⚠️ Invalid input: {str(e)}",
                    parse_mode='Markdown'
                )
                logger.error(f"Validation error for user {user_id}: {str(e)}")
            except Exception as e:
                await update.message.reply_text(
                    "❌ Sorry, I couldn't complete that action. Please try again.",
                    parse_mode='Markdown'
                )
                logger.error(f"Error processing request for user {user_id}: {str(e)}")

        except Exception as e:
            await update.message.reply_text(
                "🔧 Something went wrong. Please try again later.",
                parse_mode='Markdown'
            )
            logger.error(f"Unexpected error handling message from user {user_id}: {str(e)}")

    def _format_response(self, llm_response, func_call_response):
        """Format the response for Telegram."""
        try:
            if isinstance(func_call_response, (list, dict)):
                if isinstance(func_call_response, list):
                    formatted_response = "\n• " + "\n• ".join(str(item) for item in func_call_response)
                else:
                    formatted_response = "\n".join(f"{key}: {value}" for key, value in func_call_response.items())
            else:
                formatted_response = str(func_call_response)

            return (
                f"*LLM Response:*\n`{llm_response}`\n\n"
                f"*Result:*\n{formatted_response}"
            )
        except Exception as e:
            logger.error(f"Error formatting response: {str(e)}")
            return "Error formatting response"

    def call_planner_api(self, user_id, llm_response: str) -> str:
        """
        Process user message by sending it to the LLM and executing the identified action.
        """
        try:
            # Interpret LLM response (you'll need to customize this to match your LLM's output format)
            # Get the function name and arguments from the LLM response
            function_name = llm_response.get("function_call")
            func_args = llm_response.get("function_args", {})

            # Add user_id to function arguments
            func_args["user_id"] = user_id

            # Get the corresponding method from plan_keeper
            if hasattr(self.plan_keeper, function_name):
                method = getattr(self.plan_keeper, function_name)
                # Call the method with unpacked arguments
                return method(**func_args)
            else:
                return f"Function {function_name} not found in PlannerAPI"
        except Exception as e:
            return f"Error executing function: {str(e)}"
        return None

    def create_user_directory(self, user_id: int) -> bool:
        """Create a directory for the user if it doesn't exist and initialize files."""
        user_dir = os.path.join(ROOT_DIR, str(user_id))
        if not os.path.exists(user_dir):
            os.makedirs(user_dir)
            self.initialize_files(user_dir)
            return True
        return False

    def initialize_files(self, user_dir: str) -> None:
        """Initialize the required files in the user's directory."""
        promises_file = os.path.join(user_dir, 'promises.csv')
        actions_file = os.path.join(user_dir, 'actions.csv')
        settings_file = os.path.join(user_dir, 'settings.yaml')

        # Create promises.csv and actions.csv with headers
        for file_path in [promises_file, actions_file]:
            with open(file_path, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(['id', 'content'])  # Example headers, adjust as needed

        # Create settings.yaml with default settings
        default_settings = {'setting1': 'value1', 'setting2': 'value2'}  # Example settings, adjust as needed
        with open(settings_file, 'w') as file:
            yaml.dump(default_settings, file)

    def run(self):
        """Start the bot."""
        self.application.run_polling()


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()
    ROOT_DIR = os.getenv("ROOT_DIR")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    LOG_FILE = os.getenv("LOG_FILE", "bot.log")

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

    logger = logging.getLogger(__name__)

    bot = PlannerAPIBot(BOT_TOKEN)
    bot.run()
