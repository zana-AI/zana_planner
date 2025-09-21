import os
import subprocess
from urllib.parse import uses_relative
import asyncio
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, time
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
from utils_time import beautify_time, round_time, get_week_range
from zana_planner.tm_bot.utils_storage import create_user_directory


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
        self.application.add_handler(CommandHandler("pomodoro", self.pomodoro))  # pomodoro command handler
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_handler(CallbackQueryHandler(self.handle_promise_callback))

    def get_user_timezone(self, user_id: int) -> str:
        settings_path = os.path.join(ROOT_DIR, str(user_id), 'settings.yaml')
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                data = yaml.safe_load(f) or {}
            return data.get('timezone', 'Europe/Paris')
        return 'Europe/Paris'

    def set_user_timezone(self, user_id: int, tzname: str) -> None:
        settings_path = os.path.join(ROOT_DIR, str(user_id), 'settings.yaml')
        data = {}
        if os.path.exists(settings_path):
            with open(settings_path, 'r') as f:
                data = yaml.safe_load(f) or {}
        data['timezone'] = tzname
        with open(settings_path, 'w') as f:
            yaml.safe_dump(data, f)

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
        button_latest = InlineKeyboardButton(beautify_time(latest_record),
                                             callback_data=f"time_spent:{promise_id}:{latest_record:.5f}")
        hpd_base_rounded = round_time(hpd_base)
        button_default = InlineKeyboardButton(beautify_time(hpd_base_rounded),
                                              callback_data=f"time_spent:{promise_id}:{hpd_base_rounded:.5f}")

        # Second row: adjustment buttons for the third option (latest_record)
        adjust_minus = InlineKeyboardButton("-5 min",
                                            callback_data=f"update_time_spent:{promise_id}:{-5/60:.5f}")
        adjust_plus = InlineKeyboardButton("+10 min",
                                           callback_data=f"update_time_spent:{promise_id}:{10/60:.5f}")
        remind_next_week = InlineKeyboardButton("Remind next week",
                                                callback_data=f"remind_next_week:{promise_id}")
        delete_promise = InlineKeyboardButton("Delete",
                                              callback_data=f"delete_promise:{promise_id}")
        report_button = InlineKeyboardButton("Report",
                                             callback_data=f"report_promise:{promise_id}")

        row1 = [button_zero, button_default, adjust_minus, adjust_plus]
        row2 = [remind_next_week, delete_promise, report_button]

        return InlineKeyboardMarkup([row1, row2])

    # Revised callback handler for promise-related actions
    async def handle_promise_callback(self, update: Update, context: CallbackContext) -> None:
        """
        Handle the callback when a user selects or adjusts the time spent, or performs other actions on promises.

        Callback data format:
          - For registering an action: "time_spent:<promise_id>:<value>"
          - For adjusting the third option: "update_time_spent:<promise_id>:<new_value>"
          - For deleting a promise: "delete_promise:<promise_id>"
          - For confirming deletion: "confirm_delete:<promise_id>"
          - For canceling deletion: "cancel_delete:<promise_id>"
          - For reminding next week: "remind_next_week:<promise_id>"
        """
        query = update.callback_query
        await query.answer()

        # Parse the callback data
        data_parts = query.data.split(":")
        action_type = data_parts[0]

        if action_type == "pomodoro_start":
            await self.start_pomodoro_timer(query, context)
        elif action_type == "pomodoro_pause":
            await query.edit_message_text(
                text="Pomodoro Timer Paused.",
                parse_mode='Markdown'
            )
        elif action_type == "pomodoro_stop":
            await query.edit_message_text(
                text="Pomodoro Timer Stopped.",
                parse_mode='Markdown'
            )

        if len(data_parts) < 2:
            return  # Invalid callback data format
        
        promise_id = data_parts[1]

        if action_type == "remind_next_week":
            # Update the promise's start date to the beginning of next week
            next_monday = (datetime.now() + timedelta(days=(7 - datetime.now().weekday()))).date()
            self.plan_keeper.update_promise_start_date(query.from_user.id, promise_id, next_monday)
            await query.edit_message_text(
                text=f"#{promise_id} will be silent until monday.",
                parse_mode='Markdown'
            )
            return

        elif action_type == "delete_promise":
            # Retrieve the current keyboard from the message
            keyboard = list(query.message.reply_markup.inline_keyboard)  # Convert tuple to list
            # Add confirmation buttons to the second row
            confirm_buttons = [
                InlineKeyboardButton("Yes (delete)", callback_data=f"confirm_delete:{promise_id}"),
                InlineKeyboardButton("No (cancel)", callback_data=f"cancel_delete:{promise_id}")
            ]
            # Keep the first row and add the confirmation buttons as a new row
            keyboard.append(confirm_buttons)
            await query.edit_message_text(
                text=query.message.text_markdown,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return

        elif action_type == "confirm_delete":
            # Delete the promise after confirmation
            result = self.plan_keeper.delete_promise(query.from_user.id, promise_id)
            await query.edit_message_text(
                text=result,
                parse_mode='Markdown'
            )
            return

        elif action_type == "cancel_delete":
            # Cancel the delete action
            await query.edit_message_text(
                text=query.message.text_markdown,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(query.message.reply_markup.inline_keyboard[:-1])

            )
            return
        
        elif action_type == "report_promise":
            # Generate a report for the promise
            report = self.plan_keeper.get_promise_report(query.from_user.id, promise_id)
            await query.edit_message_text(
                text=report,
                parse_mode='Markdown'
            )
            return

        try:
            value_str = data_parts[2]
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
                    ref_value = float(keyboard[0][1].callback_data.split(":")[2])  # Extract the current value from the button text
                    new_value = round_time(ref_value + value)  # Adjust the value
                    new_button = InlineKeyboardButton(
                        text=beautify_time(new_value),
                        callback_data=f"time_spent:{promise_id}:{new_value:.5f}"
                    )
                    keyboard[0][1] = new_button
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
                    time_spent=value,
                    action_datetime=query.message.date
                )
                await query.edit_message_text(
                    text=f"Spent {beautify_time(value)} on #{promise_id}.",
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
                
                # Check if the promise's start date is in the future
                start_date = datetime.strptime(promise['start_date'], '%Y-%m-%d').date()
                if start_date > datetime.now().date():
                    continue

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
        created = create_user_directory(ROOT_DIR,  user_id)
        if created:
            await update.message.reply_text('Hi! Welcome to plan keeper. Your user directory has been created.')
        else:
            await update.message.reply_text('Hi! Welcome back.')

        # (Re)Schedule this user’s nightly job at 22:59 in their timezone
        tzname = self.get_user_timezone(user_id)
        job_name = f"nightly-{user_id}"
        # clear any previous job with same name
        for j in self.application.job_queue.get_jobs_by_name(job_name):
            j.schedule_removal()

        self.application.job_queue.run_daily(
            self.scheduled_nightly_reminders_for_one,
            time=time(22, 59, tzinfo=ZoneInfo(tzname)),
            days=(0, 1, 2, 3, 4, 5, 6),
            name=job_name,
            data={"user_id": user_id}
        )
        logger.info(f"Scheduled nightly reminders at 22:59 {tzname} for user {user_id}")

        # self.application.job_queue.run_daily(
        #     self.test_nightly_message,
        #     time=time(11, 45, tzinfo=ZoneInfo(tzname)),
        #     days=(0, 1, 2, 3, 4, 5, 6),
        #     name=job_name,
        #     data={"user_id": user_id},
        # )
        # await update.message.reply_text(f"✅ Scheduled a test auto message")

    # async def test_nightly_message(self, context: CallbackContext) -> None:
    #     user_id = context.job.data["user_id"]
    #     await context.bot.send_message(chat_id=user_id, text="🌙 Hello from nightly job!")

    async def scheduled_nightly_reminders_for_one(self, context: CallbackContext) -> None:
        user_id = context.job.data["user_id"]
        logger.info(f"Running scheduled nightly reminder for user {user_id}")
        await self.send_nightly_reminders(context, user_id=user_id)

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
        week_start, week_end = get_week_range(report_ref_time)
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
        week_start, week_end = get_week_range(report_ref_time)
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
        promises = self.plan_keeper.get_promises(user_id)
        
        if not promises:
            await update.message.reply_text("You have no promises to report on.")
            return

        # Generate reports for all promises
        reports = []
        for promise in promises:
            report = self.plan_keeper.get_promise_report(user_id, promise['id'])
            reports.append(report)

        # Concatenate all reports
        full_report = "\n\n".join(reports)

        # Create a creative prompt for the LLM
        prompt = (
            "Here is a detailed report of my current promises and progress:\n\n"
            f"'''{full_report}\n\n'''"
            f"And today is {datetime.now().strftime('%A %d-%B-%Y %H:%M')}. "
            "Based on this report, please provide insights on what the user should focus on today. "
            "Your response should follow a format similar to this example:\n\n"
            "--------------------------------------------------\n"
            "**Focus Areas + Actionable Steps for Today: [Date]**\n\n"
            "#### 1. [Promise Title]\n"
            "- Current Status: [current progress] (e.g., 10.0/30.0 hours this week, 33%).\n"
            "- Actionable Step: [Suggest a concrete step].\n\n"
            "#### 2. [Another Promise Title]\n"
            "- Current Status: [progress details].\n"
            "- Actionable Step: [Action recommendation].\n\n"
            "### Motivational Reminder\n"
            "Include a brief, uplifting message to encourage progress.\n\n"
            "### Today’s Focus Summary\n"
            "Summarize key focus areas and recommended time allocations.\n"
            "--------------------------------------------------\n\n"
            "Keep the tone creative, motivational, and succinct!"
        )

        # Get insights from the LLM handler
        insights = self.llm_handler.get_response_custom(prompt, user_id)

        # Send the insights to the user
        await update.message.reply_text(
            f"Insights from Zana:\n{insights}",
            parse_mode='Markdown'
        )

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



    def run(self):
        """Start the bot."""
        self.application.run_polling()

    async def pomodoro(self, update: Update, context: CallbackContext) -> None:
        """Handle the /pomodoro command to start a Pomodoro timer."""
        keyboard = [
            [
                InlineKeyboardButton("Start", callback_data="pomodoro_start"),
                InlineKeyboardButton("Pause", callback_data="pomodoro_pause"),
                InlineKeyboardButton("Stop", callback_data="pomodoro_stop"),
            ]
        ]
        await update.message.reply_text(
            "Pomodoro Timer: 25:00",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def start_pomodoro_timer(self, query, context):
        """Start the Pomodoro timer."""
        total_time = 25 # minutes
        interval = 5  # seconds
        for remaining in range(total_time * 60, 0, -interval):
            minutes, seconds = divmod(remaining, 60)
            timer_text = f"Pomodoro Timer: **{minutes:02}:{seconds:02}**"
            try:
                await query.edit_message_text(
                    text=timer_text,
                    parse_mode='Markdown'
                )
                await asyncio.sleep(interval)
            except Exception as e:
                break  # Exit the loop if the message is deleted or another error occurs

        await query.edit_message_text(
            text="Pomodoro Timer (25min) Finished! 🎉",
            parse_mode='Markdown'
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Time's up! Take a break or start another session.",
            parse_mode='Markdown'
        )


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
