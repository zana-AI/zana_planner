"""
Speech-to-text service for fallback transcription.
"""

from __future__ import annotations

from typing import List, Optional

from services.learning_pipeline.constants import (
    DEFAULT_FETCH_TIMEOUT_SECONDS,
    MAX_AUDIO_DURATION_SECONDS,
)
from services.learning_pipeline.ingestors.common import safe_get
from services.learning_pipeline.security import validate_safe_http_url
from services.learning_pipeline.types import SegmentRecord
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_AUDIO_DOWNLOAD_BYTES = 30 * 1024 * 1024


class TranscriptionService:
    def transcribe_audio_url(
        self,
        audio_url: str,
        language_code: str = "en-US",
        duration_seconds: Optional[float] = None,
    ) -> List[SegmentRecord]:
        validate_safe_http_url(audio_url)
        if duration_seconds and duration_seconds > MAX_AUDIO_DURATION_SECONDS:
            raise ValueError("Audio duration exceeds maximum supported duration")

        audio_bytes = _download_audio(audio_url)
        if not audio_bytes:
            return []
        try:
            from google.cloud import speech
        except Exception as exc:
            raise RuntimeError("google-cloud-speech is not available") from exc

        client = speech.SpeechClient()
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED,
            language_code=language_code or "en-US",
            enable_automatic_punctuation=True,
            enable_word_time_offsets=True,
            model="latest_long",
        )
        audio = speech.RecognitionAudio(content=audio_bytes)
        response = client.recognize(config=config, audio=audio)
        segments: List[SegmentRecord] = []
        for result in response.results:
            if not result.alternatives:
                continue
            alt = result.alternatives[0]
            text_value = (alt.transcript or "").strip()
            if not text_value:
                continue
            start_ms = None
            end_ms = None
            words = list(getattr(alt, "words", []) or [])
            if words:
                start_ms = _duration_to_ms(words[0].start_time)
                end_ms = _duration_to_ms(words[-1].end_time)
            segments.append(
                SegmentRecord(
                    text=text_value,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    section_path="transcription",
                )
            )
        return segments


def _download_audio(audio_url: str) -> bytes:
    response = safe_get(
        audio_url,
        timeout_seconds=DEFAULT_FETCH_TIMEOUT_SECONDS,
        stream=True,
    )
    response.raise_for_status()
    content = bytearray()
    for chunk in response.iter_content(chunk_size=8192):
        if not chunk:
            continue
        content.extend(chunk)
        if len(content) > MAX_AUDIO_DOWNLOAD_BYTES:
            raise ValueError("Audio file is too large for inline transcription")
    return bytes(content)


def _duration_to_ms(duration_obj) -> Optional[int]:
    if duration_obj is None:
        return None
    seconds = getattr(duration_obj, "seconds", None)
    nanos = getattr(duration_obj, "nanos", None)
    if seconds is None:
        return None
    seconds = int(seconds)
    nanos = int(nanos or 0)
    return seconds * 1000 + int(nanos / 1_000_000)
