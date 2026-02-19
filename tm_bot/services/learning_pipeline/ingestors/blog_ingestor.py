"""
Blog/article ingestion using trafilatura first, then BeautifulSoup fallback.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from services.learning_pipeline.constants import DEFAULT_FETCH_TIMEOUT_SECONDS, MAX_ARTICLE_CHARS
from services.learning_pipeline.ingestors.common import safe_get
from services.learning_pipeline.security import validate_safe_http_url
from services.learning_pipeline.types import IngestedContent, SegmentRecord
from utils.logger import get_logger

logger = get_logger(__name__)

try:
    import trafilatura
except Exception:
    trafilatura = None


class BlogIngestor:
    def ingest(self, url: str, content_metadata: Optional[Dict[str, Any]] = None) -> IngestedContent:
        validate_safe_http_url(url)
        content_metadata = content_metadata or {}
        language = content_metadata.get("language")

        if trafilatura is not None:
            try:
                downloaded = trafilatura.fetch_url(url)
                if downloaded:
                    extracted = trafilatura.extract(
                        downloaded,
                        include_comments=False,
                        include_tables=False,
                        include_images=False,
                        include_links=False,
                    )
                    if extracted:
                        extracted = extracted[:MAX_ARTICLE_CHARS]
                        segments = _segments_from_text(extracted)
                        metadata = trafilatura.extract_metadata(downloaded)
                        if metadata and getattr(metadata, "language", None):
                            language = language or metadata.language
                        return IngestedContent(
                            source_type="blog",
                            language=language,
                            text=extracted,
                            segments=segments,
                            assets=[
                                {
                                    "asset_type": "clean_text",
                                    "storage_uri": "inline://trafilatura",
                                    "size_bytes": len(extracted.encode("utf-8")),
                                    "checksum": None,
                                }
                            ],
                            needs_transcription=False,
                            metadata={"extraction_method": "trafilatura"},
                        )
            except Exception as exc:
                logger.warning("Trafilatura extraction failed: %s", exc)

        response = safe_get(url, timeout_seconds=DEFAULT_FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        html = response.text[: MAX_ARTICLE_CHARS * 2]
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "iframe"]):
            tag.decompose()
        title = None
        title_tag = soup.find("meta", property="og:title") or soup.find("title")
        if title_tag:
            title = title_tag.get("content") if title_tag.name == "meta" else title_tag.get_text(strip=True)
        headings_and_text = []
        article = soup.find("article") or soup.body or soup
        for block in article.find_all(["h1", "h2", "h3", "p", "li"]):
            value = re.sub(r"\s+", " ", block.get_text(" ", strip=True)).strip()
            if len(value) < 20 and block.name.startswith("h"):
                continue
            if not value:
                continue
            headings_and_text.append((block.name, value))
        if not headings_and_text:
            body_text = re.sub(r"\s+", " ", article.get_text(" ", strip=True)).strip()
            headings_and_text = [("p", body_text)]
        segments: List[SegmentRecord] = []
        current_section = title or "article"
        for tag_name, value in headings_and_text:
            if tag_name in ("h1", "h2", "h3"):
                current_section = value[:120]
                continue
            for chunk in _split_chunk(value):
                segments.append(SegmentRecord(text=chunk, section_path=current_section))
        raw_text = "\n\n".join(segment.text for segment in segments)[:MAX_ARTICLE_CHARS]
        return IngestedContent(
            source_type="blog",
            language=language,
            text=raw_text,
            segments=segments,
            assets=[
                {
                    "asset_type": "raw_html",
                    "storage_uri": "inline://html_response",
                    "size_bytes": len(html.encode("utf-8")),
                    "checksum": None,
                },
                {
                    "asset_type": "clean_text",
                    "storage_uri": "inline://beautifulsoup",
                    "size_bytes": len(raw_text.encode("utf-8")),
                    "checksum": None,
                },
            ],
            needs_transcription=False,
            metadata={"extraction_method": "beautifulsoup"},
        )


def _segments_from_text(text: str) -> List[SegmentRecord]:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text or "") if part.strip()]
    segments: List[SegmentRecord] = []
    for paragraph in paragraphs:
        for chunk in _split_chunk(paragraph):
            segments.append(SegmentRecord(text=chunk, section_path="article"))
    return segments


def _split_chunk(text: str, max_chars: int = 1400) -> List[str]:
    value = (text or "").strip()
    if not value:
        return []
    if len(value) <= max_chars:
        return [value]
    words = value.split()
    out: List[str] = []
    current: List[str] = []
    current_len = 0
    for word in words:
        next_len = current_len + len(word) + (1 if current else 0)
        if next_len > max_chars and current:
            out.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len = next_len
    if current:
        out.append(" ".join(current))
    return out
