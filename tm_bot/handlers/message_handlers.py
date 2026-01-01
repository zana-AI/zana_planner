"""
Message handlers for the Telegram bot.
Handles all command and text message processing.
"""

import asyncio
import os
import html
import json
import re
from datetime import datetime
from typing import Optional

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import CallbackContext

from handlers.messages_store import get_message, get_user_language, Language
from handlers.translator import translate_text
from services.planner_api_adapter import PlannerAPIAdapter
from services.voice_service import VoiceService
from services.content_service import ContentService
from services.response_service import ResponseService
from platforms.interfaces import IResponseService
from llms.llm_handler import LLMHandler
from utils.time_utils import get_week_range
from utils.calendar_utils import generate_google_calendar_link, suggest_time_slot
from utils.formatting import format_response_html
from ui.messages import weekly_report_text
from ui.keyboards import weekly_report_kb, pomodoro_kb, preping_kb, language_selection_kb, voice_mode_selection_kb, content_actions_kb, mini_app_kb
from cbdata import encode_cb
from infra.scheduler import schedule_user_daily, schedule_once
from handlers.callback_handlers import CallbackHandlers
from utils.logger import get_logger
from utils.version import get_version_info
from utils.admin_utils import is_admin
from services.broadcast_service import get_all_users, send_broadcast, parse_broadcast_time
from services.stats_service import get_aggregate_stats
from services.avatar_service import AvatarService
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = get_logger(__name__)


class MessageHandlers:
    """Handles all message and command processing."""
    
    def __init__(self, plan_keeper: PlannerAPIAdapter, llm_handler: LLMHandler, root_dir: str, application, response_service: IResponseService, miniapp_url: str = "https://zana-ai.com"):
        self.plan_keeper = plan_keeper
        self.llm_handler = llm_handler
        self.avatar_service = AvatarService(root_dir)
        self.root_dir = root_dir
        self.application = application
        self.response_service = response_service
        self.miniapp_url = miniapp_url
        self.voice_service = VoiceService()
        self.content_service = ContentService()
        try:
            # ImageService has heavier/optional deps; import lazily to avoid import-time failures.
            from services.image_service import ImageService  # noqa: WPS433
            self.image_service = ImageService()
        except Exception as e:
            logger.error(f"Failed to initialize ImageService: {str(e)}")
            self.image_service = None
    
    def _update_user_info(self, user_id: int, user) -> None:
        """Extract and update user info (first_name, username, last_seen) from Telegram user object."""
        try:
            settings = self.plan_keeper.settings_service.get_settings(user_id)
            updated = False
            
            # Update first_name if missing or changed
            if user.first_name:
                if settings.first_name != user.first_name:
                    settings.first_name = user.first_name
                    updated = True
            
            # Update username if missing or changed
            if user.username:
                if settings.username != user.username:
                    settings.username = user.username
                    updated = True
            
            # Always update last_seen
            from datetime import datetime
            settings.last_seen = datetime.now()
            updated = True
            
            if updated:
                self.plan_keeper.settings_service.save_settings(settings)
        except Exception as e:
            logger.warning(f"Failed to update user info for user {user_id}: {e}")
    
    async def _update_user_avatar_async(self, context: CallbackContext, user_id: int) -> None:
        """Fetch and store user avatar asynchronously (non-blocking)."""
        try:
            if context and context.bot:
                # Run avatar fetch in background (fire and forget)
                asyncio.create_task(
                    self.avatar_service.fetch_and_store_avatar(context.bot, user_id)
                )
        except Exception as e:
            logger.debug(f"Failed to schedule avatar fetch for user {user_id}: {e}")
    
    def get_user_timezone(self, user_id: int) -> str:
        """Get user timezone using the settings service."""
        return self.plan_keeper.settings_service.get_user_timezone(user_id)

    @staticmethod
    def _choose_from_options(user_text: str, options: list[dict]) -> Optional[str]:
        """
        Best-effort mapping of a free-form user reply to a value from options.

        Supports:
        - direct ID/value match (e.g., "P10")
        - 1-based index ("1" -> first option)
        - fuzzy title/label substring match

        Expected option keys (any subset):
        - "value" or "promise_id"
        - "label" or "title"
        """
        if not user_text or not options:
            return None
        text = str(user_text).strip()
        if not text:
            return None

        # 1) direct match against value-like fields
        upper = text.upper()
        for opt in options:
            if not isinstance(opt, dict):
                continue
            val = opt.get("value") or opt.get("promise_id")
            if val and str(val).upper() == upper:
                return str(val)

        # 2) numeric index (1-based)
        if text.isdigit():
            idx = int(text) - 1
            if 0 <= idx < len(options):
                val = options[idx].get("value") or options[idx].get("promise_id")
                if val:
                    return str(val)

        # 3) fuzzy match against label/title
        low = text.lower()
        for opt in options:
            if not isinstance(opt, dict):
                continue
            label = opt.get("label") or opt.get("title") or ""
            val = opt.get("value") or opt.get("promise_id")
            if val and label and low in str(label).lower():
                return str(val)
        return None
    
    def set_user_timezone(self, user_id: int, tzname: str) -> None:
        """Set user timezone using the settings service."""
        self.plan_keeper.settings_service.set_user_timezone(user_id, tzname)
    
    async def start(self, update: Update, context: CallbackContext) -> None:
        """Send a message when the command /start is issued."""
        user_id = update.effective_user.id
        user_lang = get_user_language(user_id)
        
        existing_promises = self.plan_keeper.get_promises(user_id)
        
        # Check if user has language preference set
        settings = self.plan_keeper.settings_service.get_settings(user_id)
        if len(existing_promises) == 0 and (not hasattr(settings, 'language') or settings.language == "en"):
            # New user without language preference - show language selection
            message = get_message("choose_language", user_lang)
            keyboard = language_selection_kb()
            await self.response_service.reply_text(
                update, message,
                user_id=user_id,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            return
        
        # Existing user or user with language preference
        if len(existing_promises) == 0:
            message = get_message("welcome_new", user_lang)
        else:
            message = get_message("welcome_return", user_lang)

        # Add mini app keyboard to welcome message
        keyboard = mini_app_kb(self.miniapp_url)

        await self.response_service.reply_text(
            update, message,
            user_id=user_id,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        
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
        
        await self.response_service.reply_text(
            update, message,
            user_id=user_id
        )
    
    async def nightly_reminders(self, update: Update, context: CallbackContext) -> None:
        """Handle the /nightly command to send nightly reminders."""
        user_id = update.effective_user.id
        await self.send_nightly_reminders(context, user_id=user_id)
    
    async def morning_reminders(self, update: Update, context: CallbackContext) -> None:
        """Handle the /morning command to send morning reminders."""
        user_id = update.effective_user.id
        await self.send_morning_reminders(context, user_id=user_id)
    
    async def weekly_report(self, update: Update, context: CallbackContext) -> None:
        """Handle the /weekly command to send a weekly report with a refresh button and visualization."""
        user_id = update.effective_user.id
        user_lang = get_user_language(user_id)
        report_ref_time = datetime.now()
        
        # Get weekly summary using the new service
        summary = self.plan_keeper.reports_service.get_weekly_summary(user_id, report_ref_time)
        report = weekly_report_text(summary)
        
        # Compute week boundaries based on report_ref_time.
        week_start, week_end = get_week_range(report_ref_time)
        date_range_str = f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b')}"
        
        # Create keyboard with refresh and mini app buttons
        keyboard = weekly_report_kb(report_ref_time, self.miniapp_url)
        
        header = get_message("weekly_header", user_lang, date_range=date_range_str)
        message_text = f"{header}\n\n{report}"

        # Telegram captions have a hard limit (1024 chars). Keep everything in one message by
        # truncating (instead of sending a 2nd message).
        # Ref: https://core.telegram.org/bots/api#sendphoto
        MAX_CAPTION_LEN = 1024
        if len(message_text) > MAX_CAPTION_LEN:
            message_text = message_text[: MAX_CAPTION_LEN - 1] + "…"
        
        # Image generation disabled - send text-only weekly report with mini app button
        # Note: Re-enable image generation if needed in the future
        # image_path = await self.plan_keeper.reports_service.generate_weekly_visualization_image(
        #     user_id, report_ref_time
        # )
        
        await self.response_service.reply_text(
            update, message_text,
            user_id=user_id,
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
        insights = self.llm_handler.get_response_custom(prompt, str(user_id))
        
        # Send the insights to the user
        message = get_message("zana_insights", user_lang, insights=insights)
        await self.response_service.reply_text(
            update, message,
            user_id=user_id,
            parse_mode='Markdown'
        )
    
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
                await self.response_service.reply_text(
                    update, message,
                    user_id=user_id
                )
                return
            
            # save
            self.set_user_timezone(user_id, tzname)
            # reschedule nightly/morning jobs if you have them
            await self._reschedule_user_jobs(user_id, tzname)
            message = get_message("timezone_set", user_lang, timezone=tzname)
            await self.response_service.reply_text(
                update, message,
                user_id=user_id
            )
            return
        
        # Ask for location
        kb = ReplyKeyboardMarkup(
            [[KeyboardButton(get_message("btn_share_location", user_lang), request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
            input_field_placeholder="Tap to share your location…",
        )
        message = get_message("timezone_location_request", user_lang)
        await self.response_service.reply_text(
            update, message,
            user_id=user_id,
            reply_markup=kb
        )
    
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
                await self.response_service.reply_text(
                    update, message,
                    user_id=user_id,
                    reply_markup=ReplyKeyboardRemove()
                )
                return
            
            self.set_user_timezone(user_id, tzname)
            message = get_message("timezone_location_success", user_lang, timezone=tzname)
            await self.response_service.reply_text(
                update, message,
                user_id=user_id,
                reply_markup=ReplyKeyboardRemove()
            )
        except ImportError:
            logger.error("timezonefinder not available")
            message = get_message("timezone_location_failed", user_lang)
            await self.response_service.reply_text(
                update, message,
                user_id=user_id,
                reply_markup=ReplyKeyboardRemove()
            )

    async def on_voice(self, update: Update, context: CallbackContext):
        """Handle voice messages with ASR and optional TTS response."""
        user_id = update.effective_user.id
        user_lang = get_user_language(update.effective_user)
        
        # Extract and update user info
        self._update_user_info(user_id, update.effective_user)
        # Fetch avatar in background (non-blocking)
        await self._update_user_avatar_async(context, user_id)
        
        # Get voice file
        voice = update.effective_message.voice
        if not voice:
            return
        
        file = await context.bot.get_file(voice.file_id)
        
        # Download to temp directory
        import tempfile
        import os
        temp_dir = tempfile.gettempdir()
        path = os.path.join(temp_dir, f"voice_{voice.file_unique_id}.ogg")
        await file.download_to_drive(path)

        
        try:
            # Check voice mode preference
            settings = self.plan_keeper.settings_service.get_settings(user_id)
            
            # Check if there's a text caption with the voice message
            voice_caption = update.effective_message.caption or ""
            
            # Send acknowledgment
            ack_message = get_message("voice_received", user_lang)
            await self.response_service.reply_text(
                update, ack_message,
                user_id=user_id,
                log_conversation=False  # Don't log acknowledgment
            )
            
            # If first time, ask about voice mode preference (but still process the message)
            if settings.voice_mode is None:
                message = get_message("voice_mode_prompt", user_lang)
                keyboard = voice_mode_selection_kb()
                await self.response_service.reply_text(
                    update, message,
                    user_id=user_id,
                    reply_markup=keyboard
                )
                # Continue processing the voice message even if preference not set yet
            
            # Transcribe voice with multi-language support
            user_lang_code = user_lang.value if user_lang else "en"
            
            # Use multi-language transcription that tries both user language and English
            transcription_result = self.voice_service.transcribe_voice_multi_language(
                path,
                user_language=user_lang_code,
                fallback_to_english=True
            )
            
            transcribed_text = transcription_result.text
            
            # Log transcription details
            if transcription_result.confidence > 0:
                logger.info(
                    f"Voice transcribed in {transcription_result.language_code} "
                    f"with confidence {transcription_result.confidence:.2f}"
                )
            
            # Combine transcribed text with caption if present
            if voice_caption and voice_caption.strip():
                if transcribed_text:
                    user_input = f"{voice_caption}\n\n{transcribed_text}".strip()
                else:
                    user_input = voice_caption.strip()
            else:
                user_input = transcribed_text if transcribed_text else ""
            
            if not user_input:
                error_msg = get_message("voice_transcription_failed", user_lang)
                await self.response_service.reply_text(
                    update, error_msg,
                    user_id=user_id
                )
                return
            
            # Send quick processing message
            processing_msg = await self.response_service.send_processing_message(
                update, user_id=user_id, user_lang=user_lang
            )
            
            # Create progress callback to show plan to user
            plan_message_to_send = None
            
            def progress_callback(event: str, payload: dict):
                nonlocal plan_message_to_send
                if event == "plan":
                    steps = payload.get("steps", [])
                    plan_message_to_send = self._format_plan_for_user(steps)
            
            # Process transcribed text as a regular message
            llm_response = self.llm_handler.get_response_api(
                user_input, str(user_id), 
                user_language=user_lang_code,
                progress_callback=progress_callback
            )
            
            # Check for errors
            if "error" in llm_response:
                error_msg = llm_response["response_to_user"]
                if user_lang and user_lang != Language.EN:
                    error_msg = translate_text(error_msg, user_lang.value, "en")
                
                # Edit processing message with error
                if processing_msg:
                    await self.response_service.edit_processing_message(
                        context, processing_msg, error_msg,
                        user_id=user_id, user_lang=user_lang
                    )
                else:
                    await self._send_response_with_voice_mode(
                        update, context, error_msg, settings, user_lang
                    )
                return
            
            # Process LLM response
            try:
                func_call_response = self.call_planner_api(user_id, llm_response)
                response_text = llm_response.get("response_to_user", "")
                formatted_response = self._format_response(response_text, func_call_response)
                
                # Edit processing message with final response
                if processing_msg:
                    await self.response_service.edit_processing_message(
                        context, processing_msg, formatted_response,
                        user_id=user_id, user_lang=user_lang
                    )
                else:
                    # Send response with voice mode if enabled
                    await self._send_response_with_voice_mode(
                        update, context, formatted_response, settings, user_lang
                    )
            except Exception as e:
                error_msg = get_message("error_general", user_lang, error=str(e))
                logger.error(f"Error processing voice message for user {user_id}: {str(e)}")
                
                # Edit processing message with error if available
                if processing_msg:
                    await self.response_service.edit_processing_message(
                        context, processing_msg, error_msg,
                        user_id=user_id, user_lang=user_lang
                    )
                else:
                    await self._send_response_with_voice_mode(
                        update, context, error_msg, settings, user_lang
                    )
        finally:
            # Clean up temp file
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"Failed to delete temp voice file {path}: {e}")
    
    async def _send_response_with_voice_mode(
        self, update: Update, context: CallbackContext, 
        text_response: str, settings, user_lang
    ):
        """Send response as voice if voice mode enabled, otherwise as text."""
        user_id = update.effective_user.id if update.effective_user else None
        
        if settings and settings.voice_mode == "enabled":
            try:
                # Synthesize speech (text will be cleaned inside synthesize_speech)
                user_lang_code = user_lang.value if user_lang else "en"
                speech_lang_map = {
                    "en": "en-US",
                    "fa": "fa-IR",
                    "fr": "fr-FR"
                }
                speech_lang = speech_lang_map.get(user_lang_code, "en-US")
                
                audio_bytes = self.voice_service.synthesize_speech(text_response, speech_lang)
                
                if audio_bytes:
                    # Send as voice message via ResponseService
                    import tempfile
                    import os
                    temp_dir = tempfile.gettempdir()
                    temp_path = os.path.join(temp_dir, f"tts_{update.effective_message.message_id}.ogg")
                    
                    try:
                        with open(temp_path, 'wb') as f:
                            f.write(audio_bytes)
                        
                        with open(temp_path, 'rb') as voice_file:
                            await self.response_service.reply_voice(
                                update, voice_file,
                                user_id=user_id
                            )
                    finally:
                        # Clean up temp file
                        try:
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                        except Exception:
                            pass
                    return
                else:
                    # TTS failed, fallback to text
                    logger.warning("TTS synthesis failed, falling back to text")
            except Exception as e:
                # TTS error, fallback to text
                logger.error(f"TTS error: {str(e)}, falling back to text")
        
        # Send as text (voice mode disabled or TTS failed) via ResponseService
        await self.response_service.reply_text(
            update, text_response,
            user_id=user_id
        )

    async def _reply_text_smart(self, message, text: str, user_id: Optional[int] = None) -> None:
        """
        Reply using the appropriate parse_mode via ResponseService.
        
        This is a transitional method - prefer using response_service.reply_text directly.

        - Our formatted responses are HTML (used for expandable blockquotes).
        - Most other bot messages/templates are Markdown.
        """
        safe_text = "" if text is None else str(text)
        looks_like_html = "<b>Zana:</b>" in safe_text or "<blockquote" in safe_text or "<pre>" in safe_text
        parse_mode = "HTML" if looks_like_html else "Markdown"
        
        # If we have user_id and can create an Update, use ResponseService
        # Otherwise fallback to direct reply (for edge cases)
        if user_id and hasattr(message, 'chat') and hasattr(message, 'reply_text'):
            # Try to create a minimal Update for ResponseService
            # For now, use direct reply as fallback
            try:
                await message.reply_text(safe_text, parse_mode=parse_mode)
            except Exception:
                await message.reply_text(safe_text)
        else:
            try:
                await message.reply_text(safe_text, parse_mode=parse_mode)
            except Exception:
                await message.reply_text(safe_text)

    @staticmethod
    def _format_plan_for_user(plan_steps: list) -> str:
        """
        Format plan steps into a user-friendly message.
        
        Only shows plans with 2+ tool steps to avoid clutter for simple operations.
        Returns None if plan should not be shown.
        """
        if not plan_steps:
            return None
        
        # Filter to only tool steps (skip internal respond/ask_user)
        tool_steps = [s for s in plan_steps if s.get("kind") == "tool"]
        
        if len(tool_steps) < 2:
            return None  # Don't show for single-step plans
        
        lines = ["🔄 *Working on it...*\n"]
        for i, step in enumerate(tool_steps, 1):
            purpose = step.get("purpose", "Processing...")
            lines.append(f"{i}. {purpose}")
        
        return "\n".join(lines)

    def _parse_slot_fill_values(
        self,
        user_text: str,
        missing_fields: list,
        user_id: int,
        user_lang_code: str,
    ) -> dict:
        """
        LLM-first parsing of user's clarification message into required fields.

        Parsing strategy:
        - If only one missing field, treat the whole message as the value (simple case).
        - Otherwise, use LLM to extract structured data with normalization.
        - Keep regex key-value parsing as lightweight fallback only.
        """
        missing_fields = [str(f) for f in (missing_fields or []) if f]
        text = (user_text or "").strip()
        if not text or not missing_fields:
            return {}

        # 1) Single-field shortcut (keep this simple case)
        if len(missing_fields) == 1:
            return {missing_fields[0]: text}

        # 2) LLM-based extraction (primary method for multiple fields)
        try:
            from langchain_core.messages import HumanMessage as LCHumanMessage, SystemMessage as LCSystemMessage

            # Build enhanced prompt with examples and normalization instructions
            field_descriptions = []
            for field in missing_fields:
                if field == "time_spent":
                    field_descriptions.append(
                        f"- time_spent: Time duration in hours (float). Accept formats: '2h', '2 hours', '90 minutes', '1.5h', 'four hours'. Normalize to float (e.g., '2h' → 2.0, '90 minutes' → 1.5)"
                    )
                elif field == "promise_id":
                    field_descriptions.append(
                        f"- promise_id: Promise identifier. Accept formats: 'P01', 'p01', '#P01', 'P-1', 'p-3'. Normalize to standard format (e.g., 'P01', 'P03')"
                    )
                elif field == "setting_value":
                    field_descriptions.append(
                        f"- setting_value: Setting value (string). Extract as-is from user message."
                    )
                else:
                    field_descriptions.append(f"- {field}: Extract the value from user message.")

            sys_content = (
                "Extract the requested fields from the user's message and normalize values.\n"
                "Output ONLY valid JSON (no markdown, no extra text).\n\n"
                f"Fields to extract:\n" + "\n".join(field_descriptions) + "\n\n"
                "Examples:\n"
                "- User: '4h' with field time_spent → {\"time_spent\": 4.0}\n"
                "- User: '90 minutes' with field time_spent → {\"time_spent\": 1.5}\n"
                "- User: 'P01' with field promise_id → {\"promise_id\": \"P01\"}\n"
                "- User: 'p-3' with field promise_id → {\"promise_id\": \"P03\"}\n"
                "- User: 'promise_id: P01, time_spent: 2h' → {\"promise_id\": \"P01\", \"time_spent\": 2.0}\n\n"
                "If a field is not provided or cannot be extracted, use null for that field.\n"
                "Always return a JSON object with all requested fields (use null for missing ones)."
            )

            sys = LCSystemMessage(content=sys_content)
            hm = LCHumanMessage(content=text)

            model = getattr(self.llm_handler, "chat_model", None)
            if model is None:
                # Fallback to regex if no LLM available
                return self._parse_slot_fill_values_regex_fallback(text, missing_fields)

            resp = model.invoke([sys, hm]) if hasattr(model, "invoke") else model([sys, hm])
            content = getattr(resp, "content", "") or ""
            
            # Try to extract JSON from response (might have markdown code blocks)
            json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
            
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                # Normalize promise_id if present
                if "promise_id" in parsed and parsed["promise_id"]:
                    from utils.promise_id import normalize_promise_id
                    try:
                        parsed["promise_id"] = normalize_promise_id(str(parsed["promise_id"]))
                    except Exception:
                        pass  # Keep original if normalization fails
                
                return {k: v for k, v in parsed.items() if k in missing_fields and v is not None}
        except Exception as e:
            logger.debug(f"LLM extraction failed for slot filling: {e}, falling back to regex")
            # Fallback to regex parsing
            return self._parse_slot_fill_values_regex_fallback(text, missing_fields)

        return {}
    
    def _parse_slot_fill_values_regex_fallback(self, text: str, missing_fields: list) -> dict:
        """Lightweight regex-based fallback for slot filling."""
        out = {}
        field_lut = {f.lower(): f for f in missing_fields}
        for line in [ln.strip() for ln in text.splitlines() if ln.strip()]:
            sep = ":" if ":" in line else ("=" if "=" in line else None)
            if not sep:
                continue
            k, v = [p.strip() for p in line.split(sep, 1)]
            if not k:
                continue
            key_norm = k.lower()
            if key_norm in field_lut:
                out[field_lut[key_norm]] = v
        return out

    async def on_image(self, update: Update, context: CallbackContext):
        """Handle image messages with VLM parsing and text extraction."""
        user_id = update.effective_user.id
        user_lang = get_user_language(update.effective_user)
        
        # Extract and update user info
        self._update_user_info(user_id, update.effective_user)
        # Fetch avatar in background (non-blocking)
        await self._update_user_avatar_async(context, user_id)
        
        msg = update.effective_message
        
        # Get image file
        if msg.photo:
            # Photo: pick the largest size
            file_id = msg.photo[-1].file_id
        else:
            # Image as document (PNG/JPG)
            file_id = msg.document.file_id
        
        file = await context.bot.get_file(file_id)
        
        # Download image
        import tempfile
        import os
        temp_dir = tempfile.gettempdir()
        path = os.path.join(temp_dir, f"image_{file.file_unique_id}")
        await file.download_to_drive(path)
        
        try:
            # Send acknowledgment
            ack_message = get_message("image_received", user_lang)
            await self.response_service.reply_text(
                update, ack_message,
                user_id=user_id,
                log_conversation=False  # Don't log acknowledgment
            )
            
            # Parse image with VLM
            try:
                if self.image_service is None:
                    error_msg = get_message("image_processing_failed", user_lang)
                    await self.response_service.reply_text(
                        update, f"{error_msg}\n\nImage processing service is not available.",
                        user_id=user_id
                    )
                    return
                
                # Use Telegram's file_path (URL) if available, otherwise use local file
                file_url = file.file_path
                
                # Parse image
                analysis = self.image_service.parse_image(path, image_url=file_url)
                
                # Extract text for processing
                extracted_text = self.image_service.extract_text_for_processing(analysis)
                
                if not extracted_text or not analysis.text or len(analysis.text.strip()) == 0:
                    # No text found in image
                    error_msg = get_message("image_no_text", user_lang)
                    await self.response_service.reply_text(
                        update, error_msg,
                        user_id=user_id
                    )
                    return
                
                # Log extracted content for debugging
                logger.info(f"Image analysis - Type: {analysis.type}, Text length: {len(analysis.text)}, Language: {analysis.meta.language}")
                
                # Use extracted text as user message input with context
                # This helps the LLM understand it's processing extracted image content
                user_message = f"I've extracted the following content from an image:\n\n{extracted_text}\n\nPlease help me process this content."
                
                # Process through LLM
                user_lang_code = user_lang.value if user_lang else "en"
                
                # Send quick processing message
                processing_msg = await self.response_service.send_processing_message(
                    update, user_id=user_id, user_lang=user_lang
                )
                
                # Create progress callback to show plan to user
                plan_message_to_send = None
                
                def progress_callback(event: str, payload: dict):
                    nonlocal plan_message_to_send
                    if event == "plan":
                        steps = payload.get("steps", [])
                        plan_message_to_send = self._format_plan_for_user(steps)
                
                llm_response = self.llm_handler.get_response_api(
                    user_message, str(user_id), 
                    user_language=user_lang_code,
                    progress_callback=progress_callback
                )
                
                # Check for errors
                if "error" in llm_response:
                    error_msg = llm_response["response_to_user"]
                    if user_lang and user_lang != Language.EN:
                        error_msg = translate_text(error_msg, user_lang.value, "en")
                    
                    # Edit processing message with error
                    if processing_msg:
                        await self.response_service.edit_processing_message(
                            context, processing_msg, error_msg,
                            user_id=user_id, user_lang=user_lang,
                            parse_mode='Markdown'
                        )
                    else:
                        await self.response_service.reply_text(
                            update, error_msg,
                            user_id=user_id,
                            parse_mode='Markdown'
                        )
                    return
                
                # Process LLM response
                try:
                    func_call_response = self.call_planner_api(user_id, llm_response)
                    # LLM should already respond in target language - trust it, translation happens in ResponseService as fallback
                    response_text = llm_response['response_to_user']
                    
                    formatted_response = self._format_response(response_text, func_call_response)
                    
                    # Edit processing message with final response
                    if processing_msg:
                        await self.response_service.edit_processing_message(
                            context, processing_msg, formatted_response,
                            user_id=user_id, user_lang=user_lang
                        )
                    else:
                        # Get settings for voice mode
                        settings = self.plan_keeper.settings_service.get_settings(user_id)
                        
                        # Send response (with voice mode if enabled)
                        await self._send_response_with_voice_mode(
                            update, context, formatted_response, settings, user_lang
                        )
                except Exception as e:
                    error_msg = get_message("error_general", user_lang, error=str(e))
                    logger.error(f"Error processing image for user {user_id}: {str(e)}")
                    await self.response_service.reply_text(
                        update, error_msg,
                        user_id=user_id
                    )
                    
            except Exception as e:
                error_msg = get_message("image_processing_failed", user_lang)
                logger.error(f"Image processing error: {str(e)}", exc_info=True)
                # Provide more context in error message
                detailed_error = f"{error_msg}\n\nError details: {str(e)}"
                await self.response_service.reply_text(
                    update, detailed_error,
                    user_id=user_id
                )
        finally:
            # Clean up temp file
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"Failed to delete temp image file {path}: {e}")

    async def on_poll_created(self, update: Update, context: CallbackContext):
        poll = update.effective_message.poll
        user_id = update.effective_user.id
        user_lang = get_user_language(update.effective_user)
        # You can store poll.id ↔ chat/message mapping if you plan to track answers
        message = get_message("poll_detected", user_lang, question=poll.question)
        await self.response_service.reply_text(
            update, message,
            user_id=user_id
        )

    async def on_poll_answer(self, update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        user_lang = get_user_language(update.effective_user)
        message = get_message("poll_answer_not_implemented", user_lang)
        await self.response_service.reply_text(
            update, message,
            user_id=user_id
        )

    async def on_todo_text(self, update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        user_lang = get_user_language(update.effective_user)
        message = get_message("todo_not_implemented", user_lang)
        await self.response_service.reply_text(
            update, message,
            user_id=user_id
        )

    async def handle_message(self, update: Update, context: CallbackContext) -> None:
        """Handle general text messages."""
        try:
            user_message = update.message.text
            user_id = update.effective_user.id
            user_group_id = update.effective_chat.id if update.effective_chat.type in ['group', 'supergroup'] else None
            user_lang = get_user_language(update.effective_user)
            
            # Extract and update user info (first_name, username, last_seen)
            self._update_user_info(user_id, update.effective_user)
            # Fetch avatar in background (non-blocking)
            await self._update_user_avatar_async(context, user_id)
            
            # Log user message
            self.response_service.log_user_message(
                user_id=user_id,
                content=user_message,
                message_id=update.message.message_id,
                chat_id=update.effective_chat.id if update.effective_chat else None,
            )

            # Check for broadcast state
            broadcast_state = context.user_data.get('broadcast_state') if context.user_data else None
            if broadcast_state == 'waiting_message':
                await self._handle_broadcast_message(update, context, user_message, user_id, user_lang)
                return
            elif broadcast_state == 'waiting_time':
                await self._handle_broadcast_time(update, context, user_message, user_id, user_lang)
                return

            # Stateful clarification: if we previously asked for missing fields, treat this message as the answer.
            pending = (context.user_data or {}).get("pending_clarification") if hasattr(context, "user_data") else None
            if pending:
                missing_fields = pending.get("missing_fields") or []
                partial_args = dict(pending.get("partial_args") or {})
                original_user_message = pending.get("original_user_message") or ""
                options = pending.get("options") or []

                user_lang_code = user_lang.value if user_lang else "en"
                filled = self._parse_slot_fill_values(
                    user_text=user_message,
                    missing_fields=missing_fields,
                    user_id=user_id,
                    user_lang_code=user_lang_code,
                )
                
                # Replace instead of merge: if single field, replace entirely with new input
                if len(missing_fields) == 1:
                    # Single field: replace entirely with new input
                    chosen = self._choose_from_options(user_message, options) if options else None
                    partial_args[missing_fields[0]] = (chosen or user_message.strip())
                else:
                    # Multiple fields: only update parsed values
                    partial_args.update({k: v for k, v in (filled or {}).items() if v})
                
                still_missing = [f for f in missing_fields if partial_args.get(f) in (None, "", [])]

                if still_missing:
                    # Update partial args and ask again (single message, all missing).
                    try:
                        context.user_data["pending_clarification"]["partial_args"] = partial_args
                    except Exception:
                        pass
                    fields = ", ".join(still_missing)
                    await self.response_service.reply_text(
                        update,
                        f"Thanks — I'm still missing: {fields}.\n"
                        f"Please reply with `field: value` for: {fields}.",
                        user_id=user_id,
                        parse_mode="Markdown",
                    )
                    return

                # We have enough: clear pending and re-run the agent with the original intent + provided fields.
                try:
                    context.user_data.pop("pending_clarification", None)
                except Exception:
                    pass

                fields_block = "\n".join([f"{k}: {partial_args.get(k)}" for k in missing_fields])
                augmented_message = (
                    f"{original_user_message}\n\n"
                    f"Clarifications provided:\n{fields_block}\n"
                ).strip()
                user_lang_code = user_lang.value if user_lang else "en"
                
                # Send quick processing message
                processing_msg = await self.response_service.send_processing_message(
                    update, user_id=user_id, user_lang=user_lang
                )
                
                # Create progress callback to show plan to user
                plan_message_to_send = None
                
                def progress_callback(event: str, payload: dict):
                    nonlocal plan_message_to_send
                    if event == "plan":
                        steps = payload.get("steps", [])
                        plan_message_to_send = self._format_plan_for_user(steps)
                
                llm_response = self.llm_handler.get_response_api(
                    augmented_message, user_id, 
                    user_language=user_lang_code,
                    progress_callback=progress_callback
                )

                # Handle errors in LLM response
                if "error" in llm_response:
                    error_msg = llm_response["response_to_user"]
                    if user_lang and user_lang != Language.EN:
                        error_msg = translate_text(error_msg, user_lang.value, "en")
                    
                    # Edit processing message with error
                    if processing_msg:
                        await self.response_service.edit_processing_message(
                            context, processing_msg, error_msg,
                            user_id=user_id, user_lang=user_lang,
                            parse_mode="Markdown"
                        )
                    else:
                        await self.response_service.reply_text(
                            update, error_msg,
                            user_id=user_id,
                            parse_mode="Markdown"
                        )
                    return

                # Store a new pending clarification if the agent asked again
                if llm_response.get("pending_clarification"):
                    try:
                        context.user_data["pending_clarification"] = {
                            **(llm_response.get("pending_clarification") or {}),
                            "original_user_message": original_user_message,
                        }
                    except Exception:
                        pass

                # Process response as normal
                func_call_response = self.call_planner_api(user_id, llm_response)
                tool_outputs = llm_response.get("tool_outputs") or []
                
                # Check if visualization should be sent
                viz_sent = await self._handle_weekly_visualization_if_present(
                    update, context, func_call_response, tool_outputs,
                    user_id, user_lang, processing_msg
                )
                if viz_sent:
                    return  # Image already sent, don't send text response
                
                # LLM should already respond in target language - trust it, translation happens in ResponseService as fallback
                response_text = llm_response.get("response_to_user", "")
                
                formatted_response = self._format_response(response_text, func_call_response)
                
                # Edit processing message with final response
                if processing_msg:
                    await self.response_service.edit_processing_message(
                        context, processing_msg, formatted_response,
                        user_id=user_id, user_lang=user_lang
                    )
                else:
                    await self.response_service.reply_text(
                        update, formatted_response,
                        user_id=user_id
                    )
                return
            
            # Check for URLs in the message
            urls = self.content_service.detect_urls(user_message)
            if urls:
                # Process the first URL found
                url = urls[0]
                await self._handle_link_message(update, context, url, user_id, user_lang)
                return
            
            # Get user language code for LLM
            user_lang_code = user_lang.value if user_lang else "en"
            
            # Send quick processing message
            processing_msg = await self.response_service.send_processing_message(
                update, user_id=user_id, user_lang=user_lang
            )
            
            # Create progress callback to show plan to user
            plan_message_to_send = None
            
            def progress_callback(event: str, payload: dict):
                nonlocal plan_message_to_send
                if event == "plan":
                    steps = payload.get("steps", [])
                    plan_message_to_send = self._format_plan_for_user(steps)
            
            llm_response = self.llm_handler.get_response_api(
                user_message, user_id, 
                user_language=user_lang_code,
                progress_callback=progress_callback
            )
            
            # Check for errors in LLM response
            if "error" in llm_response:
                # LLM should already respond in target language - trust it, translation happens in ResponseService as fallback
                error_msg = llm_response["response_to_user"]
                
                # Edit processing message with error
                if processing_msg:
                    await self.response_service.edit_processing_message(
                        context, processing_msg, error_msg,
                        user_id=user_id, user_lang=user_lang,
                        parse_mode='Markdown'
                    )
                else:
                    await self.response_service.reply_text(
                        update, error_msg,
                        user_id=user_id,
                        parse_mode='Markdown'
                    )
                return
            
            # Process the LLM response
            try:
                func_call_response = self.call_planner_api(user_id, llm_response)
                tool_outputs = llm_response.get("tool_outputs") or []
                
                # Check if visualization should be sent
                viz_sent = await self._handle_weekly_visualization_if_present(
                    update, context, func_call_response, tool_outputs,
                    user_id, user_lang, processing_msg
                )
                if viz_sent:
                    return  # Image already sent, don't send text response
                
                # LLM should already respond in target language - trust it, translation happens in ResponseService as fallback
                response_text = llm_response['response_to_user']
                
                formatted_response = self._format_response(response_text, func_call_response)
            except ValueError as e:
                formatted_response = get_message("error_invalid_input", user_lang, error=str(e))
                logger.error(f"Validation error for user {user_id}: {str(e)}")
            except Exception as e:
                formatted_response = get_message("error_general", user_lang, error=str(e))
                logger.error(f"Error processing request for user {user_id}: {str(e)}")

            # If the agent is asking for clarification, store pending state for the next message.
            if llm_response.get("pending_clarification"):
                try:
                    if hasattr(context, "user_data") and context.user_data is not None:
                        context.user_data["pending_clarification"] = {
                            **(llm_response.get("pending_clarification") or {}),
                            "original_user_message": user_message,
                            "asked_at": datetime.utcnow().isoformat(),
                        }
                except Exception:
                    pass

            # Edit processing message with final response
            if processing_msg:
                await self.response_service.edit_processing_message(
                    context, processing_msg, formatted_response,
                    user_id=user_id, user_lang=user_lang
                )
            else:
                # Fallback if processing message wasn't sent
                try:
                    await self.response_service.reply_text(
                        update, formatted_response,
                        user_id=user_id
                    )
                except Exception:
                    await self.response_service.reply_text(
                        update, formatted_response,
                        user_id=user_id,
                        auto_translate=False  # Already translated
                    )
        
        except Exception as e:
            user_lang = get_user_language(update.effective_user)
            message = get_message("error_unexpected", user_lang, error=str(e))
            await update.message.reply_text(message, parse_mode='Markdown')
            logger.error(f"Unexpected error handling message from user {update.effective_user.id}: {str(e)}")
    
    async def _handle_weekly_visualization_if_present(
        self, update: Update, context: CallbackContext, 
        func_call_response, tool_outputs: list, 
        user_id: int, user_lang: Language, processing_msg=None
    ) -> bool:
        """
        Check if any tool output contains weekly visualization marker and send image if found.
        
        Args:
            func_call_response: Can be a string (direct tool call) or list (when executed_by_agent is True)
            tool_outputs: List of tool output strings from agent execution
        
        Returns:
            True if visualization was sent, False otherwise
        """
        viz_marker = None
        
        # Check func_call_response (can be string or list)
        if isinstance(func_call_response, str) and "[WEEKLY_VIZ:" in func_call_response:
            match = re.search(r'\[WEEKLY_VIZ:([^\]]+)\]', func_call_response)
            if match:
                viz_marker = match.group(1)
        elif isinstance(func_call_response, list):
            # When executed_by_agent is True, func_call_response is the tool_outputs list
            for output in func_call_response:
                if isinstance(output, str) and "[WEEKLY_VIZ:" in output:
                    match = re.search(r'\[WEEKLY_VIZ:([^\]]+)\]', output)
                    if match:
                        viz_marker = match.group(1)
                        break
        
        # Check tool_outputs (separate from func_call_response)
        if not viz_marker and tool_outputs:
            for output in tool_outputs:
                if isinstance(output, str) and "[WEEKLY_VIZ:" in output:
                    match = re.search(r'\[WEEKLY_VIZ:([^\]]+)\]', output)
                    if match:
                        viz_marker = match.group(1)
                        break
        
        if not viz_marker:
            return False
        
        try:
            # Parse the timestamp
            ref_time = datetime.fromisoformat(viz_marker.replace('Z', '+00:00'))
            
            # Get weekly summary for caption
            summary = self.plan_keeper.reports_service.get_weekly_summary(user_id, ref_time)
            report = weekly_report_text(summary)
            
            # Compute week boundaries
            week_start, week_end = get_week_range(ref_time)
            date_range_str = f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b')}"
            
            # Get header
            header = get_message("weekly_header", user_lang, date_range=date_range_str)
            message_text = f"{header}\n\n{report}"
            
            # Truncate if needed
            MAX_MESSAGE_LEN = 4096
            if len(message_text) > MAX_MESSAGE_LEN:
                message_text = message_text[: MAX_MESSAGE_LEN - 1] + "…"
            
            # Image generation disabled - send text-only weekly report with mini app button
            # Re-enable image generation if needed in the future
            # image_path = await self.plan_keeper.reports_service.generate_weekly_visualization_image(
            #     user_id, ref_time
            # )
            
            # Create keyboard with refresh and mini app buttons
            keyboard = weekly_report_kb(ref_time, self.miniapp_url)
            
            # Send text message with keyboard
            await self.response_service.reply_text(
                update, message_text,
                user_id=user_id,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            
            # Delete processing message if it exists
            if processing_msg:
                try:
                    await processing_msg.delete()
                except Exception:
                    pass
            
            return True
        except Exception as e:
            logger.error(f"Error generating weekly visualization: {e}")
            return False

    def _format_response(self, llm_response: str, func_call_response) -> str:
        """Format the response for Telegram."""
        try:
            return format_response_html(llm_response, func_call_response)
        except Exception as e:
            logger.error(f"Error formatting response: {str(e)}")
            return "Error formatting response"
    
    def call_planner_api(self, user_id: int, llm_response: dict) -> str:
        """Process user message by sending it to the LLM and executing the identified action."""
        try:
            # If the agent already executed tools, avoid double-calling the API.
            if llm_response.get("executed_by_agent"):
                return llm_response.get("tool_outputs") or ""

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
    
    async def cmd_language(self, update: Update, context: CallbackContext) -> None:
        """Handle the /language command to change language preference."""
        user_id = update.effective_user.id
        user_lang = get_user_language(user_id)
        
        message = get_message("choose_language", user_lang)
        keyboard = language_selection_kb()
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode='Markdown')

    async def _handle_link_message(self, update: Update, context: CallbackContext, 
                                   url: str, user_id: int, user_lang: Language) -> None:
        """Handle message containing a URL."""
        try:
            # Send acknowledgment
            link_detected_msg = get_message("link_detected", user_lang)
            await update.message.reply_text(link_detected_msg)
            
            # Process the link
            link_metadata = self.content_service.process_link(url)
            url_type = link_metadata.get('type', 'unknown')
            
            processing_msg = get_message("link_processing", user_lang, url_type=url_type)
            processing_msg_obj = await update.message.reply_text(processing_msg)
            
            # Estimate time needed (already rounded to 5 minutes by the service)
            estimated_duration = self.plan_keeper.time_estimation_service.estimate_content_duration(
                link_metadata, user_id
            )
            
            # Convert to minutes for display and checks
            estimated_minutes = estimated_duration * 60 if estimated_duration else 0
            
            # Format duration string
            if estimated_duration and estimated_duration > 0:
                if estimated_duration < 1.0:
                    duration_str = f"{int(estimated_minutes)} minutes"
                else:
                    hours = int(estimated_duration)
                    minutes = int((estimated_duration - hours) * 60)
                    if minutes > 0:
                        duration_str = f"{hours}h {minutes}m"
                    else:
                        duration_str = f"{hours} hour{'s' if hours > 1 else ''}"
            else:
                duration_str = "Unknown"
            
            # Generate summary
            title = link_metadata.get('title', 'Content')
            description = link_metadata.get('description', 'No description available')
            
            # Check if content is long enough for summarization (>= 5 minutes)
            can_summarize = estimated_minutes >= 5
            
            # Check if content is long enough for calendar (>= 2 minutes)
            show_calendar = estimated_minutes >= 2
            
            # Generate Google Calendar link only if needed
            calendar_url = None
            if show_calendar and estimated_duration:
                tzname = self.get_user_timezone(user_id)
                suggested_time = suggest_time_slot(
                    estimated_duration,
                    preferred_hour=9,
                    preferred_minute=0
                )
                
                # Make timezone-aware if needed
                try:
                    from zoneinfo import ZoneInfo
                    if suggested_time.tzinfo is None:
                        tz = ZoneInfo(tzname)
                        suggested_time = suggested_time.replace(tzinfo=tz)
                except Exception:
                    pass  # Fallback to naive datetime
                
                calendar_url = generate_google_calendar_link(
                    title=title,
                    start_time=suggested_time,
                    duration_hours=estimated_duration,
                    description=f"{description}\n\nLink: {url}",
                    timezone=tzname
                )
            
            # Build response message - only show duration if it's known and >= 2 minutes
            if estimated_duration and estimated_duration > 0 and estimated_minutes >= 2:
                summary_msg = get_message("link_summary", user_lang, 
                                        title=title,
                                        description=description[:300] + ('...' if len(description) > 300 else ''),
                                        duration=duration_str)
            else:
                # Don't show duration or "too short" message - just show title and description
                summary_msg = f"📄 *{title}*\n\n{description[:300]}{'...' if len(description) > 300 else ''}"
            
            # Build full message
            if show_calendar:
                calendar_question = get_message("link_calendar_question", user_lang)
                full_message = f"{summary_msg}\n\n{calendar_question}"
            else:
                # Don't show "too short" message - just show the summary
                full_message = summary_msg
            
            # Store URL in bot_data with a short ID to avoid callback_data size limit
            url_id = None
            if can_summarize:
                import hashlib
                url_id = hashlib.md5(url.encode()).hexdigest()[:8]  # 8-char ID
                
                # Store in bot_data (accessed via application)
                if 'content_urls' not in self.application.bot_data:
                    self.application.bot_data['content_urls'] = {}
                self.application.bot_data['content_urls'][url_id] = url
            
            # Create keyboard with actions
            keyboard = content_actions_kb(
                calendar_url=calendar_url,
                url=url,
                can_summarize=can_summarize,
                url_id=url_id
            )
            
            # Delete processing message and send final response
            try:
                await processing_msg_obj.delete()
            except Exception:
                pass
            
            await update.message.reply_text(
                full_message, 
                parse_mode='Markdown', 
                disable_web_page_preview=True,
                reply_markup=keyboard
            )
        
        except Exception as e:
            logger.error(f"Error handling link message for user {user_id}: {str(e)}")
            error_msg = get_message("error_general", user_lang, error=str(e))
            await update.message.reply_text(error_msg)
    
    async def cmd_version(self, update: Update, context: CallbackContext) -> None:
        """Handle the /version command to show bot version."""
        user_id = update.effective_user.id
        user_lang = get_user_language(update.effective_user)
        
        version_info = get_version_info()

        def _md_code(v) -> str:
            s = "—" if v is None else str(v)
            return s.replace("`", "'")

        def _fmt_started_utc(v) -> str:
            """Format ISO datetime into a compact UTC string."""
            if not v:
                return "—"
            s = str(v).strip()
            try:
                # Handle common variants: "+00:00" or trailing "Z"
                s_norm = s.replace("Z", "+00:00")
                from datetime import datetime as _dt  # local import to avoid broad file changes
                dt = _dt.fromisoformat(s_norm)
                # Always display as UTC label (value is already stored in UTC).
                return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except Exception:
                # Fallback: best-effort string trimming
                if "T" in s:
                    s = s.replace("T", " ")
                if "+" in s:
                    s = s.split("+", 1)[0].strip()
                return f"{s} UTC"

        def _fmt_uptime(seconds) -> str:
            """Format uptime seconds into a human-friendly duration."""
            try:
                total = int(seconds)
            except Exception:
                return "—"
            if total < 0:
                total = 0

            days, rem = divmod(total, 86400)
            hours, rem = divmod(rem, 3600)
            minutes, secs = divmod(rem, 60)

            parts = []
            if days:
                parts.append(f"{days}d")
            if hours:
                parts.append(f"{hours}h")
            if minutes:
                parts.append(f"{minutes}m")
            if secs or not parts:
                parts.append(f"{secs}s")
            return " ".join(parts)

        lines = ["*Zana AI Bot — Version*"]
        lines.append(f"- Version: `{_md_code(version_info.get('version'))}`")
        lines.append(f"- Environment: `{_md_code(version_info.get('environment', 'unknown'))}`")

        if version_info.get("build_date"):
            lines.append(f"- Build date: `{_md_code(version_info.get('build_date'))}`")

        if version_info.get("last_update") and version_info.get("last_update") != "unknown":
            lines.append(f"- Last update: `{_md_code(version_info.get('last_update'))}`")

        # Commit information from build-time metadata
        if version_info.get("commit"):
            lines.append(f"- Commit: `{_md_code(version_info.get('commit'))}`")
        if version_info.get("commit_message"):
            lines.append(f"- Commit message: `{_md_code(version_info.get('commit_message'))}`")
        if version_info.get("commit_author"):
            lines.append(f"- Commit author: `{_md_code(version_info.get('commit_author'))}`")
        if version_info.get("commit_date"):
            lines.append(f"- Commit date: `{_md_code(version_info.get('commit_date'))}`")

        # Runtime metadata
        if version_info.get("started_at_utc"):
            lines.append(f"- Started (UTC): `{_md_code(_fmt_started_utc(version_info.get('started_at_utc')))} `")
        if "uptime_seconds" in version_info:
            lines.append(f"- Uptime: `{_md_code(_fmt_uptime(version_info.get('uptime_seconds')))} `")
        if version_info.get("pid") is not None:
            lines.append(f"- PID: `{_md_code(version_info.get('pid'))}`")
        if version_info.get("python"):
            lines.append(f"- Python: `{_md_code(version_info.get('python'))}`")

        # Git status-like section
        git_info = version_info.get("git") or {}
        if git_info.get("available"):
            lines.append("")
            lines.append("*Git*")
            if git_info.get("branch"):
                lines.append(f"- Branch: `{_md_code(git_info.get('branch'))}`")
            if git_info.get("head_short"):
                lines.append(f"- Commit: `{_md_code(git_info.get('head_short'))}`")
            if git_info.get("commit_date_iso"):
                lines.append(f"- Commit date: `{_md_code(git_info.get('commit_date_iso'))}`")

            ahead = git_info.get("ahead")
            behind = git_info.get("behind")
            if ahead is not None or behind is not None:
                lines.append(f"- Ahead/behind: `{_md_code(ahead)} / {_md_code(behind)}`")

            dirty = "dirty" if git_info.get("dirty") else "clean"
            lines.append(
                f"- Status: `{dirty}` (changed: `{_md_code(git_info.get('changed_files'))}`, "
                f"untracked: `{_md_code(git_info.get('untracked_files'))}`)"
            )

        # Database statistics
        try:
            stats = get_aggregate_stats(self.root_dir)
            lines.append("")
            lines.append("*Database Statistics*")
            lines.append(f"- Total users: `{stats.get('total_users', 0)}`")
            lines.append(f"- Total promises: `{stats.get('total_promises', 0)}`")
            lines.append(f"- Actions (24h): `{stats.get('actions_24h', 0)}`")
        except Exception as e:
            logger.warning(f"Error getting database stats: {e}")
            # Don't fail the version command if stats fail

        text = "\n".join(lines)
        # Telegram message limits: keep it safe.
        if len(text) > 3500:
            text = text[:3499] + "…"

        await update.message.reply_text(text, parse_mode='Markdown')

    async def cmd_me(self, update: Update, context: CallbackContext) -> None:
        """Handle the /me command to show user profile information (DM-only)."""
        chat = update.effective_chat
        msg = update.effective_message
        user = update.effective_user

        if not chat or not msg or not user:
            return

        # DM-only: in groups/supergroups, ask the user to DM the bot instead.
        if chat.type in ["group", "supergroup"]:
            await msg.reply_text("Please DM me to use `/me`.", parse_mode="Markdown")
            return

        user_id = user.id

        # Bot-side settings (best-effort; don't crash if fields differ).
        settings = None
        try:
            settings = self.plan_keeper.settings_service.get_settings(user_id)
        except Exception:
            settings = None

        timezone = getattr(settings, "timezone", None) if settings else None
        preferred_language = getattr(settings, "language", None) if settings else None

        full_name = getattr(user, "full_name", None) or "Unknown"
        username = getattr(user, "username", None)
        language_code = getattr(user, "language_code", None)

        def _md_code(value) -> str:
            """Return a safe Markdown inline-code representation."""
            s = "—" if value is None else str(value)
            # Inline-code uses backticks; replace any backticks to avoid breaking Markdown parsing.
            return s.replace("`", "'")

        # Keep dynamic values inside code formatting to avoid Markdown issues.
        lines = [
            "*Your info*",
            f"- Name: `{_md_code(full_name)}`",
            f"- User ID: `{_md_code(user_id)}`",
            f"- Username: `{_md_code(('@' + username) if username else None)}`",
            f"- Telegram language: `{_md_code(language_code)}`",
            f"- Timezone: `{_md_code(timezone)}`",
            f"- Preferred language: `{_md_code(preferred_language)}`",
            f"- Chat ID: `{_md_code(chat.id)}`",
            f"- Chat type: `{_md_code(chat.type)}`",
        ]
        caption = "\n".join(lines)

        # Telegram captions have a hard limit (1024 chars). Keep it safe.
        MAX_CAPTION_LEN = 1024
        if len(caption) > MAX_CAPTION_LEN:
            caption = caption[: MAX_CAPTION_LEN - 1] + "…"

        # Fetch profile photo (best-effort); fallback to text-only.
        try:
            photos = await context.bot.get_user_profile_photos(user_id=user_id, limit=1)
            photo_file_id = None
            if photos and getattr(photos, "total_count", 0) and getattr(photos, "photos", None):
                # photos.photos is a list of photo-size lists; pick the largest size.
                photo_file_id = photos.photos[0][-1].file_id

            if photo_file_id:
                await context.bot.send_photo(
                    chat_id=chat.id,
                    photo=photo_file_id,
                    caption=caption,
                    parse_mode="Markdown",
                )
            else:
                await msg.reply_text(caption, parse_mode="Markdown")
        except Exception:
            await msg.reply_text(caption, parse_mode="Markdown")
    
    async def cmd_broadcast(self, update: Update, context: CallbackContext) -> None:
        """Handle the /broadcast command for admins to schedule broadcast messages."""
        user_id = update.effective_user.id
        user_lang = get_user_language(update.effective_user)
        
        # Check admin status
        if not is_admin(user_id):
            message = "❌ You don't have permission to use this command."
            await update.message.reply_text(message)
            logger.warning(f"Non-admin user {user_id} attempted to use /broadcast")
            return
        
        # Set state to waiting for message
        if 'user_data' not in context:
            context.user_data = {}
        context.user_data['broadcast_state'] = 'waiting_message'
        context.user_data['broadcast_admin_id'] = user_id
        
        message = "📢 **Broadcast Message**\n\nPlease send the message you want to broadcast to all users."
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def _handle_broadcast_message(
        self, update: Update, context: CallbackContext, 
        message_text: str, user_id: int, user_lang: Language
    ) -> None:
        """Handle broadcast message input (show preview with Schedule/Cancel buttons)."""
        # Store the message
        context.user_data['broadcast_message'] = message_text
        
        # Show preview with Schedule/Cancel buttons
        preview_text = f"**Preview:**\n──────────────\n{message_text}\n──────────────\n\nSend to all users?"
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📅 Schedule", callback_data=encode_cb("broadcast_schedule")),
                InlineKeyboardButton("❌ Cancel", callback_data=encode_cb("broadcast_cancel"))
            ]
        ])
        
        await update.message.reply_text(preview_text, parse_mode='Markdown', reply_markup=keyboard)
    
    async def _handle_broadcast_time(
        self, update: Update, context: CallbackContext,
        time_str: str, user_id: int, user_lang: Language
    ) -> None:
        """Handle broadcast time input and schedule the broadcast."""
        # Get admin timezone
        admin_tz = self.get_user_timezone(user_id) or "UTC"
        
        # Parse time
        scheduled_time = parse_broadcast_time(time_str, admin_tz)
        
        if scheduled_time is None:
            error_msg = (
                f"❌ Could not parse time: '{time_str}'\n\n"
                f"Please use one of these formats:\n"
                f"• ISO: `YYYY-MM-DD HH:MM` (e.g., 2024-01-15 14:30)\n"
                f"• Natural: `tomorrow 2pm`, `in 1 hour`, etc.\n\n"
                f"Your timezone: {admin_tz}"
            )
            await update.message.reply_text(error_msg, parse_mode='Markdown')
            return
        
        # Check if time is in the past
        now = datetime.now(ZoneInfo(admin_tz))
        if scheduled_time < now:
            error_msg = f"❌ The specified time is in the past: {scheduled_time.strftime('%Y-%m-%d %H:%M')}"
            await update.message.reply_text(error_msg)
            return
        
        # Get broadcast message
        broadcast_message = context.user_data.get('broadcast_message')
        if not broadcast_message:
            await update.message.reply_text("❌ Error: Broadcast message not found. Please start over with /broadcast")
            context.user_data.pop('broadcast_state', None)
            return
        
        # Get all users
        user_ids = get_all_users(self.root_dir)
        if not user_ids:
            await update.message.reply_text("❌ No users found to broadcast to.")
            context.user_data.pop('broadcast_state', None)
            return
        
        # Convert to UTC for scheduling
        scheduled_time_utc = scheduled_time.astimezone(ZoneInfo("UTC"))
        
        # Schedule the broadcast
        job_name = f"broadcast-{user_id}-{int(scheduled_time_utc.timestamp())}"
        schedule_once(
            self.application.job_queue,
            name=job_name,
            callback=self._execute_scheduled_broadcast,
            when_dt=scheduled_time_utc,
            data={
                "message": broadcast_message,
                "user_ids": user_ids,
                "admin_id": user_id,
                "scheduled_time": scheduled_time.isoformat()
            }
        )
        
        # Confirm to admin
        confirm_msg = (
            f"✅ **Broadcast Scheduled**\n\n"
            f"📅 Time: `{scheduled_time.strftime('%Y-%m-%d %H:%M')}` ({admin_tz})\n"
            f"👥 Users: {len(user_ids)}\n"
            f"📝 Message preview: {broadcast_message[:50]}{'...' if len(broadcast_message) > 50 else ''}\n\n"
            f"The broadcast will be sent automatically at the scheduled time."
        )
        await update.message.reply_text(confirm_msg, parse_mode='Markdown')
        
        # Clear state
        context.user_data.pop('broadcast_state', None)
        context.user_data.pop('broadcast_message', None)
        context.user_data.pop('broadcast_admin_id', None)
        
        logger.info(
            f"Admin {user_id} scheduled broadcast for {scheduled_time.isoformat()} "
            f"to {len(user_ids)} users"
        )
    
    async def _execute_scheduled_broadcast(self, context: CallbackContext) -> None:
        """Execute a scheduled broadcast."""
        data = context.job.data
        message = data.get("message")
        user_ids = data.get("user_ids", [])
        admin_id = data.get("admin_id")
        scheduled_time = data.get("scheduled_time")
        
        logger.info(f"Executing scheduled broadcast to {len(user_ids)} users (scheduled by admin {admin_id})")
        
        # Send broadcast
        results = await send_broadcast(self.response_service, user_ids, message)
        
        # Log results
        logger.info(
            f"Broadcast completed - Success: {results['success']}, "
            f"Failed: {results['failed']} (scheduled by admin {admin_id})"
        )
        
        # Optionally notify admin
        if admin_id:
            try:
                admin_msg = (
                    f"📢 **Broadcast Completed**\n\n"
                    f"✅ Sent: {results['success']}\n"
                    f"❌ Failed: {results['failed']}\n"
                    f"📅 Scheduled time: {scheduled_time}"
                )
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_msg,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"Could not notify admin {admin_id} of broadcast completion: {str(e)}")
