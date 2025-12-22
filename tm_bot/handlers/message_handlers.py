"""
Message handlers for the Telegram bot.
Handles all command and text message processing.
"""

import os
import html
from datetime import datetime
from typing import Optional

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import CallbackContext

from handlers.messages_store import get_message, get_user_language, Language
from handlers.translator import translate_text
from services.planner_api_adapter import PlannerAPIAdapter
from services.voice_service import VoiceService
from services.image_service import ImageService
from services.content_service import ContentService
from llms.llm_handler import LLMHandler
from utils.time_utils import get_week_range
from utils.calendar_utils import generate_google_calendar_link, suggest_time_slot
from ui.messages import weekly_report_text
from ui.keyboards import weekly_report_kb, pomodoro_kb, preping_kb, language_selection_kb, voice_mode_selection_kb, content_actions_kb
from cbdata import encode_cb
from infra.scheduler import schedule_user_daily, schedule_once
from utils_storage import create_user_directory
from handlers.callback_handlers import CallbackHandlers
from utils.logger import get_logger
from utils.version import get_version_info
from utils.admin_utils import is_admin
from services.broadcast_service import get_all_users, send_broadcast, parse_broadcast_time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = get_logger(__name__)


class MessageHandlers:
    """Handles all message and command processing."""
    
    def __init__(self, plan_keeper: PlannerAPIAdapter, llm_handler: LLMHandler, root_dir: str, application):
        self.plan_keeper = plan_keeper
        self.llm_handler = llm_handler
        self.root_dir = root_dir
        self.application = application
        self.voice_service = VoiceService()
        self.content_service = ContentService()
        try:
            self.image_service = ImageService()
        except Exception as e:
            logger.error(f"Failed to initialize ImageService: {str(e)}")
            self.image_service = None
    
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
        
        # Check if user has language preference set
        settings = self.plan_keeper.settings_repo.get_settings(user_id)
        if len(existing_promises) == 0 and (not hasattr(settings, 'language') or settings.language == "en"):
            # New user without language preference - show language selection
            message = get_message("choose_language", user_lang)
            keyboard = language_selection_kb()
            await update.message.reply_text(message, reply_markup=keyboard, parse_mode='Markdown')
            return
        
        # Existing user or user with language preference
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
        
        # Create refresh keyboard
        keyboard = weekly_report_kb(report_ref_time)
        
        header = get_message("weekly_header", user_lang, date_range=date_range_str)
        message_text = f"{header}\n\n{report}"

        # Telegram captions have a hard limit (1024 chars). Keep everything in one message by
        # truncating (instead of sending a 2nd message).
        # Ref: https://core.telegram.org/bots/api#sendphoto
        MAX_CAPTION_LEN = 1024
        if len(message_text) > MAX_CAPTION_LEN:
            message_text = message_text[: MAX_CAPTION_LEN - 1] + "…"
        
        # Generate and send visualization image
        image_path = None
        try:
            image_path = self.plan_keeper.reports_service.generate_weekly_visualization_image(
                user_id, report_ref_time
            )
            if image_path and os.path.exists(image_path):
                with open(image_path, 'rb') as photo:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=photo,
                        caption=message_text,
                        reply_markup=keyboard,
                        parse_mode='Markdown',
                    )
            else:
                # Fallback: no image generated, send text-only weekly report
                await update.message.reply_text(
                    message_text,
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.warning(f"Failed to generate weekly visualization: {e}")
            # Don't fail the whole command if visualization fails
            try:
                await update.message.reply_text(
                    message_text,
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
            except Exception:
                await update.message.reply_text(message_text)
        finally:
            # Clean up temp file
            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temp visualization file {image_path}: {e}")
    
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

    async def on_voice(self, update: Update, context: CallbackContext):
        """Handle voice messages with ASR and optional TTS response."""
        user_id = update.effective_user.id
        user_lang = get_user_language(update.effective_user)
        
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
            settings = self.plan_keeper.settings_repo.get_settings(user_id)
            
            # Check if there's a text caption with the voice message
            voice_caption = update.effective_message.caption or ""
            
            # Send acknowledgment
            ack_message = get_message("voice_received", user_lang)
            await update.effective_message.reply_text(ack_message)
            
            # If first time, ask about voice mode preference (but still process the message)
            if settings.voice_mode is None:
                message = get_message("voice_mode_prompt", user_lang)
                keyboard = voice_mode_selection_kb()
                await update.effective_message.reply_text(message, reply_markup=keyboard)
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
                await update.effective_message.reply_text(error_msg)
                return
            
            # Process transcribed text as a regular message
            llm_response = self.llm_handler.get_response_api(user_input, str(user_id), user_language=user_lang_code)
            
            # Check for errors
            if "error" in llm_response:
                error_msg = llm_response["response_to_user"]
                if user_lang and user_lang != Language.EN:
                    error_msg = translate_text(error_msg, user_lang.value, "en")
                await self._send_response_with_voice_mode(
                    update, context, error_msg, settings, user_lang
                )
                return
            
            # Process LLM response
            try:
                func_call_response = self.call_planner_api(user_id, llm_response)
                response_text = llm_response['response_to_user']
                if user_lang and user_lang != Language.EN:
                    response_text = translate_text(response_text, user_lang.value, "en")
                formatted_response = self._format_response(response_text, func_call_response)
                
                # Send response with voice mode if enabled
                await self._send_response_with_voice_mode(
                    update, context, formatted_response, settings, user_lang
                )
            except Exception as e:
                error_msg = get_message("error_general", user_lang, error=str(e))
                logger.error(f"Error processing voice message for user {user_id}: {str(e)}")
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
                    # Send as voice message
                    import tempfile
                    import os
                    temp_dir = tempfile.gettempdir()
                    temp_path = os.path.join(temp_dir, f"tts_{update.effective_message.message_id}.ogg")
                    
                    try:
                        with open(temp_path, 'wb') as f:
                            f.write(audio_bytes)
                        
                        with open(temp_path, 'rb') as voice_file:
                            await update.effective_message.reply_voice(voice=voice_file)
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
        
        # Send as text (voice mode disabled or TTS failed)
        try:
            await update.effective_message.reply_text(text_response, parse_mode='Markdown')
        except Exception:
            await update.effective_message.reply_text(text_response)

    async def on_image(self, update: Update, context: CallbackContext):
        """Handle image messages with VLM parsing and text extraction."""
        user_id = update.effective_user.id
        user_lang = get_user_language(update.effective_user)
        
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
            await msg.reply_text(ack_message)
            
            # Parse image with VLM
            try:
                if self.image_service is None:
                    error_msg = get_message("image_processing_failed", user_lang)
                    await msg.reply_text(f"{error_msg}\n\nImage processing service is not available.")
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
                    await msg.reply_text(error_msg)
                    return
                
                # Log extracted content for debugging
                logger.info(f"Image analysis - Type: {analysis.type}, Text length: {len(analysis.text)}, Language: {analysis.meta.language}")
                
                # Use extracted text as user message input with context
                # This helps the LLM understand it's processing extracted image content
                user_message = f"I've extracted the following content from an image:\n\n{extracted_text}\n\nPlease help me process this content."
                
                # Process through LLM
                user_lang_code = user_lang.value if user_lang else "en"
                llm_response = self.llm_handler.get_response_api(user_message, str(user_id), user_language=user_lang_code)
                
                # Check for errors
                if "error" in llm_response:
                    error_msg = llm_response["response_to_user"]
                    if user_lang and user_lang != Language.EN:
                        error_msg = translate_text(error_msg, user_lang.value, "en")
                    await msg.reply_text(error_msg, parse_mode='Markdown')
                    return
                
                # Process LLM response
                try:
                    func_call_response = self.call_planner_api(user_id, llm_response)
                    response_text = llm_response['response_to_user']
                    if user_lang and user_lang != Language.EN:
                        response_text = translate_text(response_text, user_lang.value, "en")
                    formatted_response = self._format_response(response_text, func_call_response)
                    
                    # Get settings for voice mode
                    settings = self.plan_keeper.settings_repo.get_settings(user_id)
                    
                    # Send response (with voice mode if enabled)
                    await self._send_response_with_voice_mode(
                        update, context, formatted_response, settings, user_lang
                    )
                except Exception as e:
                    error_msg = get_message("error_general", user_lang, error=str(e))
                    logger.error(f"Error processing image for user {user_id}: {str(e)}")
                    await msg.reply_text(error_msg)
                    
            except Exception as e:
                error_msg = get_message("image_processing_failed", user_lang)
                logger.error(f"Image processing error: {str(e)}", exc_info=True)
                # Provide more context in error message
                detailed_error = f"{error_msg}\n\nError details: {str(e)}"
                await msg.reply_text(detailed_error)
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
        await update.effective_message.reply_text(message)

    async def on_poll_answer(self, update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        user_lang = get_user_language(update.effective_user)
        message = get_message("poll_answer_not_implemented", user_lang)
        await update.effective_message.reply_text(message)

    async def on_todo_text(self, update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        user_lang = get_user_language(update.effective_user)
        message = get_message("todo_not_implemented", user_lang)
        await update.effective_message.reply_text(message)

    async def handle_message(self, update: Update, context: CallbackContext) -> None:
        """Handle general text messages."""
        try:
            user_message = update.message.text
            user_id = update.effective_user.id
            user_group_id = update.effective_chat.id if update.effective_chat.type in ['group', 'supergroup'] else None
            user_lang = get_user_language(update.effective_user)

            # Check for broadcast state
            broadcast_state = context.user_data.get('broadcast_state') if context.user_data else None
            if broadcast_state == 'waiting_message':
                await self._handle_broadcast_message(update, context, user_message, user_id, user_lang)
                return
            elif broadcast_state == 'waiting_time':
                await self._handle_broadcast_time(update, context, user_message, user_id, user_lang)
                return

            # Check if user exists, if not, call start
            user_dir = os.path.join(self.root_dir, str(user_id))
            if not os.path.exists(user_dir):
                await self.start(update, context)
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
            llm_response = self.llm_handler.get_response_api(user_message, user_id, user_language=user_lang_code)
            
            # Check for errors in LLM response
            if "error" in llm_response:
                # Translate error message if needed
                error_msg = llm_response["response_to_user"]
                if user_lang and user_lang != Language.EN:
                    error_msg = translate_text(error_msg, user_lang.value, "en")
                await update.message.reply_text(
                    error_msg,
                    parse_mode='Markdown'
                )
                return
            
            # Process the LLM response
            try:
                func_call_response = self.call_planner_api(user_id, llm_response)
                # LLM should already respond in target language, but translate as fallback if needed
                response_text = llm_response['response_to_user']
                if user_lang and user_lang != Language.EN:
                    # Try to detect if already in target language, otherwise translate
                    # For now, always translate to ensure consistency
                    response_text = translate_text(response_text, user_lang.value, "en")
                formatted_response = self._format_response(response_text, func_call_response)
            except ValueError as e:
                formatted_response = get_message("error_invalid_input", user_lang, error=str(e))
                logger.error(f"Validation error for user {user_id}: {str(e)}")
            except Exception as e:
                formatted_response = get_message("error_general", user_lang, error=str(e))
                logger.error(f"Error processing request for user {user_id}: {str(e)}")

            try:
                await update.message.reply_text(formatted_response, parse_mode='HTML')
            except Exception:
                await update.message.reply_text(formatted_response)
        
        except Exception as e:
            user_lang = get_user_language(update.effective_user)
            message = get_message("error_unexpected", user_lang, error=str(e))
            await update.message.reply_text(message, parse_mode='Markdown')
            logger.error(f"Unexpected error handling message from user {update.effective_user.id}: {str(e)}")
    
    def _format_response(self, llm_response: str, func_call_response) -> str:
        """Format the response for Telegram."""
        try:
            if func_call_response is None:
                return llm_response
            elif isinstance(func_call_response, list):
                formatted_response = "• " + "\n• ".join(str(item) for item in func_call_response)
            elif isinstance(func_call_response, dict):
                formatted_response = "\n".join(f"{key}: {value}" for key, value in func_call_response.items())
            else:
                formatted_response = str(func_call_response)
            
            # Use HTML formatting so we can render an expandable blockquote for logs robustly.
            # This avoids Markdown escaping issues and lets Telegram clients collapse/expand the Log section.
            zana_text = html.escape(llm_response or "")
            log_text = html.escape(formatted_response or "")

            full_response = f"<b>Zana:</b>\n{zana_text}\n"
            if formatted_response:
                full_response += f"\n<b>Log:</b>\n<blockquote expandable>{log_text}</blockquote>"
            return full_response
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
        
        version_text = f"**Zana AI Bot Version**\n\n"
        version_text += f"Version: `{version_info['version']}`\n"
        version_text += f"Environment: `{version_info.get('environment', 'unknown')}`\n"
        
        # Show last update date
        if 'last_update' in version_info and version_info['last_update'] != "unknown":
            version_text += f"Last Update: `{version_info['last_update']}`\n"
        
        if 'commit' in version_info:
            version_text += f"Commit: `{version_info['commit']}`\n"
        
        await update.message.reply_text(version_text, parse_mode='Markdown')
    
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
        results = await send_broadcast(context.bot, user_ids, message)
        
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
