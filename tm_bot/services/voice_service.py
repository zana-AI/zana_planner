"""
Voice service for speech-to-text (ASR) and text-to-speech (TTS).

ASR uses Google Cloud Speech-to-Text.
TTS uses a dedicated Google Cloud implementation (Gemini/classic fallback)
that returns Telegram-compatible voice-note audio.
"""

import re
import html
from typing import Optional, Tuple, List
from dataclasses import dataclass
from dotenv import load_dotenv

from llms.llm_env_utils import load_llm_env
from services.gcp_tts_service import GcpTtsService
from utils.logger import get_logger

logger = get_logger(__name__)

# Load environment variables
load_dotenv()


@dataclass
class TranscriptionResult:
    """Result from voice transcription with metadata."""
    text: str
    confidence: float
    language_code: str
    alternatives: List[Tuple[str, float]]  # List of (text, confidence) tuples


class VoiceService:
    """Service for voice transcription and synthesis using Google Cloud APIs."""
    
    def __init__(self):
        self.project_id = None
        self.location = "us-central1"
        try:
            cfg = load_llm_env()
            self.project_id = cfg.get("GCP_PROJECT_ID")
            self.location = cfg.get("GCP_LOCATION", "us-central1")
        except Exception as e:
            logger.warning("VoiceService env bootstrap failed, using existing env: %s", e)
        self.gcp_tts_service = GcpTtsService()
        
    def transcribe_voice(
        self, 
        voice_file_path: str, 
        primary_language: Optional[str] = None,
        alternative_languages: Optional[List[str]] = None
    ) -> TranscriptionResult:
        """
        Transcribe voice file to text using Google Cloud Speech-to-Text API.
        
        Args:
            voice_file_path: Path to the voice audio file (OGG format from Telegram)
            primary_language: Primary language code (e.g., "en-US", "fa-IR", "fr-FR")
            alternative_languages: List of alternative language codes to try
        
        Returns:
            TranscriptionResult with text, confidence, and metadata
        """
        try:
            from google.cloud import speech
            
            client = speech.SpeechClient()
            
            # Read audio file
            with open(voice_file_path, "rb") as audio_file:
                content = audio_file.read()
            
            # Configure recognition
            # Note: Confidence scores are available by default in the API response
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
                sample_rate_hertz=48000,  # Telegram voice notes are typically 48kHz
                language_code=primary_language or "en-US",
                alternative_language_codes=alternative_languages or [],
                enable_automatic_punctuation=True,
            )
            
            audio = speech.RecognitionAudio(content=content)
            
            # Perform transcription
            response = client.recognize(config=config, audio=audio)
            
            # Extract transcribed text with confidence scores
            if response.results:
                all_transcripts = []
                all_confidences = []
                alternatives_list = []
                detected_language = primary_language or "en-US"
                
                for result in response.results:
                    if result.alternatives:
                        # Get the best alternative
                        best_alt = result.alternatives[0]
                        all_transcripts.append(best_alt.transcript)
                        confidence = best_alt.confidence if hasattr(best_alt, 'confidence') and best_alt.confidence > 0 else 0.0
                        all_confidences.append(confidence)

                        # Prefer detected language when available (for multi-language recognition)
                        if hasattr(result, "language_code") and result.language_code:
                            detected_language = result.language_code
                        elif hasattr(best_alt, "language_code") and best_alt.language_code:
                            detected_language = best_alt.language_code
                        
                        # Collect all alternatives for this result
                        for alt in result.alternatives:
                            alt_confidence = alt.confidence if hasattr(alt, 'confidence') and alt.confidence > 0 else 0.0
                            alternatives_list.append((alt.transcript, alt_confidence))
                
                # Combine all transcripts
                transcribed_text = " ".join(all_transcripts)
                # Average confidence across all results
                avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
                
                logger.debug(f"Transcribed voice: {transcribed_text[:50]}... (confidence: {avg_confidence:.2f})")
                
                return TranscriptionResult(
                    text=transcribed_text,
                    confidence=avg_confidence,
                    language_code=detected_language,
                    alternatives=alternatives_list
                )
            else:
                logger.warning("No transcription results returned")
                return TranscriptionResult(
                    text="",
                    confidence=0.0,
                    language_code=primary_language or "en-US",
                    alternatives=[]
                )
                
        except ImportError:
            logger.error("google-cloud-speech not available. Install with: pip install google-cloud-speech")
            return TranscriptionResult(text="", confidence=0.0, language_code="en-US", alternatives=[])
        except Exception as e:
            logger.error(f"Voice transcription failed: {str(e)}")
            return TranscriptionResult(text="", confidence=0.0, language_code="en-US", alternatives=[])
    
    def transcribe_voice_multi_language(
        self,
        voice_file_path: str,
        user_language: str,
        fallback_to_english: bool = True
    ) -> TranscriptionResult:
        """
        Transcribe voice with multi-language support, trying user language and English.
        Returns the transcription with highest confidence.
        
        Args:
            voice_file_path: Path to the voice audio file
            user_language: User's preferred language code (e.g., "en", "fa", "fr")
            fallback_to_english: If True, always try English as well
        
        Returns:
            TranscriptionResult with the best transcription
        """
        # Map language codes
        lang_map = {
            "en": "en-US",
            "fa": "fa-IR",
            "fr": "fr-FR"
        }
        
        primary_lang = lang_map.get(user_language, "en-US")
        user_language_base = user_language.split("-")[0] if "-" in user_language else user_language
        common_alternatives = ["en-US", "fa-IR", "fr-FR"]
        
        # If user language is not English and fallback is enabled, try both
        if user_language_base != "en" and fallback_to_english:
            # Try user's language first with broader alternatives
            user_alternatives = [lang for lang in common_alternatives if lang != primary_lang]
            result_user_lang = self.transcribe_voice(
                voice_file_path,
                primary_language=primary_lang,
                alternative_languages=user_alternatives
            )
            
            # Try English as primary with user's language as an alternative
            english_alternatives = [lang for lang in common_alternatives if lang != "en-US"]
            if primary_lang not in english_alternatives:
                english_alternatives.insert(0, primary_lang)
            result_english = self.transcribe_voice(
                voice_file_path,
                primary_language="en-US",
                alternative_languages=english_alternatives
            )

            def _base_lang(code: str) -> str:
                return code.split("-")[0] if code else ""

            user_detected_base = _base_lang(result_user_lang.language_code)
            english_detected_base = _base_lang(result_english.language_code)

            # Prefer non-English detections when English is likely a fallback mismatch.
            confidence_margin = 0.15
            if user_detected_base and user_detected_base != "en" and english_detected_base == "en":
                if result_user_lang.confidence >= result_english.confidence - confidence_margin:
                    logger.info(
                        f"Selected {result_user_lang.language_code} transcription "
                        f"(confidence: {result_user_lang.confidence:.2f} vs {result_english.confidence:.2f})"
                    )
                    return result_user_lang

            # Prefer the user's language when close in confidence.
            if user_detected_base == user_language_base:
                if result_user_lang.confidence >= result_english.confidence - confidence_margin:
                    logger.info(
                        f"Selected {result_user_lang.language_code} transcription "
                        f"(confidence: {result_user_lang.confidence:.2f} vs {result_english.confidence:.2f})"
                    )
                    return result_user_lang

            # Compare confidence scores and return the best
            if result_user_lang.confidence >= result_english.confidence:
                logger.info(
                    f"Selected {result_user_lang.language_code} transcription "
                    f"(confidence: {result_user_lang.confidence:.2f} vs {result_english.confidence:.2f})"
                )
                return result_user_lang
            else:
                logger.info(
                    f"Selected {result_english.language_code} transcription "
                    f"(confidence: {result_english.confidence:.2f} vs {result_user_lang.confidence:.2f})"
                )
                return result_english
        else:
            # Single language transcription with alternatives
            alternative_langs = common_alternatives if primary_lang == "en-US" else [lang for lang in common_alternatives if lang != primary_lang]
            return self.transcribe_voice(
                voice_file_path,
                primary_language=primary_lang,
                alternative_languages=alternative_langs
            )
    
    @staticmethod
    def clean_text_for_tts(text: str) -> str:
        """
        Clean text for TTS by removing markdown, special characters, and formatting.
        
        Args:
            text: Raw text that may contain markdown or special characters
        
        Returns:
            Cleaned text suitable for TTS
        """
        if not text:
            return ""

        # If text is HTML-formatted (e.g. <blockquote expandable>...</blockquote>), strip tags first.
        # We replace tags with newlines to keep some structure for the TTS output.
        if "<" in text and ">" in text:
            text = re.sub(r"<[^>]+>", "\n", text)
            text = html.unescape(text)
        
        # Remove markdown formatting
        # Remove bold/italic: **text**, *text*, __text__, _text_
        text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^\*]+)\*', r'\1', text)
        text = re.sub(r'__([^_]+)__', r'\1', text)
        text = re.sub(r'_([^_]+)_', r'\1', text)
        
        # Remove code blocks: `code`, ```code```
        text = re.sub(r'```[^`]*```', '', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        
        # Remove markdown links: [text](url)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # Remove headers: # Header, ## Header, etc.
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
        
        # Remove bullet points and list markers
        text = re.sub(r'^[\*\-\+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
        
        # Remove special characters that TTS might pronounce
        # Keep basic punctuation but remove symbols
        text = re.sub(r'[^\w\s\.\,\!\?\:\;\'\"\-\n]', ' ', text)
        
        # Clean up multiple spaces
        text = re.sub(r'\s+', ' ', text)
        
        # Handle the specific format from MessageHandlers._format_response:
        # - Older Markdown: "*Xaana:*\n`text`\n\n*Log:*\n..."
        # - New HTML: "<b>Xaana:</b>\n<pre>text</pre>\n\n<b>Log:</b>\n<blockquote expandable><pre>...</pre></blockquote>"
        # Extract just the main content, removing the structured format
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # Skip formatting markers
            if re.match(r'^\*?(Zana|Log)\*?:\s*$', line_stripped, re.IGNORECASE):
                continue
            
            # Extract content from backtick-wrapped text
            if line_stripped.startswith('`') and line_stripped.endswith('`'):
                content = line_stripped.strip('`').strip()
                if content:  # Only add non-empty content
                    cleaned_lines.append(content)
            elif line_stripped:  # Add non-empty lines
                cleaned_lines.append(line)
        
        text = '\n'.join(cleaned_lines)
        
        # Remove "Log:" or "Zana:" prefixes that might remain
        text = re.sub(r'^(Log|Zana):\s*', '', text, flags=re.IGNORECASE | re.MULTILINE)
        
        # Clean up leading/trailing whitespace
        text = text.strip()
        
        return text
    
    def synthesize_speech(self, text: str, language_code: str = "en-US") -> Optional[bytes]:
        """
        Synthesize text to speech for Telegram voice notes.

        Primary implementation uses Google Cloud TTS (Gemini model when available),
        with fallback to classic Google Cloud voices.
        
        Args:
            text: Text to synthesize (will be cleaned of markdown/special chars)
            language_code: Language code (e.g., "en-US", "fa-IR", "fr-FR")
        
        Returns:
            Audio bytes in OGG_OPUS format, or None on failure
        """
        # Clean text before synthesis
        cleaned_text = self.clean_text_for_tts(text)
        
        if not cleaned_text:
            logger.warning("Text is empty after cleaning, cannot synthesize")
            return None

        return self.gcp_tts_service.synthesize_voice_note(cleaned_text, language_code)
