"""Load and validate the data-driven Explore catalog."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
    class_offer: Optional[str] = None


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
    """Fetch Explore YAML with a short in-process cache and stale fallback."""

    def __init__(self, local_path: Optional[Path] = None, cache_ttl_seconds: int = 60):
        self.local_path = local_path or Path(__file__).resolve().parents[1] / "config" / "explore.yaml"
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: Optional[ExploreCatalog] = None
        self._cache_loaded_at = 0.0
        self._lock = threading.Lock()

    def load(self) -> ExploreCatalog:
        now = time.monotonic()
        with self._lock:
            if self._cache is not None and now - self._cache_loaded_at < self.cache_ttl_seconds:
                return self._cache
            remote_url = os.getenv("EXPLORE_CONFIG_URL", "").strip()
            sources = [("remote", remote_url)] if remote_url else []
            sources.append(("local", str(self.local_path)))
            for source_name, source in sources:
                if not source:
                    continue
                try:
                    catalog = self._parse(self._read_source(source_name, source)).published_view()
                    self._cache = catalog
                    self._cache_loaded_at = now
                    return catalog
                except (OSError, httpx.HTTPError, ValidationError, TypeError, ValueError, yaml.YAMLError) as exc:
                    logger.warning("Explore %s config unavailable: %s", source_name, exc)
            self._cache_loaded_at = now
            return self._cache or ExploreCatalog()

    @staticmethod
    def _read_source(source_name: str, source: str) -> str:
        if source_name == "remote":
            response = httpx.get(source, timeout=5.0, follow_redirects=True)
            response.raise_for_status()
            return response.text
        return Path(source).read_text(encoding="utf-8")

    @staticmethod
    def _parse(raw: str) -> ExploreCatalog:
        document: Any = yaml.safe_load(raw)
        if not isinstance(document, dict):
            raise ValueError("Explore YAML root must be a mapping")
        return ExploreCatalog.model_validate(document)


explore_config_loader = ExploreConfigLoader()
