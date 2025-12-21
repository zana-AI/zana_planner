"""
Message handlers for the Telegram bot.
Handles all command and text message processing.
"""

import os
from datetime import datetime
from typing import Optional

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import CallbackContext

from handlers.messages_store import get_message, get_user_language, Language
from handlers.translator import translate_text
from services.planner_api_adapter import PlannerAPIAdapter
from services.voice_service import VoiceService
from llms.llm_handler import LLMHandler
from utils.time_utils import get_week_range
from ui.messages import weekly_report_text
from ui.keyboards import weekly_report_kb, pomodoro_kb, preping_kb, language_selection_kb, voice_mode_selection_kb
from cbdata import encode_cb
from infra.scheduler import schedule_user_daily
from utils_storage import create_user_directory
from handlers.callback_handlers import CallbackHandlers
from utils.logger import get_logger
from utils.version import get_version_info

logger = get_logger(__name__)


class MessageHandlers:
    """Handles all message and command processing."""
    
    def __init__(self, plan_keeper: PlannerAPIAdapter, llm_handler: LLMHandler, root_dir: str, application):
        self.plan_keeper = plan_keeper
        self.llm_handler = llm_handler
        self.root_dir = root_dir
        self.application = application
        self.voice_service = VoiceService()
    
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
        await update.message.reply_text(
            f"{header}\n\n{report}",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
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
                        photo=photo
                    )
        except Exception as e:
            logger.warning(f"Failed to generate weekly visualization: {e}")
            # Don't fail the whole command if visualization fails
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
            
            if settings.voice_mode is None:
                # First time - ask user preference
                message = get_message("voice_mode_prompt", user_lang)
                keyboard = voice_mode_selection_kb()
                await update.effective_message.reply_text(message, reply_markup=keyboard)
                # Don't process voice until preference is set
                return
            
            # Send acknowledgment
            ack_message = get_message("voice_received", user_lang)
            await update.effective_message.reply_text(ack_message)
            
            # Transcribe voice
            user_lang_code = user_lang.value if user_lang else "en"
            # Map language codes for speech recognition
            speech_lang_map = {
                "en": "en-US",
                "fa": "fa-IR",
                "fr": "fr-FR"
            }
            speech_lang = speech_lang_map.get(user_lang_code, "en-US")
            
            transcribed_text = self.voice_service.transcribe_voice(path, speech_lang)
            
            if not transcribed_text:
                error_msg = get_message("voice_transcription_failed", user_lang)
                await update.effective_message.reply_text(error_msg)
                return
            
            # Process transcribed text as a regular message
            # Create a mock update with the transcribed text
            llm_response = self.llm_handler.get_response_api(transcribed_text, str(user_id), user_language=user_lang_code)
            
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
        if settings.voice_mode == "enabled":
            try:
                # Synthesize speech
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
                import sys
                from pathlib import Path
                # Add parent directory to path to import from demo_features
                parent_dir = Path(__file__).parent.parent.parent
                if str(parent_dir) not in sys.path:
                    sys.path.insert(0, str(parent_dir))
                from demo_features.demo_image_processing import ImageVLMParser
                
                parser = ImageVLMParser()
                # Use Telegram's file_path (URL) if available, otherwise use local path
                # Note: ImageVLMParser expects a URL, so we use Telegram's file_path
                file_url = file.file_path
                
                if not file_url:
                    # If file_path is not available, we need to use the local file
                    # For Gemini, we might need to convert to base64 or use a different approach
                    # For now, try using the local path (may need adjustment based on API)
                    file_url = f"file://{os.path.abspath(path)}"
                
                vlm_output = parser.parse(file_url)
                
                # Extract text from image
                extracted_text = vlm_output.text or vlm_output.caption or ""
                
                if not extracted_text:
                    # No text found in image
                    error_msg = get_message("image_processing_failed", user_lang)
                    await msg.reply_text(error_msg)
                    return
                
                # Use extracted text as user message input
                # Combine caption and text for better context
                user_message = f"{vlm_output.caption}\n\n{extracted_text}".strip()
                
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
                    
            except ImportError:
                error_msg = get_message("image_processing_failed", user_lang)
                logger.error("ImageVLMParser not available")
                await msg.reply_text(error_msg)
            except Exception as e:
                error_msg = get_message("image_processing_failed", user_lang)
                logger.error(f"Image processing error: {str(e)}")
                await msg.reply_text(error_msg)
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

            # Check if user exists, if not, call start
            user_dir = os.path.join(self.root_dir, str(user_id))
            if not os.path.exists(user_dir):
                await self.start(update, context)
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
                await update.message.reply_text(formatted_response, parse_mode='Markdown')
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
    
    async def cmd_language(self, update: Update, context: CallbackContext) -> None:
        """Handle the /language command to change language preference."""
        user_id = update.effective_user.id
        user_lang = get_user_language(user_id)
        
        message = get_message("choose_language", user_lang)
        keyboard = language_selection_kb()
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode='Markdown')

    async def cmd_version(self, update: Update, context: CallbackContext) -> None:
        """Handle the /version command to show bot version."""
        user_id = update.effective_user.id
        user_lang = get_user_language(user_id)
        
        version_info = get_version_info()
        
        version_text = f"**Zana AI Bot Version**\n\n"
        version_text += f"Version: `{version_info['version']}`\n"
        version_text += f"Environment: `{version_info.get('environment', 'unknown')}`\n"
        
        if 'commit' in version_info:
            version_text += f"Commit: `{version_info['commit']}`\n"
        if 'date' in version_info:
            version_text += f"Build Date: `{version_info['date'][:10]}`\n"
        
        await update.message.reply_text(version_text, parse_mode='Markdown')
