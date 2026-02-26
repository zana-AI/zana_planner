"""
Unified response service for all Telegram bot communications.
Handles translation, logging, formatting, and error handling.
"""

import re
from typing import Optional, Dict, Any
from datetime import datetime

from telegram import Update, Message, InlineKeyboardMarkup, InputFile, MessageEntity
from telegram.ext import CallbackContext
from telegram.error import TelegramError

from handlers.messages_store import get_user_language, Language
from handlers.translator import translate_text
from repositories.conversation_repo import ConversationRepository
from utils.logger import get_logger
from utils.formatting import prepend_xaana_to_message

logger = get_logger(__name__)

# Promise count threshold for context injection
PROMISE_COUNT_THRESHOLD = 50
# Telegram hard limit is 4096 chars for text; keep margin for formatting/safety.
MAX_TELEGRAM_TEXT_CHARS = 3900


class ResponseService:
    """Centralized service for all bot responses with translation and logging."""
    
    def __init__(self, settings_repo=None, llm_handler=None) -> None:
        self.settings_repo = settings_repo
        self.conversation_repo = ConversationRepository()
        # Cache for user language (to avoid repeated DB calls)
        self._lang_cache: Dict[int, Language] = {}
        # Optional LLM handler for translation review
        self.llm_handler = llm_handler
    
    def _get_user_language_cached(self, user_id: int) -> Language:
        """Get user language with caching."""
        if user_id not in self._lang_cache:
            if self.settings_repo:
                try:
                    settings = self.settings_repo.get_settings(user_id)
                    # Convert string to Language enum
                    for lang in Language:
                        if lang.value == settings.language:
                            self._lang_cache[user_id] = lang
                            return lang
                except Exception:
                    pass
            self._lang_cache[user_id] = Language.EN
        return self._lang_cache[user_id]
    
    def clear_lang_cache(self, user_id: Optional[int] = None) -> None:
        """Clear language cache (useful when user changes language)."""
        if user_id:
            self._lang_cache.pop(user_id, None)
        else:
            self._lang_cache.clear()
    
    def set_llm_handler(self, llm_handler) -> None:
        """Set the LLM handler for translation review (can be called after initialization)."""
        self.llm_handler = llm_handler
    
    def _should_translate(self, text: str, user_lang: Language) -> bool:
        """Simple check: translate if user language is not English."""
        if user_lang == Language.EN:
            return False
        if not text or len(text.strip()) < 3:
            return False
        return True
    
    def _translate_if_needed(self, text: str, user_lang: Language, user_id: Optional[int] = None) -> str:
        """Translate text if needed, preserving promise IDs and technical terms."""
        if not self._should_translate(text, user_lang):
            return text
        original_text = text

        # If there is an HTML log block appended (from format_response_html),
        # keep it out of the translation step so logs stay in the original language.
        log_suffix = ""
        try:
            log_match = re.search(
                r'(\n\s*<b>Log:</b>\s*\n<blockquote expandable>.*</blockquote>\s*)$',
                text,
                flags=re.DOTALL | re.IGNORECASE,
            )
        except re.error:
            log_match = None

        if log_match:
            log_suffix = log_match.group(1)
            text = text[: log_match.start(1)]

        # Extract and preserve promise IDs and technical terms
        # Pattern: P01, P02, T01, T02, etc. or in brackets [P01: text]
        placeholders = {}
        placeholder_counter = 0
        
        # Find patterns in brackets like [P01: text] first (longer matches)
        bracket_pattern = r'\[([PT]\d+):[^\]]+\]'
        bracket_matches = list(re.finditer(bracket_pattern, text))
        for match in reversed(bracket_matches):
            placeholder = f"__PLACEHOLDER_{placeholder_counter}__"
            placeholders[placeholder] = match.group(0)
            text = text[:match.start()] + placeholder + text[match.end():]
            placeholder_counter += 1
        
        # Find standalone promise IDs (P\d+, T\d+)
        promise_id_pattern = r'\b([PT]\d+)\b'
        matches = list(re.finditer(promise_id_pattern, text))
        # Process in reverse to maintain positions
        for match in reversed(matches):
            placeholder = f"__PLACEHOLDER_{placeholder_counter}__"
            placeholders[placeholder] = match.group(1)
            text = text[:match.start()] + placeholder + text[match.end():]
            placeholder_counter += 1
        
        try:
            user_lang_code = user_lang.value if user_lang else "en"
            translated = translate_text(text, user_lang_code, "en")
            
            # Restore preserved patterns
            for placeholder, original in placeholders.items():
                translated = translated.replace(placeholder, original)

            # Never leak internal placeholders to users; prefer original text if unresolved.
            if re.search(r"__PLACEHOLDER_\d+__", translated or ""):
                logger.warning(
                    "Unresolved translation placeholder for user %s; falling back to original text",
                    user_id,
                )
                return original_text
            
            # Review translation for errors (e.g., proper noun mistranslations)
            if self.llm_handler:
                translated = self._review_translation(text, translated, user_lang, user_id)

            # Re-attach any log suffix without translating it.
            if log_suffix:
                # Preserve spacing between main text and log block.
                return f"{translated.rstrip()}{log_suffix}"
            return translated
        except Exception as e:
            logger.warning(f"Translation failed for user {user_id}: {e}")
            return original_text  # Fallback to original (without placeholders)
    
    def _review_translation(self, original_text: str, translated_text: str, user_lang: Language, user_id: Optional[int] = None) -> str:
        """
        Review translated text using LLM to catch errors like proper noun mistranslations.
        
        Args:
            original_text: Original English text
            translated_text: Translated text that may contain errors
            user_lang: Target language
            user_id: Optional user ID for logging
            
        Returns:
            Corrected translation if errors found, otherwise original translated text
        """
        if not self.llm_handler or not self.llm_handler.chat_model:
            return translated_text
        
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            
            review_prompt = (
                "You are reviewing a translation for errors. The original English text was translated to another language, "
                "but the translation may have incorrectly translated proper nouns (names, places, etc.).\n\n"
                f"Original English text: {original_text}\n"
                f"Translated text: {translated_text}\n\n"
                "Your task:\n"
                "1. Identify any proper nouns (names, places, brands, etc.) in the original text\n"
                "2. Check if they were incorrectly translated in the translated text\n"
                "3. If errors are found, provide a corrected version of the translated text with proper nouns restored\n"
                "4. If no errors are found, return the translated text as-is\n\n"
                "Return ONLY the corrected translation text, nothing else. Do not include explanations or markdown."
            )
            
            messages = [
                SystemMessage(content="You are a translation quality reviewer. Review translations and fix proper noun errors."),
                HumanMessage(content=review_prompt)
            ]
            
            result = self.llm_handler.chat_model.invoke(messages)
            reviewed_text = getattr(result, "content", translated_text).strip()
            
            # If the review returned something reasonable, use it; otherwise fall back to original translation
            if reviewed_text and len(reviewed_text) > 0 and len(reviewed_text) <= len(translated_text) * 2:
                logger.debug(f"Translation reviewed for user {user_id}, corrections applied if any")
                return reviewed_text
            else:
                logger.debug(f"Translation review returned unexpected result, using original translation")
                return translated_text
                
        except Exception as e:
            logger.warning(f"Translation review failed for user {user_id}: {e}")
            return translated_text  # Fallback to original translation
    
    def _detect_parse_mode(self, text: str) -> Optional[str]:
        """Detect parse mode from text content."""
        if not text:
            return None
        
        # Check for HTML markers
        if "<b>" in text or "<i>" in text or "<blockquote" in text or "<pre>" in text or "<code>" in text:
            return "HTML"
        
        # Check for Markdown markers
        if "**" in text or "__" in text or "`" in text or "[" in text:
            return "Markdown"

        return None

    @staticmethod
    def _normalize_non_html_entities(text: str, parse_mode: Optional[str] = None) -> str:
        """
        Decode common quote entities for non-HTML output.

        This fixes visible artifacts like '&#x27;' in plain/Markdown messages
        without changing HTML-sanitized payloads.
        """
        safe_text = "" if text is None else str(text)
        if not safe_text:
            return safe_text
        if str(parse_mode or "").strip().upper() == "HTML":
            return safe_text

        normalized = safe_text
        normalized = re.sub(r"(?i)&#x0*27;", "'", normalized)
        normalized = normalized.replace("&#39;", "'").replace("&apos;", "'")
        normalized = re.sub(r"(?i)&#x0*22;", '"', normalized)
        normalized = normalized.replace("&#34;", '"').replace("&quot;", '"')
        return normalized

    def _fit_for_telegram(self, text: str, parse_mode: Optional[str]) -> tuple[str, Optional[str]]:
        """
        Ensure text is safe for Telegram edit/send limits.

        If truncated, disable parse mode to avoid broken HTML/Markdown tags at cut point.
        """
        safe_text = "" if text is None else str(text)
        if len(safe_text) <= MAX_TELEGRAM_TEXT_CHARS:
            return safe_text, parse_mode
        clipped = safe_text[: MAX_TELEGRAM_TEXT_CHARS - 1] + "…"
        logger.warning(
            "Truncated outgoing Telegram text from %s to %s chars",
            len(safe_text),
            len(clipped),
        )
        return clipped, None
    
    def log_user_message(
        self,
        user_id: int,
        content: str,
        message_id: Optional[int] = None,
        chat_id: Optional[int] = None,
    ) -> None:
        """Log a user message (called from message handlers)."""
        self.conversation_repo.save_message(
            user_id=user_id,
            message_type='user',
            content=content,
            message_id=message_id,
            chat_id=chat_id,
        )
    
    async def reply_text(
        self,
        update: Update,
        text: str,
        user_id: Optional[int] = None,
        user_lang: Optional[Language] = None,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        disable_web_page_preview: Optional[bool] = None,
        log_conversation: bool = True,
        auto_translate: bool = True,
    ) -> Optional[Message]:
        """
        Unified reply_text with translation and logging.
        
        Args:
            update: Telegram Update object
            text: Message text
            user_id: User ID (if not provided, extracted from update)
            user_lang: User language (if not provided, fetched from settings)
            parse_mode: Override parse mode detection
            reply_markup: Inline keyboard
            disable_web_page_preview: Disable link previews
            log_conversation: Whether to log this message
            auto_translate: Whether to auto-translate if needed
        """
        # Extract user_id if not provided
        if user_id is None:
            user_id = update.effective_user.id if update.effective_user else None
        
        if user_id is None:
            logger.error("Cannot reply: user_id is None")
            return None
        
        # Get user language if not provided
        if user_lang is None:
            user_lang = self._get_user_language_cached(user_id)
        
        # Translate if needed
        if auto_translate:
            text = self._translate_if_needed(text, user_lang, user_id)
        text = self._normalize_non_html_entities(text, parse_mode=parse_mode)

        # Prepend Xaana header after translation so it is never translated.
        text = prepend_xaana_to_message(text)

        # Detect parse mode if not provided
        if parse_mode is None:
            parse_mode = self._detect_parse_mode(text)
        text, parse_mode = self._fit_for_telegram(text, parse_mode)
        
        # Log conversation
        if log_conversation:
            self.conversation_repo.save_message(
                user_id=user_id,
                message_type='bot',
                content=text,
                message_id=None,  # Will be updated after sending
                chat_id=update.effective_chat.id if update.effective_chat else None,
            )
        
        # Send message with error handling
        try:
            message = await update.message.reply_text(
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
            )
            
            # Update conversation log with actual message_id
            if log_conversation and message:
                self.conversation_repo.update_message_id(user_id, message.message_id)
            
            return message
            
        except TelegramError as e:
            logger.error(f"Telegram API error sending message to user {user_id}: {e}")
            # Try fallback without parse_mode
            try:
                message = await update.message.reply_text(
                    text=text,
                    reply_markup=reply_markup,
                )
                if log_conversation and message:
                    self.conversation_repo.update_message_id(user_id, message.message_id)
                return message
            except Exception as e2:
                logger.error(f"Fallback send also failed: {e2}")
                return None
    
    async def send_message(
        self,
        context: CallbackContext,
        chat_id: int,
        text: str,
        user_id: Optional[int] = None,
        user_lang: Optional[Language] = None,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        log_conversation: bool = True,
        auto_translate: bool = True,
    ) -> Optional[Message]:
        """Unified send_message with translation and logging."""
        if user_id is None:
            logger.error("Cannot send message: user_id is None")
            return None
        
        # Get user language if not provided
        if user_lang is None:
            user_lang = self._get_user_language_cached(user_id)
        
        # Translate if needed
        if auto_translate:
            text = self._translate_if_needed(text, user_lang, user_id)
        text = self._normalize_non_html_entities(text, parse_mode=parse_mode)

        # Prepend Xaana header after translation so it is never translated.
        text = prepend_xaana_to_message(text)

        # Detect parse mode if not provided
        if parse_mode is None:
            parse_mode = self._detect_parse_mode(text)
        text, parse_mode = self._fit_for_telegram(text, parse_mode)
        
        # Log conversation
        if log_conversation:
            self.conversation_repo.save_message(
                user_id=user_id,
                message_type='bot',
                content=text,
                message_id=None,  # Will be updated after sending
                chat_id=chat_id,
            )
        
        # Send message with error handling
        try:
            message = await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            
            # Update conversation log with actual message_id
            if log_conversation and message:
                self.conversation_repo.update_message_id(user_id, message.message_id)
            
            return message
            
        except TelegramError as e:
            logger.error(f"Telegram API error sending message to user {user_id}: {e}")
            # Try fallback without parse_mode
            try:
                message = await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                )
                if log_conversation and message:
                    self.conversation_repo.update_message_id(user_id, message.message_id)
                return message
            except Exception as e2:
                logger.error(f"Fallback send also failed: {e2}")
                return None
    
    async def send_photo(
        self,
        context: CallbackContext,
        chat_id: int,
        photo: Any,  # File path, file_id, or InputFile
        caption: Optional[str] = None,
        user_id: Optional[int] = None,
        user_lang: Optional[Language] = None,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        log_conversation: bool = True,
        auto_translate: bool = True,
    ) -> Optional[Message]:
        """Unified send_photo with translation and logging."""
        if user_id is None:
            logger.error("Cannot send photo: user_id is None")
            return None
        
        # Translate caption if provided
        if caption and auto_translate:
            if user_lang is None:
                user_lang = self._get_user_language_cached(user_id)
            caption = self._translate_if_needed(caption, user_lang, user_id)
        
        # Detect parse mode if not provided
        if parse_mode is None and caption:
            parse_mode = self._detect_parse_mode(caption)
        
        # Log conversation (caption only, or note about photo)
        if log_conversation:
            content = caption or "[Photo sent]"
            self.conversation_repo.save_message(
                user_id=user_id,
                message_type='bot',
                content=content,
                message_id=None,  # Will be updated after sending
                chat_id=chat_id,
            )
        
        # Send photo
        try:
            message = await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            
            # Update conversation log with actual message_id
            if log_conversation and message:
                self.conversation_repo.update_message_id(user_id, message.message_id)
            
            return message
            
        except TelegramError as e:
            logger.error(f"Telegram API error sending photo to user {user_id}: {e}")
            return None
    
    async def reply_voice(
        self,
        update: Update,
        voice: Any,
        user_id: Optional[int] = None,
        user_lang: Optional[Language] = None,
        log_conversation: bool = True,
    ) -> Optional[Message]:
        """Unified reply_voice with logging."""
        # Extract user_id if not provided
        if user_id is None:
            user_id = update.effective_user.id if update.effective_user else None
        
        if user_id is None:
            logger.error("Cannot reply voice: user_id is None")
            return None
        
        # Log as "[Voice message sent]"
        if log_conversation:
            self.conversation_repo.save_message(
                user_id=user_id,
                message_type='bot',
                content="[Voice message sent]",
                message_id=None,  # Will be updated after sending
                chat_id=update.effective_chat.id if update.effective_chat else None,
            )
        
        try:
            message = await update.message.reply_voice(voice=voice)
            
            # Update conversation log with actual message_id
            if log_conversation and message:
                self.conversation_repo.update_message_id(user_id, message.message_id)
            
            return message
        except TelegramError as e:
            logger.error(f"Telegram API error sending voice to user {user_id}: {e}")
            return None
    
    async def edit_message_text(
        self,
        query,  # CallbackQuery
        text: str,
        user_id: Optional[int] = None,
        user_lang: Optional[Language] = None,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        log_conversation: bool = True,
        auto_translate: bool = True,
    ) -> Optional[Message]:
        """Unified edit_message_text with translation and logging."""
        # Extract user_id if not provided
        if user_id is None:
            user_id = query.from_user.id if query.from_user else None
        
        if user_id is None:
            logger.error("Cannot edit message: user_id is None")
            return None
        
        # Get user language if not provided
        if user_lang is None:
            user_lang = self._get_user_language_cached(user_id)
        
        # Translate if needed
        if auto_translate:
            text = self._translate_if_needed(text, user_lang, user_id)
        text = self._normalize_non_html_entities(text, parse_mode=parse_mode)

        # Prepend Xaana header after translation so it is never translated.
        text = prepend_xaana_to_message(text)

        # Detect parse mode if not provided
        if parse_mode is None:
            parse_mode = self._detect_parse_mode(text)
        text, parse_mode = self._fit_for_telegram(text, parse_mode)
        
        # Log conversation (edits are logged as new bot messages)
        if log_conversation:
            self.conversation_repo.save_message(
                user_id=user_id,
                message_type='bot',
                content=f"[Edited] {text}",
                message_id=query.message.message_id if query.message else None,
                chat_id=query.message.chat.id if query.message else None,
            )
        
        # Edit message with error handling
        try:
            return await query.edit_message_text(
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
        except TelegramError as e:
            logger.warning(f"Telegram API error editing message for user {user_id}: {e}")
            return None
    
    async def edit_message_reply_markup(
        self,
        query,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        log_conversation: bool = False,  # Usually just UI updates
    ) -> Optional[Message]:
        """Unified edit_message_reply_markup."""
        # Usually doesn't need translation or logging (just UI state changes)
        try:
            return await query.edit_message_reply_markup(reply_markup=reply_markup)
        except TelegramError as e:
            logger.debug(f"Failed to edit message markup: {e}")
            return None
    
    async def delete_message(
        self,
        context: CallbackContext,
        chat_id: int,
        message_id: int,
        log_conversation: bool = False,  # Usually cleanup, not user-facing
    ) -> bool:
        """Unified delete_message with optional logging."""
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            return True
        except TelegramError as e:
            logger.debug(f"Failed to delete message {message_id}: {e}")
            return False
    
    async def send_processing_message(
        self,
        update: Update,
        user_id: Optional[int] = None,
        user_lang: Optional[Language] = None,
    ) -> Optional[Message]:
        """
        Send a quick 'processing...' message that will be edited later.
        Returns the message object for later editing.
        """
        if user_id is None:
            user_id = update.effective_user.id if update.effective_user else None
        
        if user_id is None:
            logger.error("Cannot send processing message: user_id is None")
            return None
        
        # Get user language if not provided
        if user_lang is None:
            user_lang = self._get_user_language_cached(user_id)
        
        # Processing message - keep it simple, don't translate
        # Use custom emoji (hourglass) for "waiting" - entity covers first character (UTF-16)
        processing_text = "⏳ Processing..."
        processing_entities = [
            MessageEntity(
                type=MessageEntity.CUSTOM_EMOJI,
                offset=0,
                length=1,
                custom_emoji_id="5217697679030637222",
            )
        ]
        try:
            message = await update.message.reply_text(
                processing_text,
                entities=processing_entities,
            )
            # Don't log processing messages to conversation history
            return message
        except TelegramError as e:
            logger.error(f"Telegram API error sending processing message to user {user_id}: {e}")
            return None
    
    async def edit_processing_message(
        self,
        context: CallbackContext,
        message: Message,
        final_text: str,
        user_id: Optional[int] = None,
        user_lang: Optional[Language] = None,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        log_conversation: bool = True,
        auto_translate: bool = True,
    ) -> Optional[Message]:
        """
        Edit a processing message with the final response.
        Handles translation and logging.
        """
        if user_id is None:
            logger.error("Cannot edit processing message: user_id is None")
            return None
        
        # Get user language if not provided
        if user_lang is None:
            user_lang = self._get_user_language_cached(user_id)
        
        # Translate if needed
        if auto_translate:
            final_text = self._translate_if_needed(final_text, user_lang, user_id)
        final_text = self._normalize_non_html_entities(final_text, parse_mode=parse_mode)

        # Prepend Xaana header after translation so it is never translated.
        final_text = prepend_xaana_to_message(final_text)

        # Detect parse mode if not provided
        if parse_mode is None:
            parse_mode = self._detect_parse_mode(final_text)
        final_text, parse_mode = self._fit_for_telegram(final_text, parse_mode)
        
        # Log conversation
        if log_conversation:
            self.conversation_repo.save_message(
                user_id=user_id,
                message_type='bot',
                content=final_text,
                message_id=message.message_id,
                chat_id=message.chat.id,
            )
        
        # Edit message
        try:
            edited = await context.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=message.message_id,
                text=final_text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            return edited
        except TelegramError as e:
            logger.warning(f"Failed to edit processing message for user {user_id}: {e}")
            # Fallback: try without parse_mode
            try:
                return await context.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    text=final_text,
                    reply_markup=reply_markup,
                )
            except Exception as e2:
                logger.error(f"Fallback edit also failed: {e2}")
                return None
