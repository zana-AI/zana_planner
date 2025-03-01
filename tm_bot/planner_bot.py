import os
import csv
import subprocess
from urllib.parse import uses_relative
import asyncio
from datetime import datetime, timedelta
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


class PlannerTelegramBot:
    def __init__(self, token: str):
        request = HTTPXRequest(connect_timeout=10, read_timeout=20)
        self.application = Application.builder().token(token).build()
        self.llm_handler = LLMHandler()  # Instantiate the LLM handler
        self.plan_keeper = PlannerAPI(ROOT_DIR)  # Instantiate the PlannerAPI class

        # Register handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("promises", self.list_promises))  # list_promises command handler
        self.application.add_handler(CommandHandler("nightly", self.nightly_reminders))  # nightly command handler
        self.application.add_handler(CommandHandler("weekly", self.weekly_report))  # weekly command handler
        self.application.add_handler(CommandHandler("zana", self.plan_by_zana))  # zana command handler
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

    def beautify_time(self, time: float) -> str:
        """Convert a float time value in hours to a human-readable string."""
        hours = int(time)
        minutes = int((time - hours) * 60)
        if hours == 0 and minutes == 0:
            return "0 min"
        elif hours == 0:
            return f"{minutes} min"
        else:  # show something like "3:45" for 3 hours and 45 minutes
            return f"{hours}:{minutes:02d} hrs"

    def round_time(self, time: float) -> float:
        """Round a time value to the nearest 15 minutes."""
        hours = int(time)
        minutes = int((time - hours) * 60)
        if hours <= 0 and minutes <= 0:
            return 0
        elif hours == 0:
            return round(minutes / 5) * 5 / 60
        else:
            return hours + round(minutes / 5) * 5 / 60

    # Example helper function to create the inline keyboard
    def create_time_options(self, promise_id: str, hpd_base: float, latest_record: float) -> InlineKeyboardMarkup:
        """
        Create an inline keyboard with two rows:
          - Row 1: Three buttons showing:
              [0 hrs] [<sensible default> hrs] [<latest record> hrs]
          - Row 2: Two adjustment buttons for the third option:
              [-5 min] and [+10 min]
        hpd_base is a default sensible value (for example, hours per day based on the weekly promise)
        latest_record is the most recent logged time.
        """
        # First row buttons
        button_zero = InlineKeyboardButton("0 hrs", callback_data=f"time_spent:{promise_id}:0.00")
        button_latest = InlineKeyboardButton(self.beautify_time(latest_record),
                                             callback_data=f"time_spent:{promise_id}:{latest_record:.5f}")
        hpd_base_rounded = self.round_time(hpd_base)
        button_default = InlineKeyboardButton(self.beautify_time(hpd_base_rounded),
                                              callback_data=f"time_spent:{promise_id}:{hpd_base_rounded:.5f}")
        row1 = [button_zero, button_latest, button_default]

        # Second row: adjustment buttons for the third option (latest_record)
        adjust_minus = InlineKeyboardButton("-5 min",
                                            callback_data=f"update_time_spent:{promise_id}:{-5/60:.5f}")
        adjust_plus = InlineKeyboardButton("+10 min",
                                           callback_data=f"update_time_spent:{promise_id}:{10/60:.5f}")
        row2 = [adjust_minus, adjust_plus]

        return InlineKeyboardMarkup([row1, row2])

    # Revised callback handler for time selection
    async def handle_time_selection(self, update: Update, context: CallbackContext) -> None:
        """
        Handle the callback when a user selects or adjusts the time spent.

        Callback data format:
          - For registering an action: "time_spent:<promise_id>:<value>"
          - For adjusting the third option: "update_time_spent:<promise_id>:<new_value>"
        """
        query = update.callback_query
        await query.answer()

        # Parse the callback data
        data_parts = query.data.split(":")
        if len(data_parts) != 3:
            return  # Invalid callback data format

        action_type, promise_id, value_str = data_parts
        try:
            value = float(value_str)  # the time spent value
        except ValueError:
            return  # Could not parse a number

        # If the callback is for updating (adjusting) the third button's value:
        if action_type == "update_time_spent":
            # Retrieve the current keyboard from the message
            keyboard = query.message.reply_markup.inline_keyboard
            # convert tuple to list
            keyboard = [list(row) for row in keyboard]
            # Assume the first row holds the time selection buttons;
            # we want to update the third button (index 2) in that row.
            if len(keyboard) > 0 and len(keyboard[0]) >= 3:
                try:
                    ref_value = float(keyboard[0][2].callback_data.split(":")[2])  # Extract the current value from the button text
                    new_value = self.round_time(ref_value + value)  # Adjust the value
                    new_button = InlineKeyboardButton(
                        text=self.beautify_time(new_value),
                        callback_data=f"time_spent:{promise_id}:{new_value:.5f}"
                    )
                    keyboard[0][2] = new_button
                    # Optionally, you might also update the adjustment buttons in row 2
                    # to reflect the new value if desired.
                    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
                except Exception as e:
                    logger.error(f"Error updating message: {str(e)}")
            return  # Do not register the action yet.

        # Else, if the callback is from the first row (confirming the time selection)
        elif action_type == "time_spent":
            # When a valid time option is selected (greater than 0), register the action.
            if value > 0:
                # Register the action (e.g., using your PlannerAPI's add_action method)
                self.plan_keeper.add_action(
                    user_id=query.from_user.id,
                    promise_id=promise_id,
                    time_spent=value
                )
                await query.edit_message_text(
                    text=f"Spent {self.beautify_time(value)} on #{promise_id}.",
                    parse_mode='Markdown'
                )
            else:
                # If 0 is selected, consider it a cancellation and delete the message.
                await query.delete_message()

    async def send_nightly_reminders(self, context: CallbackContext, user_id=None) -> None:
        """
        Send nightly reminders to users about their promises.
        If user_id is provided, only that user is targeted; otherwise, all user directories under ROOT_DIR are processed.
        """
        # Determine which user directories to use.
        if user_id is not None:
            user_dirs = [str(user_id)]
        else:
            user_dirs = [d for d in os.listdir(ROOT_DIR) if os.path.isdir(os.path.join(ROOT_DIR, d))]
        
        for user_id in user_dirs:
            # Get all promises for the current user.
            promises = self.plan_keeper.get_promises(user_id)
            if not promises:
                continue

            # Send reminder for each promise
            for promise in promises:
                promise_id = promise['id']
                # Skip non-recurring promises that have already reached full weekly progress.
                promise_progress = self.plan_keeper.get_promise_weekly_progress(user_id, promise_id)
                if not promise.get('recurring', False) and promise_progress >= 1:
                    continue

                # Get the latest action for the promise.
                last_action = self.plan_keeper.get_last_action_on_promise(user_id, promise_id)
                if last_action:
                    # last_action is a UserAction instance.
                    last_time_spent = float(last_action.time_spent)
                    try:
                        last_date = datetime.strptime(last_action.action_date, '%Y-%m-%d')
                    except Exception:
                        last_date = datetime.now()
                    days_passed = (datetime.now() - last_date).days
                else:
                    last_time_spent = 0
                    days_passed = -1

                # Prepare the reminder question.
                question = (
                    f"How much time did you spend today on: "
                    f"*{promise['text'].replace('_', ' ')}*?"
                )

                # Calculate a sensible default value (hpd_base):
                # If there is a last action, use its value; otherwise, use hours_per_week divided by 7.
                if last_time_spent > 0:
                    hpd_base = last_time_spent
                else:
                    hpd_base = promise['hours_per_week'] / 7

                # For non-recurring promises, you might want to scale the suggested time differently.
                if not promise.get('recurring', False):
                    default_time = 0.5 * 7 * hpd_base  # For example, half a week's worth.
                    latest_time = 1 * 7 * hpd_base  # One week's worth.
                else:
                    default_time = hpd_base
                    latest_time = last_time_spent if last_time_spent > 0 else hpd_base

                # Build the inline keyboard.
                # This helper function creates:
                #   - First row: [0 hrs] [default_time hrs] [latest_time hrs]
                #   - Second row: adjustment buttons for the third option (-5 min, +10 min)
                reply_markup = self.create_time_options(promise_id, default_time, latest_time)

                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=question,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Failed to send reminder to user {user_id}: {str(e)}")

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
            await update.message.reply_text("You have no promises. You want to add one? For example, you could promise to "
                                            "'deep work 6 hours a day, 5 days a week', "
                                            "'spend 2 hours a week on playing guitar.'")
        else:
            formatted_promises = ""
            # Sort promises by promise_id
            sorted_promises = sorted(promises, key=lambda p: p['id'])
            for index, promise in enumerate(sorted_promises):
                # Numerize and format promises
                promised_hours = promise['hours_per_week']
                promise_progress = self.plan_keeper.get_promise_weekly_progress(user_id, promise['id'])
                recurring = promise['recurring']
                # if not recurring:
                formatted_promises += f"* {promise['id']}: {promise['text'].replace('_', ' ')}\n"
                # formatted_promises += f"  - Progress: {promise_progress * 100:.1f}% ({promise_progress * promised_hours:.1f}/{promised_hours} hours)\n"

            # formatted_promises = "\n".join([f"* #{promise['id']}: {promise['text'].replace('_', ' ')}" for index, promise in enumerate(sorted_promises)])
            await update.message.reply_text(f"Your promises:\n{formatted_promises}")

    async def nightly_reminders(self, update: Update, _context: CallbackContext) -> None:
        """Handle the /nightly command to send nightly reminders."""
        uses_id = update.effective_user.id
        await self.send_nightly_reminders(_context, user_id=uses_id)
        await update.message.reply_text("Nightly reminders sent!")

    async def weekly_report(self, update: Update, _context: CallbackContext) -> None:
        """Handle the /weekly command to send a weekly report with a refresh button."""
        user_id = update.effective_user.id
        report_ref_time = datetime.now()
        report = self.plan_keeper.get_weekly_report(user_id, reference_time=report_ref_time)

        # Compute week boundaries based on report_ref_time.
        monday = report_ref_time - timedelta(days=report_ref_time.weekday())
        week_start = monday.replace(hour=3, minute=0, second=0, microsecond=0)
        if report_ref_time < week_start:
            week_start = week_start - timedelta(days=7)
        # For the header, we use the reference time as the end of the range.
        week_end = report_ref_time
        date_range_str = f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b')}"

        # Create a refresh button whose callback data includes the user_id and report_ref_time (as epoch).
        refresh_callback_data = f"refresh_weekly:{user_id}:{int(report_ref_time.timestamp())}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Refresh", callback_data=refresh_callback_data)]])

        await update.message.reply_text(
            f"Weekly: {date_range_str}\n\n{report}",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    
    async def refresh_weekly_report(self, update: Update, context: CallbackContext) -> None:
        """Handle refresh callback to update the weekly report using the original reference time."""
        query = update.callback_query
        await query.answer()

        # Callback data format: "refresh_weekly:<user_id>:<ref_timestamp>"
        parts = query.data.split(":")
        if len(parts) != 3:
            return

        user_id = parts[1]
        ref_timestamp = int(parts[2])
        report_ref_time = datetime.fromtimestamp(ref_timestamp)

        report = self.plan_keeper.get_weekly_report(user_id, reference_time=report_ref_time)

        # Recompute the date range.
        monday = report_ref_time - timedelta(days=report_ref_time.weekday())
        week_start = monday.replace(hour=3, minute=0, second=0, microsecond=0)
        if report_ref_time < week_start:
            week_start = week_start - timedelta(days=7)
        week_end = report_ref_time
        date_range_str = f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b')}"

        # Preserve the same refresh callback data.
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Refresh", callback_data=query.data)]])
        await query.edit_message_text(
            f"Weekly: {date_range_str}\n\n{report}",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    async def plan_by_zana(self, update: Update, _context: CallbackContext) -> None:
        user_id = update.effective_user.id
        recommended_actions = self.llm_handler.get_response_custom("What should I do today?"
                                                            "Recommend actions for me based on the promises, and the weekly report."
                                                            "I expect the output to be a list of actions like:"
                                                            "1. [5h] Deep work on promise #P31"
                                                            "2. [0.5h] Exercise for 30 minutes this evening #P62",
                                                            user_id)
        formatted_actions = "".join([f"* {action}" for action in recommended_actions])
        await update.message.reply_text(f"Recommended actions for today:\n{formatted_actions}", parse_mode='Markdown')

    async def handle_message(self, update: Update, _context: CallbackContext) -> None:
        try:
            user_message = update.message.text
            user_id = update.effective_user.id

            # Check if user exists, if not, call start
            user_dir = os.path.join(ROOT_DIR, str(user_id))
            if not os.path.exists(user_dir):
                await self.start(update, _context)

            llm_response = self.llm_handler.get_response_api(user_message, user_id)

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
                formatted_response = self._format_response(llm_response['response_to_user'], func_call_response)
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
                    f"❌ Sorry, I couldn't complete that action. Please try again. Error: {str(e)}",
                    parse_mode='Markdown'
                )
                logger.error(f"Error processing request for user {user_id}: {str(e)}")

        except Exception as e:
            await update.message.reply_text(
                f"🔧 Something went wrong. Please try again later. Error: {str(e)}",
                parse_mode='Markdown'
            )
            logger.error(f"Unexpected error handling message from user {user_id}: {str(e)}")

    def _format_response(self, llm_response, func_call_response):
        """Format the response for Telegram."""
        try:
            if isinstance(func_call_response, list):
                formatted_response = "\n• " + "\n• ".join(str(item) for item in func_call_response)
            elif isinstance(func_call_response, dict):
                formatted_response = "\n".join(f"{key}: {value}" for key, value in func_call_response.items())
            else:
                formatted_response = str(func_call_response)

            full_response = f"*Zana:*\n`{llm_response}`\n\n"
            if formatted_response:
                full_response += f"*Log:*\n{formatted_response}"
            return full_response
        except Exception as e:
            logger.error(f"Error formatting response: {str(e)}")
            return "Error formatting response"

    def call_planner_api(self, user_id, llm_response: dict) -> str:
        """
        Process user message by sending it to the LLM and executing the identified action.
        """
        try:
            # Interpret LLM response (you'll need to customize this to match your LLM's output format)
            # Get the function name and arguments from the LLM response
            function_name = llm_response.get("function_call", None)
            if function_name is None:
                return ""

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

    logger = logging.getLogger(__name__)

    bot = PlannerTelegramBot(BOT_TOKEN)
    bot.run()
