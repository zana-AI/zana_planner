"""Load and validate the curated Explore catalog stored in PostgreSQL."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from utils.logger import get_logger

logger = get_logger(__name__)


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
    # Optional verified video length; fresher DB metadata takes precedence.
    # Never use the last subtitle cue as a duration fallback.
    duration_seconds: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
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

    @staticmethod
    def _read_database() -> dict[str, Any]:
        from db.postgres_db import get_db_session

        with get_db_session() as session:
            document = session.execute(text("SELECT document FROM explore_catalog WHERE id='main'")).scalar_one_or_none()
        if not isinstance(document, dict):
            raise ValueError("Explore catalog has not been seeded")
        return document


explore_config_loader = ExploreConfigLoader()
