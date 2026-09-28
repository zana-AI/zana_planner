"""Load and validate the curated Explore catalog stored in PostgreSQL."""

from __future__ import annotations

import threading
import time
import re
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from utils.logger import get_logger

logger = get_logger(__name__)

_ESTIMATED_LEVEL = re.compile(r"^(?P<level>[ABC][12](?:-[ABC][12])?)(?:\s+\(stretch\))?\s+estimate\.\s*", re.I)
_VIDEO_REF = re.compile(r"[?&]video_id=([A-Za-z0-9_-]{11})(?:[&#]|$)")


def separate_level(description: Optional[str], level: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """Move legacy leading CEFR estimates from card subtitles into a badge."""
    match = _ESTIMATED_LEVEL.match(description or "")
    if not match:
        return level, description
    inferred = "~" + match.group("level").replace("-", "–")
    if "(stretch)" in match.group(0).lower():
        inferred += "+"
    return level or inferred, (description or "")[match.end():].strip() or None


def catalog_video_levels(catalog: "ExploreCatalog") -> dict[str, str]:
    levels = {}
    for category in catalog.categories:
        for topic in category.topics:
            for item in topic.items:
                match = _VIDEO_REF.search(item.native_ref or "")
                if match:
                    level, _ = separate_level(item.description, item.level)
                    if level:
                        levels[match[1]] = level
    return levels


def catalog_video_ids(catalog: "ExploreCatalog") -> set[str]:
    """Published video IDs from the already filtered catalog view."""
    return {match[1] for category in catalog.categories if category.published
            for topic in category.topics if topic.published
            for item in topic.items if item.published
            if (match := _VIDEO_REF.search(item.native_ref or ""))}


class ExploreItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    type: str = Field(default="link", min_length=1)
    order: int = 0
    published: bool = True
    url: Optional[str] = None
    native_ref: Optional[str] = None
    image: Optional[str] = None
    description: Optional[str] = None
    creator: Optional[str] = None
    content_id: Optional[str] = None
    language: Optional[str] = None
    level: Optional[str] = None
    # Optional verified video length; fresher DB metadata takes precedence.
    # Never use the last subtitle cue as a duration fallback.
    duration_seconds: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    estimated_read_seconds: Optional[int] = Field(default=None, gt=0)
    class_offer: Optional[str] = None
    # Editorial eligibility for Today; runtime cache readiness is also required.
    starter: bool = False


class ExploreTopic(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    order: int = 0
    published: bool = True
    items: list[ExploreItem] = Field(default_factory=list)


class ExploreCategory(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    # A glyph and a colour for the subject tile. Both are optional: a category
    # with neither still renders, just without a face.
    icon: Optional[str] = None
    accent: Optional[str] = None
    language: Optional[str] = None
    order: int = 0
    published: bool = True
    topics: list[ExploreTopic] = Field(default_factory=list)


class ExploreCatalog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    version: int = 1
    categories: list[ExploreCategory] = Field(default_factory=list)

    def published_view(self) -> "ExploreCatalog":
        categories = []
        for category in sorted(self.categories, key=lambda value: (value.order, value.id)):
            if not category.published:
                continue
            topics = []
            for topic in sorted(category.topics, key=lambda value: (value.order, value.id)):
                if not topic.published:
                    continue
                items = [item for item in sorted(topic.items, key=lambda value: (value.order, value.id)) if item.published]
                topics.append(topic.model_copy(update={"items": items}))
            categories.append(category.model_copy(update={"topics": topics}))
        return self.model_copy(update={"categories": categories})


class ExploreConfigLoader:
    """Read the database catalog with a short cache and last-good fallback."""

    def __init__(self, cache_ttl_seconds: int = 60, catalog_reader: Optional[Callable[[], dict]] = None):
        self.cache_ttl_seconds = cache_ttl_seconds
        self.catalog_reader = catalog_reader or self._read_database
        self._cache: Optional[ExploreCatalog] = None
        self._cache_loaded_at = 0.0
        self._lock = threading.Lock()

    def load(self) -> ExploreCatalog:
        now = time.monotonic()
        with self._lock:
            if self._cache is not None and now - self._cache_loaded_at < self.cache_ttl_seconds:
                return self._cache
            try:
                catalog = ExploreCatalog.model_validate(self.catalog_reader()).published_view()
                self._cache = catalog
                self._cache_loaded_at = now
                return catalog
            except Exception:
                logger.exception("Explore database catalog unavailable")
            self._cache_loaded_at = now
            return self._cache or ExploreCatalog()

    def invalidate(self) -> None:
        """Make an explicit share visible on the next request in this process."""
        with self._lock:
            self._cache_loaded_at = 0.0

    @staticmethod
    def _read_database() -> dict[str, Any]:
        from db.postgres_db import get_db_session

        with get_db_session() as session:
            document = session.execute(text("SELECT document FROM explore_catalog WHERE id='main'")).scalar_one_or_none()
        if not isinstance(document, dict):
            raise ValueError("Explore catalog has not been seeded")
        return document


explore_config_loader = ExploreConfigLoader()
