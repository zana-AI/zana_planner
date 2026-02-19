"""
Google Cloud TTS service used by voice mode responses.

Primary path:
- Google TTS with Gemini model (when supported by installed client)

Fallback path:
- Classic Google Cloud TTS voices

Output is OGG_OPUS so Telegram can deliver it as a voice note.
"""

from __future__ import annotations

import os
from typing import Optional

from llms.llm_env_utils import load_llm_env
from utils.logger import get_logger

logger = get_logger(__name__)


class GcpTtsService:
    """Generate Telegram-friendly voice-note bytes with Google Cloud TTS."""

    def __init__(self) -> None:
        # Ensures GOOGLE_APPLICATION_CREDENTIALS is configured when using
        # base64 credentials env pattern in this codebase.
        try:
            load_llm_env()
        except Exception as e:
            logger.warning("GCP TTS env bootstrap failed, using existing env: %s", e)

        self.gemini_model_name = os.getenv("GCP_TTS_MODEL_NAME", "gemini-2.5-flash-tts")
        self.gemini_prompt = os.getenv("GCP_TTS_PROMPT", "Say the following clearly and naturally.")

        # Voice from the provided demo for Persian; configurable.
        self.gemini_voice_map = {
            "fa-IR": os.getenv("GCP_TTS_VOICE_FA", "Achernar"),
            "en-US": os.getenv("GCP_TTS_VOICE_EN", ""),
            "fr-FR": os.getenv("GCP_TTS_VOICE_FR", ""),
        }
        self.standard_voice_map = {
            "en-US": os.getenv("GCP_TTS_STANDARD_VOICE_EN", "en-US-Neural2-F"),
            "fa-IR": os.getenv("GCP_TTS_STANDARD_VOICE_FA", "fa-IR-Standard-A"),
            "fr-FR": os.getenv("GCP_TTS_STANDARD_VOICE_FR", "fr-FR-Neural2-A"),
        }

    @staticmethod
    def normalize_language_code(language_code: str) -> str:
        base = (language_code or "en").strip().lower()
        if base.startswith("fa"):
            return "fa-IR"
        if base.startswith("fr"):
            return "fr-FR"
        return "en-US"

    def synthesize_voice_note(self, text: str, language_code: str = "en-US") -> Optional[bytes]:
        """Synthesize OGG_OPUS bytes for Telegram voice notes."""
        if not text:
            return None

        try:
            from google.cloud import texttospeech
        except Exception as e:
            logger.error("google-cloud-texttospeech is not available: %s", e)
            return None

        locale = self.normalize_language_code(language_code)
        client = texttospeech.TextToSpeechClient()

        synthesis_input = self._build_input(text, texttospeech)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.OGG_OPUS,
        )

        attempts = [
            {"model_name": self.gemini_model_name, "name": self.gemini_voice_map.get(locale) or None},
            {"model_name": self.gemini_model_name, "name": None},
            {"model_name": None, "name": self.standard_voice_map.get(locale) or None},
            {"model_name": None, "name": None},
        ]

        for i, attempt in enumerate(attempts, start=1):
            try:
                voice = self._build_voice_params(texttospeech, locale, attempt["name"], attempt["model_name"])
                response = client.synthesize_speech(
                    input=synthesis_input,
                    voice=voice,
                    audio_config=audio_config,
                )
                if response and response.audio_content:
                    logger.debug(
                        "GCP TTS synthesis succeeded (attempt=%s, locale=%s, model=%s, voice=%s)",
                        i,
                        locale,
                        attempt["model_name"] or "classic",
                        attempt["name"] or "default",
                    )
                    return response.audio_content
            except Exception as e:
                logger.warning(
                    "GCP TTS attempt failed (attempt=%s, locale=%s, model=%s, voice=%s): %s",
                    i,
                    locale,
                    attempt["model_name"] or "classic",
                    attempt["name"] or "default",
                    e,
                )

        logger.error("All GCP TTS attempts failed for locale=%s", locale)
        return None

    def _build_input(self, text: str, texttospeech_module):
        """Build synthesis input, using prompt when supported by client version."""
        try:
            return texttospeech_module.SynthesisInput(
                text=text,
                prompt=self.gemini_prompt,
            )
        except TypeError:
            return texttospeech_module.SynthesisInput(text=text)

    @staticmethod
    def _build_voice_params(texttospeech_module, language_code: str, name: Optional[str], model_name: Optional[str]):
        kwargs = {"language_code": language_code}
        if name:
            kwargs["name"] = name
        if model_name:
            kwargs["model_name"] = model_name

        try:
            return texttospeech_module.VoiceSelectionParams(**kwargs)
        except TypeError:
            kwargs.pop("model_name", None)
            return texttospeech_module.VoiceSelectionParams(**kwargs)
