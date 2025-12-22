"""
Voice service for speech-to-text (ASR) and text-to-speech (TTS) using Google Cloud APIs.
Supports Eleven Labs TTS, OpenAI TTS, with automatic fallback to Google Cloud TTS.
"""

import os
import re
import html
from typing import Optional, Tuple, List
from dataclasses import dataclass
from io import BytesIO
from dotenv import load_dotenv

from llms.llm_env_utils import load_llm_env
from utils.logger import get_logger

logger = get_logger(__name__)

# Load environment variables
load_dotenv()

# Load GCP configuration
cfg = load_llm_env()
project_id = cfg.get("GCP_PROJECT_ID")
location = cfg.get("GCP_LOCATION", "us-central1")


@dataclass
class TranscriptionResult:
    """Result from voice transcription with metadata."""
    text: str
    confidence: float
    language_code: str
    alternatives: List[Tuple[str, float]]  # List of (text, confidence) tuples


class VoiceService:
    """Service for voice transcription and synthesis using Google Cloud APIs.
    Supports Eleven Labs TTS, OpenAI TTS, with automatic fallback to Google Cloud TTS."""
    
    def __init__(self):
        self.project_id = project_id
        self.location = location
        self.eleven_labs_api_key = os.getenv("ELEVEN_LABS_API_KEY")
        self.openai_api_key = cfg.get("OPENAI_API_KEY", "")
        
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
                
                for result in response.results:
                    if result.alternatives:
                        # Get the best alternative
                        best_alt = result.alternatives[0]
                        all_transcripts.append(best_alt.transcript)
                        confidence = best_alt.confidence if hasattr(best_alt, 'confidence') and best_alt.confidence > 0 else 0.0
                        all_confidences.append(confidence)
                        
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
                    language_code=primary_language or "en-US",
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
        
        # If user language is not English and fallback is enabled, try both
        if user_language != "en" and fallback_to_english:
            # Try user's language first
            result_user_lang = self.transcribe_voice(
                voice_file_path,
                primary_language=primary_lang,
                alternative_languages=["en-US"]
            )
            
            # Try English as primary
            result_english = self.transcribe_voice(
                voice_file_path,
                primary_language="en-US",
                alternative_languages=[primary_lang]
            )
            
            # Compare confidence scores and return the best
            if result_user_lang.confidence >= result_english.confidence:
                logger.info(
                    f"Selected {primary_lang} transcription "
                    f"(confidence: {result_user_lang.confidence:.2f} vs {result_english.confidence:.2f})"
                )
                return result_user_lang
            else:
                logger.info(
                    f"Selected English transcription "
                    f"(confidence: {result_english.confidence:.2f} vs {result_user_lang.confidence:.2f})"
                )
                return result_english
        else:
            # Single language transcription with alternatives
            alternative_langs = ["en-US", "fa-IR", "fr-FR"] if primary_lang == "en-US" else ["en-US"]
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
        # - Older Markdown: "*Zana:*\n`text`\n\n*Log:*\n..."
        # - New HTML: "<b>Zana:</b>\n<pre>text</pre>\n\n<b>Log:</b>\n<blockquote expandable><pre>...</pre></blockquote>"
        # Extract just the main content, removing the structured format
        lines = text.split('\n')
        cleaned_lines = []
        in_zana_section = False
        in_log_section = False
        
        for line in lines:
            line_stripped = line.strip()
            
            # Skip formatting markers
            if re.match(r'^\*?(Zana|Log)\*?:\s*$', line_stripped, re.IGNORECASE):
                if 'Zana' in line_stripped or 'zana' in line_stripped:
                    in_zana_section = True
                    in_log_section = False
                elif 'Log' in line_stripped or 'log' in line_stripped:
                    in_log_section = True
                    in_zana_section = False
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
    
    def _synthesize_with_eleven_labs(self, text: str, language_code: str = "en-US") -> Optional[bytes]:
        """
        Synthesize text to speech using Eleven Labs API.
        
        Args:
            text: Text to synthesize (should already be cleaned)
            language_code: Language code (e.g., "en-US", "fa-IR", "fr-FR")
        
        Returns:
            Audio bytes in MP3 format, or None on failure
        """
        if not self.eleven_labs_api_key:
            return None
        
        try:
            from elevenlabs import generate, set_api_key
            
            # Set API key
            set_api_key(self.eleven_labs_api_key)
            
            # Map language codes to Eleven Labs voices
            # Eleven Labs voice IDs or names (using common voices)
            voice_map = {
                "en": "Rachel",      # English female voice
                "en-US": "Rachel",
                "fa": "Bella",        # Multilingual voice for Farsi
                "fa-IR": "Bella",
                "fr": "Antoni",       # Multilingual voice for French
                "fr-FR": "Antoni",
            }
            
            # Get base language code
            base_lang = language_code.split("-")[0] if "-" in language_code else language_code
            voice_name = voice_map.get(language_code) or voice_map.get(base_lang) or "Rachel"
            
            # Use eleven_v3 (alpha) for Persian/Farsi - supports 70+ languages with better quality
            # For other languages, use eleven_multilingual_v2
            model = "eleven_v3" if base_lang == "fa" else "eleven_multilingual_v2"
            
            # Generate audio using Eleven Labs
            audio = generate(
                text=text,
                voice=voice_name,
                model=model
            )
            
            logger.debug(f"Synthesized speech with Eleven Labs for text: {text[:50]}...")
            return audio
            
        except ImportError:
            logger.warning("elevenlabs package not available. Install with: pip install elevenlabs")
            return None
        except Exception as e:
            error_str = str(e).lower()
            # Check for credit/quota related errors
            if any(keyword in error_str for keyword in ["quota", "credit", "insufficient", "401", "403", "429"]):
                logger.warning(f"Eleven Labs API credit/quota issue: {str(e)}. Falling back to next TTS provider.")
            else:
                logger.warning(f"Eleven Labs synthesis failed: {str(e)}. Falling back to next TTS provider.")
            return None
    
    def _synthesize_with_openai(self, text: str, language_code: str = "en-US") -> Optional[bytes]:
        """
        Synthesize text to speech using OpenAI TTS API.
        
        Args:
            text: Text to synthesize (should already be cleaned)
            language_code: Language code (e.g., "en-US", "fa-IR", "fr-FR")
        
        Returns:
            Audio bytes in MP3 format, or None on failure
        """
        if not self.openai_api_key:
            return None
        
        try:
            from openai import OpenAI
            from io import BytesIO
            
            client = OpenAI(api_key=self.openai_api_key)
            
            # Map language codes to OpenAI voices
            voice_map = {
                "en": "cedar",      # English voice
                "en-US": "cedar",
                "fa": "cedar",      # Multilingual voice for Farsi
                "fa-IR": "cedar",
                "fr": "cedar",      # Multilingual voice for French
                "fr-FR": "cedar",
            }
            
            # Get base language code
            base_lang = language_code.split("-")[0] if "-" in language_code else language_code
            voice_name = voice_map.get(language_code) or voice_map.get(base_lang) or "cedar"
            
            # Language-specific instructions
            instructions_map = {
                "en": "Speak English clearly, natural pace, neutral tone.",
                "en-US": "Speak English clearly, natural pace, neutral tone.",
                "fa": "Speak Persian (Farsi) clearly, natural pace, neutral tone.",
                "fa-IR": "Speak Persian (Farsi) clearly, natural pace, neutral tone.",
                "fr": "Speak French clearly, natural pace, neutral tone.",
                "fr-FR": "Speak French clearly, natural pace, neutral tone.",
            }
            instructions = instructions_map.get(language_code) or instructions_map.get(base_lang) or "Speak clearly, natural pace, neutral tone."
            
            # Generate audio using OpenAI TTS with streaming
            with client.audio.speech.with_streaming_response.create(
                model="gpt-4o-mini-tts",
                voice=voice_name,
                input=text,
                instructions=instructions,
            ) as response:
                # Stream to BytesIO instead of file
                audio_buffer = BytesIO()
                for chunk in response.iter_bytes():
                    audio_buffer.write(chunk)
                audio_buffer.seek(0)
                audio_bytes = audio_buffer.read()
            
            logger.debug(f"Synthesized speech with OpenAI TTS for text: {text[:50]}...")
            return audio_bytes
            
        except ImportError:
            logger.warning("openai package not available. Install with: pip install openai")
            return None
        except Exception as e:
            error_str = str(e).lower()
            # Check for credit/quota related errors
            if any(keyword in error_str for keyword in ["quota", "credit", "insufficient", "401", "403", "429", "rate limit"]):
                logger.warning(f"OpenAI TTS API credit/quota issue: {str(e)}. Falling back to next TTS provider.")
            else:
                logger.warning(f"OpenAI TTS synthesis failed: {str(e)}. Falling back to next TTS provider.")
            return None
    
    def _synthesize_with_google_cloud(self, text: str, language_code: str = "en-US") -> Optional[bytes]:
        """
        Synthesize text to speech using Google Cloud Text-to-Speech API (baseline fallback).
        
        Args:
            text: Text to synthesize (should already be cleaned)
            language_code: Language code (e.g., "en-US", "fa-IR", "fr-FR")
        
        Returns:
            Audio bytes in OGG format, or None on failure
        """
        try:
            from google.cloud import texttospeech
            
            if not text:
                logger.warning("Text is empty, cannot synthesize")
                return None
            
            client = texttospeech.TextToSpeechClient()
            
            # Map language codes to voice names
            voice_map = {
                "en": "en-US-Neural2-F",  # English female neural voice
                "en-US": "en-US-Neural2-F",
                "fa": "fa-IR-Standard-A",  # Farsi female voice
                "fa-IR": "fa-IR-Standard-A",
                "fr": "fr-FR-Neural-A",    # French female neural voice
                "fr-FR": "fr-FR-Neural-A",
            }
            
            # Get base language code (e.g., "en" from "en-US")
            base_lang = language_code.split("-")[0] if "-" in language_code else language_code
            voice_name = voice_map.get(language_code) or voice_map.get(base_lang) or "en-US-Neural2-F"
            
            # Configure synthesis
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(
                language_code=language_code if "-" in language_code else f"{base_lang}-{base_lang.upper()}",
                name=voice_name,
                ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.OGG_OPUS,
            )
            
            # Perform synthesis
            response = client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config,
            )
            
            logger.debug(f"Synthesized speech with Google Cloud for text: {text[:50]}...")
            return response.audio_content
            
        except ImportError:
            logger.error("google-cloud-texttospeech not available. Install with: pip install google-cloud-texttospeech")
            return None
        except Exception as e:
            logger.error(f"Google Cloud speech synthesis failed: {str(e)}")
            return None
    
    def synthesize_speech(self, text: str, language_code: str = "en-US") -> Optional[bytes]:
        """
        Synthesize text to speech using Eleven Labs (if API key available), 
        then OpenAI TTS (if API key available), with fallback to Google Cloud TTS.
        
        Args:
            text: Text to synthesize (will be cleaned of markdown/special chars)
            language_code: Language code (e.g., "en-US", "fa-IR", "fr-FR")
        
        Returns:
            Audio bytes in OGG/MP3 format, or None on failure
        """
        # Clean text before synthesis
        cleaned_text = self.clean_text_for_tts(text)
        
        if not cleaned_text:
            logger.warning("Text is empty after cleaning, cannot synthesize")
            return None
        
        # Try Eleven Labs first if API key is present
        if self.eleven_labs_api_key:
            audio_bytes = self._synthesize_with_eleven_labs(cleaned_text, language_code)
            if audio_bytes:
                return audio_bytes
        
        # Try OpenAI TTS if API key is present
        if self.openai_api_key:
            audio_bytes = self._synthesize_with_openai(cleaned_text, language_code)
            if audio_bytes:
                return audio_bytes
        
        # Fallback to Google Cloud TTS (baseline)
        logger.debug("Using Google Cloud TTS (baseline fallback)")
        return self._synthesize_with_google_cloud(cleaned_text, language_code)
