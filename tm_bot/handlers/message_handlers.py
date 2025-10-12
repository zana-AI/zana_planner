"""
Message handlers for the Telegram bot.
Handles all command and text message processing.
"""

import os
import logging
from datetime import datetime
from typing import Optional

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import CallbackContext

from handlers.messages_store import get_message, get_user_language
from services.planner_api_adapter import PlannerAPIAdapter
from llms.llm_handler import LLMHandler
from utils.time_utils import get_week_range
from ui.messages import weekly_report_text
from ui.keyboards import weekly_report_kb, pomodoro_kb, preping_kb
from cbdata import encode_cb
from infra.scheduler import schedule_user_daily
from utils_storage import create_user_directory
from handlers.callback_handlers import CallbackHandlers

logger = logging.getLogger(__name__)


class MessageHandlers:
    """Handles all message and command processing."""
    
    def __init__(self, plan_keeper: PlannerAPIAdapter, llm_handler: LLMHandler, root_dir: str, application):
        self.plan_keeper = plan_keeper
        self.llm_handler = llm_handler
        self.root_dir = root_dir
        self.application = application
    
    def get_user_timezone(self, user_id: int) -> str:
        """Get user timezone using the settings repository."""
        settings = self.plan_keeper.settings_repo.get_settings(user_id)
        return settings.timezone
    
    def set_user_timezone(self, user_id: int, tzname: str) -> None:
        """Set user timezone using the settings repository."""
        settings = self.plan_keeper.settings_repo.get_settings(user_id)
        settings.timezone = tzname
        self.plan_keeper.settings_repo.save_settings(settings)
    
    async def start(self, update: Update, context: CallbackContext) -> None:
        """Send a message when the command /start is issued."""
        user_id = update.effective_user.id
        user_lang = get_user_language(user_id)
        
        create_user_directory(self.root_dir, user_id)
        existing_promises = self.plan_keeper.get_promises(user_id)
        if len(existing_promises) == 0:
            message = get_message("welcome_new", user_lang)
        else:
            message = get_message("welcome_return", user_lang)
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
        tzname = self.get_user_timezone(user_id)
        schedule_user_daily(
            self.application.job_queue,
            user_id=user_id,
            tz=tzname,
            callback=self.scheduled_morning_reminders_for_one,
            hh=8, mm=30,
            name_prefix="morning",
        )
        
        # (Re)Schedule this user's nightly job at 22:59 in their timezone
        schedule_user_daily(
            self.application.job_queue,
            user_id,
            tzname,
            self.scheduled_nightly_reminders_for_one,
            hh=22,
            mm=59,
            name_prefix="nightly"
        )
        logger.info(f"Scheduled nightly reminders at 22:59 {tzname} for user {user_id}")
    
    async def list_promises(self, update: Update, context: CallbackContext) -> None:
        """Send a message listing all promises for the user."""
        user_id = update.effective_user.id
        user_lang = get_user_language(user_id)
        
        promises = self.plan_keeper.get_promises(user_id)
        if not promises:
            message = get_message("no_promises", user_lang)
        else:
            formatted_promises = ""
            # Sort promises by promise_id
            sorted_promises = sorted(promises, key=lambda p: p['id'])
            for promise in sorted_promises:
                formatted_promises += get_message("promise_item", user_lang, 
                                                id=promise['id'], 
                                                text=promise['text'].replace('_', ' ')) + "\n"
            
            header = get_message("promises_list_header", user_lang)
            message = f"{header}\n{formatted_promises}"
        
        await update.message.reply_text(message)
    
    async def nightly_reminders(self, update: Update, context: CallbackContext) -> None:
        """Handle the /nightly command to send nightly reminders."""
        user_id = update.effective_user.id
        await self.send_nightly_reminders(context, user_id=user_id)
    
    async def morning_reminders(self, update: Update, context: CallbackContext) -> None:
        """Handle the /morning command to send morning reminders."""
        user_id = update.effective_user.id
        await self.send_morning_reminders(context, user_id=user_id)
    
    async def weekly_report(self, update: Update, context: CallbackContext) -> None:
        """Handle the /weekly command to send a weekly report with a refresh button."""
        user_id = update.effective_user.id
        user_lang = get_user_language(user_id)
        report_ref_time = datetime.now()
        
        # Get weekly summary using the new service
        summary = self.plan_keeper.reports_service.get_weekly_summary(user_id, report_ref_time)
        report = weekly_report_text(summary)
        
        # Compute week boundaries based on report_ref_time.
        week_start, week_end = get_week_range(report_ref_time)
        date_range_str = f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b')}"
        
        # Create refresh keyboard
        keyboard = weekly_report_kb(report_ref_time)
        
        header = get_message("weekly_header", user_lang, date_range=date_range_str)
        await update.message.reply_text(
            f"{header}\n\n{report}",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    
    async def plan_by_zana(self, update: Update, context: CallbackContext) -> None:
        """Handle the /zana command to get AI insights."""
        user_id = update.effective_user.id
        user_lang = get_user_language(user_id)
        
        promises = self.plan_keeper.get_promises(user_id)
        
        if not promises:
            message = get_message("zana_no_promises", user_lang)
            await update.message.reply_text(message)
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
            "### Today's Focus Summary\n"
            "Summarize key focus areas and recommended time allocations.\n"
            "--------------------------------------------------\n\n"
            "Keep the tone creative, motivational, and succinct!"
        )
        
        # Get insights from the LLM handler
        insights = self.llm_handler.get_response_custom(prompt, user_id)
        
        # Send the insights to the user
        message = get_message("zana_insights", user_lang, insights=insights)
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def pomodoro(self, update: Update, context: CallbackContext) -> None:
        """Handle the /pomodoro command to start a Pomodoro timer."""
        user_id = update.effective_user.id
        user_lang = get_user_language(user_id)
        
        keyboard = pomodoro_kb()
        message = get_message("pomodoro_start", user_lang)
        await update.message.reply_text(
            message,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    
    async def cmd_settimezone(self, update: Update, context: CallbackContext) -> None:
        """Handle the /settimezone command."""
        user_id = update.effective_user.id
        user_lang = get_user_language(user_id)
        
        if context.args:
            tzname = context.args[0]
            # validate
            try:
                from zoneinfo import ZoneInfo
                ZoneInfo(tzname)
            except Exception:
                message = get_message("timezone_invalid", user_lang)
                await update.message.reply_text(message)
                return
            
            # save
            self.set_user_timezone(user_id, tzname)
            # reschedule nightly/morning jobs if you have them
            await self._reschedule_user_jobs(user_id, tzname)
            message = get_message("timezone_set", user_lang, timezone=tzname)
            await update.message.reply_text(message)
            return
        
        # Ask for location
        kb = ReplyKeyboardMarkup(
            [[KeyboardButton(get_message("btn_share_location", user_lang), request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
            input_field_placeholder="Tap to share your location…",
        )
        message = get_message("timezone_location_request", user_lang)
        await update.message.reply_text(message, reply_markup=kb)
    
    async def on_location_shared(self, update: Update, context: CallbackContext) -> None:
        """Handle location sharing for timezone detection."""
        user_id = update.effective_user.id
        user_lang = get_user_language(user_id)
        
        loc = update.effective_message.location
        if not loc:
            return
        
        try:
            from timezonefinder import TimezoneFinder
            tf = TimezoneFinder()
            tzname = tf.timezone_at(lat=loc.latitude, lng=loc.longitude)
            
            if not tzname:
                message = get_message("timezone_location_failed", user_lang)
                await update.message.reply_text(
                    message,
                    reply_markup=ReplyKeyboardRemove(),
                )
                return
            
            self.set_user_timezone(user_id, tzname)
            message = get_message("timezone_location_success", user_lang, timezone=tzname)
            await update.message.reply_text(
                message,
                reply_markup=ReplyKeyboardRemove(),
            )
        except ImportError:
            logger.error("timezonefinder not available")
            message = get_message("timezone_location_failed", user_lang)
            await update.message.reply_text(
                message,
                reply_markup=ReplyKeyboardRemove(),
            )
    
    async def handle_message(self, update: Update, context: CallbackContext) -> None:
        """Handle general text messages."""
        try:
            user_message = update.message.text
            user_id = update.effective_user.id
            user_lang = get_user_language(user_id)
            
            # Check if user exists, if not, call start
            user_dir = os.path.join(self.root_dir, str(user_id))
            if not os.path.exists(user_dir):
                await self.start(update, context)
                return
            
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
                message = get_message("error_invalid_input", user_lang, error=str(e))
                await update.message.reply_text(message, parse_mode='Markdown')
                logger.error(f"Validation error for user {user_id}: {str(e)}")
            except Exception as e:
                message = get_message("error_general", user_lang, error=str(e))
                await update.message.reply_text(message, parse_mode='Markdown')
                logger.error(f"Error processing request for user {user_id}: {str(e)}")
        
        except Exception as e:
            user_lang = get_user_language(update.effective_user.id)
            message = get_message("error_unexpected", user_lang, error=str(e))
            await update.message.reply_text(message, parse_mode='Markdown')
            logger.error(f"Unexpected error handling message from user {update.effective_user.id}: {str(e)}")
    
    def _format_response(self, llm_response: str, func_call_response) -> str:
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
    
    def call_planner_api(self, user_id: int, llm_response: dict) -> str:
        """Process user message by sending it to the LLM and executing the identified action."""
        try:
            # Interpret LLM response
            function_name = llm_response.get("function_call", None)
            if function_name is None:
                return ""
            
            func_args = llm_response.get("function_args", {})
            func_args["user_id"] = user_id
            
            # Get the corresponding method from plan_keeper
            if hasattr(self.plan_keeper, function_name):
                method = getattr(self.plan_keeper, function_name)
                return method(**func_args)
            else:
                return f"Function {function_name} not found in PlannerAPI"
        except Exception as e:
            return f"Error executing function: {str(e)}"
    
    async def _reschedule_user_jobs(self, user_id: int, tzname: str) -> None:
        """Reschedule user jobs with new timezone."""
        # TODO: Implementation for rescheduling jobs
        pass

    async def send_nightly_reminders(self, context: CallbackContext, user_id: int = None) -> None:
        """Send nightly reminders to users about their promises."""
        # Delegate to callback handlers which has the implementation
        callback_handlers = CallbackHandlers(self.plan_keeper, self.application)
        await callback_handlers.send_nightly_reminders(context, user_id)

    async def send_morning_reminders(self, context: CallbackContext, user_id: int) -> None:
        """Send morning reminders to users."""
        # Delegate to callback handlers which has the implementation
        callback_handlers = CallbackHandlers(self.plan_keeper, self.application)
        await callback_handlers.send_morning_reminders(context, user_id)
    
    async def scheduled_noon_cleanup_for_one(self, context: CallbackContext) -> None:
        """Scheduled callback for noon cleanup of unread morning messages."""
        user_id = context.job.data["user_id"]
        logger.info(f"Running scheduled noon cleanup for user {user_id}")
        
        # Delegate to callback handlers which has the implementation
        callback_handlers = CallbackHandlers(self.plan_keeper, self.application)
        await callback_handlers.cleanup_unread_morning_messages(context, user_id)
    
    async def scheduled_nightly_reminders_for_one(self, context: CallbackContext) -> None:
        """Scheduled callback for nightly reminders."""
        user_id = context.job.data["user_id"]
        logger.info(f"Running scheduled nightly reminder for user {user_id}")
        await self.send_nightly_reminders(context, user_id=user_id)
    
    async def scheduled_morning_reminders_for_one(self, context: CallbackContext) -> None:
        """Scheduled callback for morning reminders."""
        user_id = context.job.data["user_id"]
        await self.send_morning_reminders(context, user_id=user_id)
