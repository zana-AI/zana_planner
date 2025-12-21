"""
Voice service for speech-to-text (ASR) and text-to-speech (TTS) using Google Cloud APIs.
"""

import os
from typing import Optional
from io import BytesIO

from llms.llm_env_utils import load_llm_env
from utils.logger import get_logger

logger = get_logger(__name__)

# Load GCP configuration
cfg = load_llm_env()
project_id = cfg.get("GCP_PROJECT_ID")
location = cfg.get("GCP_LOCATION", "us-central1")


class VoiceService:
    """Service for voice transcription and synthesis using Google Cloud APIs."""
    
    def __init__(self):
        self.project_id = project_id
        self.location = location
        
    def transcribe_voice(self, voice_file_path: str, language_code: Optional[str] = None) -> str:
        """
        Transcribe voice file to text using Google Cloud Speech-to-Text API.
        
        Args:
            voice_file_path: Path to the voice audio file (OGG format from Telegram)
            language_code: Optional language code (e.g., "en-US", "fa-IR", "fr-FR")
                          If None, will attempt auto-detection
        
        Returns:
            Transcribed text string
        """
        try:
            from google.cloud import speech
            
            client = speech.SpeechClient()
            
            # Read audio file
            with open(voice_file_path, "rb") as audio_file:
                content = audio_file.read()
            
            # Configure recognition
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
                sample_rate_hertz=48000,  # Telegram voice notes are typically 48kHz
                language_code=language_code or "en-US",  # Default to English if not specified
                alternative_language_codes=["en-US", "fa-IR", "fr-FR"] if not language_code else None,
                enable_automatic_punctuation=True,
            )
            
            audio = speech.RecognitionAudio(content=content)
            
            # Perform transcription
            response = client.recognize(config=config, audio=audio)
            
            # Extract transcribed text
            if response.results:
                transcribed_text = " ".join(
                    result.alternatives[0].transcript 
                    for result in response.results
                )
                logger.debug(f"Transcribed voice: {transcribed_text[:50]}...")
                return transcribed_text
            else:
                logger.warning("No transcription results returned")
                return ""
                
        except ImportError:
            logger.error("google-cloud-speech not available. Install with: pip install google-cloud-speech")
            return ""
        except Exception as e:
            logger.error(f"Voice transcription failed: {str(e)}")
            return ""
    
    def synthesize_speech(self, text: str, language_code: str = "en-US") -> Optional[bytes]:
        """
        Synthesize text to speech using Google Cloud Text-to-Speech API.
        
        Args:
            text: Text to synthesize
            language_code: Language code (e.g., "en-US", "fa-IR", "fr-FR")
        
        Returns:
            Audio bytes in OGG format, or None on failure
        """
        try:
            from google.cloud import texttospeech
            
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
            
            logger.debug(f"Synthesized speech for text: {text[:50]}...")
            return response.audio_content
            
        except ImportError:
            logger.error("google-cloud-texttospeech not available. Install with: pip install google-cloud-texttospeech")
            return None
        except Exception as e:
            logger.error(f"Speech synthesis failed: {str(e)}")
            return None
