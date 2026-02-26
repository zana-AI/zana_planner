"""
YouTube ingestion with subtitle-first strategy and ASR fallback marker.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.learning_pipeline.constants import DEFAULT_FETCH_TIMEOUT_SECONDS
from services.learning_pipeline.ingestors.common import parse_json3_to_segments, parse_vtt_to_segments, safe_get
from services.learning_pipeline.security import validate_safe_http_url
from services.learning_pipeline.types import IngestedContent, SegmentRecord
from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import yt_dlp
except Exception:
    yt_dlp = None


class YouTubeIngestor:
    def ingest(self, url: str, content_metadata: Optional[Dict[str, Any]] = None) -> IngestedContent:
        validate_safe_http_url(url)
        content_metadata = content_metadata or {}
        segments: List[SegmentRecord] = []
        language = content_metadata.get("language")
        subtitle_payload = None
        video_info: Dict[str, Any] = {}

        if yt_dlp is not None:
            try:
                ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                video_info = info or {}
                subtitle_ref = _pick_subtitle_ref(video_info)
                if subtitle_ref and subtitle_ref.get("url"):
                    validate_safe_http_url(subtitle_ref["url"])
                    response = safe_get(subtitle_ref["url"], timeout_seconds=DEFAULT_FETCH_TIMEOUT_SECONDS)
                    response.raise_for_status()
                    subtitle_payload = response.text
                    ext = (subtitle_ref.get("ext") or "").lower()
                    if ext in ("json3", "srv3"):
                        segments = parse_json3_to_segments(subtitle_payload)
                    else:
                        segments = parse_vtt_to_segments(subtitle_payload)
                    language = language or subtitle_ref.get("lang")
            except Exception as exc:
                logger.warning("YouTube subtitle extraction failed: %s", exc)

        transcript_text = " ".join(segment.text for segment in segments).strip()
        if transcript_text:
            assets = [
                {
                    "asset_type": "transcript_json",
                    "storage_uri": "inline://youtube_subtitles",
                    "size_bytes": len(transcript_text.encode("utf-8")),
                    "checksum": None,
                }
            ]
            if subtitle_payload:
                assets.append(
                    {
                        "asset_type": "metadata_json",
                        "storage_uri": "inline://youtube_subtitles_raw",
                        "size_bytes": len(subtitle_payload.encode("utf-8")),
                        "checksum": None,
                    }
                )
            return IngestedContent(
                source_type="youtube",
                language=language,
                text=transcript_text,
                segments=segments,
                assets=assets,
                needs_transcription=False,
                audio_url=None,
                metadata={"captions_used": True},
            )

        description = str(content_metadata.get("description") or video_info.get("description") or "").strip()
        audio_stream_url = _pick_audio_stream_url(video_info)
        if audio_stream_url:
            try:
                validate_safe_http_url(audio_stream_url)
            except Exception:
                audio_stream_url = None
        text_value = description[:4000] if description else ""
        needs_transcription = bool(audio_stream_url)
        if text_value:
            segments = [SegmentRecord(text=text_value, section_path="description")]
        return IngestedContent(
            source_type="youtube",
            language=language,
            text=text_value,
            segments=segments,
            assets=[],
            needs_transcription=needs_transcription,
            audio_url=audio_stream_url,
            metadata={
                "captions_used": False,
                "audio_stream_found": bool(audio_stream_url),
                "duration_seconds": video_info.get("duration"),
            },
        )


def _pick_subtitle_ref(info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    subtitles = info.get("subtitles") or {}
    auto_subtitles = info.get("automatic_captions") or {}
    candidates = _subtitle_candidates(subtitles) + _subtitle_candidates(auto_subtitles)
    if not candidates:
        return None
    preferred_langs = ("en", "en-us", "en-gb")
    for lang in preferred_langs:
        for candidate in candidates:
            if candidate.get("lang", "").lower() == lang:
                return candidate
    return candidates[0]


def _subtitle_candidates(bucket: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for lang, entries in (bucket or {}).items():
        for item in entries or []:
            url = item.get("url")
            if not url:
                continue
            ext = item.get("ext") or ""
            candidates.append({"lang": str(lang), "ext": str(ext), "url": str(url)})
    # Prefer VTT and json3 over others for easier parsing
    priority = {"vtt": 1, "json3": 2, "srv3": 3}
    candidates.sort(key=lambda item: priority.get(item.get("ext", "").lower(), 100))
    return candidates


def _pick_audio_stream_url(info: Dict[str, Any]) -> Optional[str]:
    formats = info.get("formats") or []
    candidates = []
    for item in formats:
        stream_url = item.get("url")
        audio_codec = str(item.get("acodec") or "").lower()
        video_codec = str(item.get("vcodec") or "").lower()
        if not stream_url or not audio_codec or audio_codec == "none":
            continue
        candidates.append(
            {
                "url": str(stream_url),
                "is_audio_only": video_codec == "none",
                "abr": float(item.get("abr") or 0.0),
                "asr": float(item.get("asr") or 0.0),
            }
        )
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            0 if item["is_audio_only"] else 1,
            -item["abr"],
            -item["asr"],
        )
    )
    return candidates[0]["url"]
