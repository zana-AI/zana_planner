"""Data-driven Explore catalog endpoint."""

from fastapi import APIRouter, Depends, Request

from ..dependencies import get_current_user
from services.explore_config import explore_config_loader

router = APIRouter(prefix="/api", tags=["explore"])


@router.get("/explore")
async def get_explore_catalog(request: Request, user_id: int = Depends(get_current_user)):
    """Return the published Explore catalog from the configured YAML source."""
    return explore_config_loader.load().model_dump(mode="json")
