"""Data-driven Explore catalog endpoint."""

import re

from fastapi import APIRouter, Depends, Response

from ..dependencies import get_current_user
from services.explore_config import explore_config_loader
from repositories.explore_repo import ExploreRepository
from utils.logger import get_logger

router = APIRouter(prefix="/api", tags=["explore"])
logger = get_logger(__name__)


@router.get("/explore")
def get_explore_catalog(response: Response, user_id: int = Depends(get_current_user)):
    """Published allowlist plus safe club cards and factual learning metadata."""
    response.headers["Cache-Control"] = "private, no-store"
    # model_dump creates a fresh response; never mutate the shared config cache.
    catalog = explore_config_loader.load().model_dump(mode="json")
    items = [item for category in catalog["categories"] for topic in category["topics"] for item in topic["items"]]
    videos = [(item, re.search(r"[?&]video_id=([\w-]{11})(?:[&#]|$)", item.get("native_ref") or "")) for item in items]
    repo = ExploreRepository()
    catalog.update(metadata_available=True, clubs_available=True, clubs=[])
    try:
        metadata = repo.video_metadata(sorted({match[1] for _, match in videos if match}))
        for item, match in videos:
            if match:
                item.update(metadata.get(match[1], {"subtitles_available": False}))
    except Exception:
        logger.warning("Explore video metadata unavailable", exc_info=True)
        catalog["metadata_available"] = False
    try:
        catalog["clubs"] = repo.clubs(user_id)
    except Exception:
        logger.warning("Explore clubs unavailable", exc_info=True)
        catalog["clubs_available"] = False
    return catalog
