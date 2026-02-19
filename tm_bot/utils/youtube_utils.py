"""
YouTube video metadata and formatting utilities.

Single place for YouTube-related logic: video analysis (duration, topic, category,
language, captions), message formatting for the bot, and future content-manager
features (transcript fetch for Q&A, caption language list, reminders, repeat/track).

Future extensions (document only):
- Transcript: fetch via yt-dlp or transcript API for summarization and Q&A.
- Captions: list caption languages (yt-dlp now; YouTube captions.list if OAuth added).
- Tracking/reminders: integrate with youtube_watch_stats and content_management_service.
"""
import os
import re
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False

try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# Patterns to extract video_id from URLs (same logic as message_handlers._extract_youtube_video_id)
_YOUTUBE_VIDEO_ID_PATTERNS = [
    r"(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})",
    r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
    r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
]
_VIDEO_ID_RE = re.compile("|".join(f"({p})" for p in _YOUTUBE_VIDEO_ID_PATTERNS))


def extract_video_id(url_or_text: str) -> Optional[str]:
    """Extract YouTube video ID from a URL or text containing a YouTube link."""
    for m in _VIDEO_ID_RE.finditer(url_or_text):
        for g in m.groups():
            if g:
                return g
    return None


def format_duration(seconds: Optional[float]) -> str:
    """Return human-readable duration: '5:32', '1h 2m', etc."""
    if seconds is None or seconds <= 0:
        return "Unknown"
    secs = int(seconds)
    if secs < 3600:
        m, s = divmod(secs, 60)
        if m == 0:
            return f"0:{s:02d}"
        return f"{m}:{s:02d}"
    h, rest = divmod(secs, 3600)
    m, s = divmod(rest, 60)
    if m == 0 and s == 0:
        return f"{h}h"
    if s == 0:
        return f"{h}h {m}m"
    return f"{h}h {m}m {s}s"


def get_video_info(video_id: str, url: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch metadata for a YouTube video.

    Uses yt-dlp first; falls back to basic HTML fetch if yt-dlp is missing or fails.
    Optional: if YOUTUBE_API_KEY or GOOGLE_API_KEY is set, enriches with
    category name and default language from YouTube Data API v3.

    Returns a dict with: title, duration_seconds, duration_formatted, category,
    tags, language, captions_available, channel, view_count, description_snippet, url.
    On failure returns a minimal dict so the bot can still show the Mini App button.
    """
    if not url:
        url = f"https://www.youtube.com/watch?v={video_id}"

    result: Dict[str, Any] = {
        "title": "YouTube Video",
        "duration_seconds": None,
        "duration_formatted": "Unknown",
        "category": None,
        "tags": [],
        "language": None,
        "captions_available": False,
        "channel": None,
        "view_count": None,
        "description_snippet": None,
        "url": url,
    }

    if YT_DLP_AVAILABLE:
        try:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return result

                result["title"] = info.get("title") or result["title"]
                duration_sec = info.get("duration")
                result["duration_seconds"] = duration_sec
                result["duration_formatted"] = format_duration(duration_sec)
                result["category"] = info.get("category") or None
                result["tags"] = list(info.get("tags") or [])[:15]
                result["channel"] = info.get("uploader") or None
                result["view_count"] = info.get("view_count")
                desc = (info.get("description") or "")[:300]
                result["description_snippet"] = desc.strip() or None

                subtitles = info.get("subtitles") or {}
                auto_captions = info.get("automatic_captions") or {}
                result["captions_available"] = bool(subtitles or auto_captions)

                # Language: yt-dlp may expose meta_language or similar
                result["language"] = (
                    info.get("language")
                    or info.get("meta_language")
                    or None
                )
        except Exception as e:
            logger.debug("youtube_utils get_video_info yt-dlp failed: %s", e)
            result = _get_video_info_basic(url, result)
    else:
        result = _get_video_info_basic(url, result)

    # Optional: YouTube Data API v3 for category name and language
    api_key = os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if api_key:
        _enrich_with_youtube_api(video_id, result, api_key)

    return result


def _get_video_info_basic(url: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback: fetch page and parse og:title, og:description."""
    if not REQUESTS_AVAILABLE:
        return result
    try:
        resp = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        )
        if resp.status_code != 200:
            return result
        soup = BeautifulSoup(resp.text, "html.parser")
        title_tag = soup.find("meta", property="og:title")
        if title_tag and title_tag.get("content"):
            result["title"] = title_tag["content"]
        desc_tag = soup.find("meta", property="og:description")
        if desc_tag and desc_tag.get("content"):
            result["description_snippet"] = (desc_tag["content"] or "")[:300]
    except Exception as e:
        logger.debug("youtube_utils basic fetch failed: %s", e)
    return result


def _enrich_with_youtube_api(video_id: str, result: Dict[str, Any], api_key: str) -> None:
    """Enrich result with category name and language from YouTube Data API v3."""
    try:
        # videos.list
        vurl = (
            "https://www.googleapis.com/youtube/v3/videos"
            f"?id={video_id}&part=snippet,contentDetails&key={api_key}"
        )
        resp = requests.get(vurl, timeout=5)
        if resp.status_code != 200:
            return
        data = resp.json()
        items = data.get("items") or []
        if not items:
            return
        snippet = items[0].get("snippet") or {}
        category_id = snippet.get("categoryId")
        lang = snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage")
        if lang:
            result["language"] = result["language"] or lang
        if category_id:
            # videoCategories.list to get category title
            cat_url = (
                "https://www.googleapis.com/youtube/v3/videoCategories"
                f"?id={category_id}&part=snippet&key={api_key}"
            )
            cat_resp = requests.get(cat_url, timeout=5)
            if cat_resp.status_code == 200:
                cat_data = cat_resp.json()
                cat_items = cat_data.get("items") or []
                if cat_items and cat_items[0].get("snippet", {}).get("title"):
                    result["category"] = result["category"] or cat_items[0]["snippet"]["title"]
            else:
                result["category"] = result["category"] or f"Category {category_id}"
    except Exception as e:
        logger.debug("youtube_utils YouTube API enrichment failed: %s", e)


def format_analysis_message(info: Dict[str, Any]) -> str:
    """
    Build short, Telegram-friendly analysis text: title, duration, category/topic,
    language (if present), captions (yes/no). Avoid long blocks.
    """
    parts: List[str] = []

    title = (info.get("title") or "YouTube Video").strip()
    if len(title) > 80:
        title = title[:77] + "..."
    parts.append(f"<b>{title}</b>")

    dur = info.get("duration_formatted") or format_duration(info.get("duration_seconds"))
    if dur and dur != "Unknown":
        parts.append(f"Duration: {dur}")

    channel = info.get("channel")
    if channel:
        parts.append(f"Channel: {channel}")

    category = info.get("category")
    if category:
        parts.append(f"Category: {category}")

    tags = info.get("tags") or []
    if tags:
        topic_str = ", ".join(tags[:5])
        if len(topic_str) > 50:
            topic_str = topic_str[:47] + "..."
        parts.append(f"Topics: {topic_str}")

    language = info.get("language")
    if language:
        parts.append(f"Language: {language}")

    captions = "Yes" if info.get("captions_available") else "No"
    parts.append(f"Captions: {captions}")

    return "\n".join(parts)
