"""
Content resolution: canonicalize URL, resolve metadata via ContentService (and youtube_utils for YouTube),
upsert into content table with optional TTL cache.
"""
from typing import Any, Dict, Optional

from utils.url_utils import canonicalize_url
from services.content_service import ContentService
from repositories.content_repo import ContentRepository
from utils.logger import get_logger

logger = get_logger(__name__)

# Cache TTL: if content was updated within this many seconds, return from DB without re-fetching.
CONTENT_CACHE_TTL_SECONDS = 86400  # 24 hours


def _type_to_content_type(url_type: str) -> str:
    """Map ContentService type to content_type enum."""
    if url_type == "youtube":
        return "video"
    if url_type in ("podcast",):
        return "audio"
    if url_type in ("substack_article", "blog"):
        return "text"
    return "other"


def _parse_iso_to_seconds(updated_at: Optional[str]) -> Optional[int]:
    """Parse ISO timestamp and return seconds since epoch for TTL comparison."""
    if not updated_at:
        return None
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        return None


class ContentResolveService:
    """Resolve URL to content metadata and upsert into content table."""

    def __init__(self, content_repo: Optional[ContentRepository] = None):
        self._repo = content_repo or ContentRepository()
        self._content_service = ContentService()

    def resolve(self, url: str) -> Dict[str, Any]:
        """
        Resolve URL to content: canonicalize, optionally return cached row, else fetch via ContentService
        and upsert. Returns content row dict with content_id (id).
        """
        canonical = canonicalize_url(url)
        if not canonical:
            raise ValueError("Invalid or empty URL")

        # Check cache: existing row updated within TTL
        existing = self._repo.get_content_by_canonical_url(canonical)
        if existing:
            updated_at_sec = _parse_iso_to_seconds(existing.get("updated_at"))
            if updated_at_sec:
                import time
                if (int(time.time()) - updated_at_sec) < CONTENT_CACHE_TTL_SECONDS:
                    existing["content_id"] = existing["id"]
                    return existing

        # Fetch metadata
        link_meta = self._content_service.process_link(url)
        url_type = link_meta.get("type") or "other"
        provider = url_type
        content_type = _type_to_content_type(url_type)

        title = link_meta.get("title")
        description = (link_meta.get("description") or "")[:2000]
        metadata = dict(link_meta.get("metadata") or {})

        duration_hours = link_meta.get("duration")
        duration_seconds = float(duration_hours * 3600) if duration_hours else None
        estimated_read_seconds = None
        if content_type == "text" and duration_hours:
            estimated_read_seconds = int(duration_hours * 3600)

        author_channel = metadata.get("channel") or None
        thumbnail_url = None

        # YouTube: enrich metadata and set thumbnail
        if url_type == "youtube":
            try:
                from utils.youtube_utils import get_video_info, extract_video_id
                video_id = extract_video_id(url)
                if video_id:
                    info = get_video_info(video_id, url=url)
                    metadata["category"] = info.get("category")
                    metadata["tags"] = info.get("tags")
                    metadata["language"] = info.get("language")
                    metadata["captions_available"] = info.get("captions_available")
                    thumbnail_url = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
            except Exception as e:
                logger.debug("youtube_utils enrichment in resolve: %s", e)

        content_id = self._repo.upsert_content(
            canonical_url=canonical,
            original_url=url,
            provider=provider,
            content_type=content_type,
            title=title,
            description=description,
            author_channel=author_channel,
            language=metadata.get("language"),
            published_at=None,
            duration_seconds=duration_seconds,
            estimated_read_seconds=estimated_read_seconds,
            thumbnail_url=thumbnail_url,
            metadata_json=metadata,
        )
        row = self._repo.get_content_by_id(content_id)
        if row:
            row["content_id"] = row["id"]
            return row
        return {"id": content_id, "content_id": content_id, "canonical_url": canonical, "original_url": url, "provider": provider, "content_type": content_type, "title": title}
