"""
Podcast ingestion with RSS parsing and audio-enclosure extraction.
"""

from __future__ import annotations

import io
import re
from typing import Any, Dict, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from services.learning_pipeline.constants import (
    DEFAULT_FETCH_TIMEOUT_SECONDS,
    MAX_ARTICLE_CHARS,
    MAX_AUDIO_DURATION_SECONDS,
)
from services.learning_pipeline.ingestors.common import safe_get
from services.learning_pipeline.security import validate_safe_http_url
from services.learning_pipeline.types import IngestedContent, SegmentRecord
from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import podcastparser
except Exception:
    podcastparser = None


class PodcastIngestor:
    def ingest(self, url: str, content_metadata: Optional[Dict[str, Any]] = None) -> IngestedContent:
        validate_safe_http_url(url)
        content_metadata = content_metadata or {}

        rss_url = _discover_rss(url)
        if rss_url and podcastparser is not None:
            try:
                validate_safe_http_url(rss_url)
                feed_response = safe_get(rss_url, timeout_seconds=DEFAULT_FETCH_TIMEOUT_SECONDS)
                feed_response.raise_for_status()
                feed = podcastparser.parse(rss_url, io.BytesIO(feed_response.content))
                episodes = feed.get("episodes") or []
                if episodes:
                    episode = episodes[0]
                    enclosure_url = episode.get("enclosures", [{}])[0].get("url")
                    duration_seconds = _parse_duration_seconds(episode.get("total_time"))
                    description = (
                        episode.get("description")
                        or episode.get("summary")
                        or feed.get("description")
                        or ""
                    )
                    description = _clean_text(description)[:MAX_ARTICLE_CHARS]
                    segments = [SegmentRecord(text=description, section_path="episode_description")] if description else []
                    needs_transcription = bool(enclosure_url)
                    if duration_seconds and duration_seconds > MAX_AUDIO_DURATION_SECONDS:
                        needs_transcription = False
                    return IngestedContent(
                        source_type="podcast",
                        language=content_metadata.get("language"),
                        text=description,
                        segments=segments,
                        assets=[
                            {
                                "asset_type": "metadata_json",
                                "storage_uri": "inline://podcast_feed",
                                "size_bytes": len(feed_response.content),
                                "checksum": None,
                            }
                        ],
                        needs_transcription=needs_transcription,
                        audio_url=enclosure_url,
                        metadata={
                            "rss_url": rss_url,
                            "duration_seconds": duration_seconds,
                            "title": episode.get("title") or feed.get("title"),
                        },
                    )
            except Exception as exc:
                logger.warning("Podcast RSS ingestion failed: %s", exc)

        # Fallback: parse source page metadata.
        response = safe_get(url, timeout_seconds=DEFAULT_FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        soup = BeautifulSoup(response.text[: MAX_ARTICLE_CHARS * 2], "html.parser")
        title = soup.find("meta", property="og:title") or soup.find("title")
        description = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
        title_text = ""
        if title:
            title_text = title.get("content") if title.name == "meta" else title.get_text(" ", strip=True)
        desc_text = _clean_text(description.get("content") if description else "")
        text_value = "\n".join([title_text, desc_text]).strip()[:MAX_ARTICLE_CHARS]
        segments = [SegmentRecord(text=text_value, section_path="podcast_page")] if text_value else []
        return IngestedContent(
            source_type="podcast",
            language=content_metadata.get("language"),
            text=text_value,
            segments=segments,
            assets=[],
            needs_transcription=False,
            audio_url=None,
            metadata={"rss_url": rss_url},
        )


def _discover_rss(url: str) -> Optional[str]:
    if re.search(r"\.(rss|xml)$", url, flags=re.IGNORECASE):
        return url
    try:
        response = safe_get(url, timeout_seconds=DEFAULT_FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
    except Exception:
        return None
    soup = BeautifulSoup(response.text, "html.parser")
    rss_link = soup.find("link", attrs={"type": "application/rss+xml"})
    if rss_link and rss_link.get("href"):
        return urljoin(url, rss_link["href"])
    return None


def _parse_duration_seconds(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    raw = str(value).strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    parts = raw.split(":")
    try:
        parts_int = [int(item) for item in parts]
    except ValueError:
        return None
    if len(parts_int) == 3:
        return parts_int[0] * 3600 + parts_int[1] * 60 + parts_int[2]
    if len(parts_int) == 2:
        return parts_int[0] * 60 + parts_int[1]
    return None


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()
