"""
Content consumption manager API: resolve URL, user library, consume events, heatmap.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from ..dependencies import get_current_user
from ..schemas import (
    ResolveContentRequest,
    AddUserContentRequest,
    ConsumeEventRequest,
    UpdateUserContentRequest,
)
from services.content_resolve_service import ContentResolveService
from services.content_progress_service import ContentProgressService
from repositories.content_repo import ContentRepository
from utils.logger import get_logger

router = APIRouter(prefix="/api", tags=["content"])
logger = get_logger(__name__)


def get_content_repo() -> ContentRepository:
    return ContentRepository()


def get_resolve_service() -> ContentResolveService:
    return ContentResolveService(content_repo=get_content_repo())


def get_progress_service() -> ContentProgressService:
    return ContentProgressService(content_repo=get_content_repo())


@router.post("/content/resolve")
async def resolve_content(
    body: ResolveContentRequest,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """Resolve URL to content metadata and upsert into catalog. Returns content row with content_id."""
    try:
        service = get_resolve_service()
        row = service.resolve(body.url)
        return row
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("content resolve failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to resolve content")


@router.post("/user-content")
async def add_user_content(
    body: AddUserContentRequest,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """Add content to user library. Returns user_content id and status."""
    repo = get_content_repo()
    content = repo.get_content_by_id(body.content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    uc_id = repo.add_user_content(str(user_id), body.content_id)
    return {"user_content_id": uc_id, "status": "saved"}


@router.get("/my-contents")
async def get_my_contents(
    status: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = 20,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """Paginated list of user's content with content + user_content + rollup buckets."""
    repo = get_content_repo()
    rows = repo.get_user_contents(str(user_id), status=status, cursor=cursor, limit=limit)
    # Normalize for JSON: ensure buckets is list, metadata_json is dict
    items: List[Dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        if "buckets" in item and item["buckets"] is not None:
            b = item["buckets"]
            item["buckets"] = b if isinstance(b, list) else []
        if "metadata_json" in item and item["metadata_json"] is not None:
            m = item["metadata_json"]
            item["metadata_json"] = m if isinstance(m, dict) else {}
        items.append(item)
    return {"items": items, "count": len(items)}


@router.post("/consume-event")
async def post_consume_event(
    body: ConsumeEventRequest,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """Record a consumption segment. Returns progress_ratio and status."""
    service = get_progress_service()
    result = service.record_consumption(
        user_id=user_id,
        content_id=body.content_id,
        start_position=body.start_position,
        end_position=body.end_position,
        position_unit=body.position_unit,
        started_at=body.started_at,
        ended_at=body.ended_at,
        client=body.client,
    )
    return result


@router.get("/content/{content_id}/heatmap")
async def get_content_heatmap(
    content_id: str,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return bucket_count and buckets for content heatmap."""
    repo = get_content_repo()
    data = repo.get_heatmap(str(user_id), content_id)
    if not data:
        return {"bucket_count": 120, "buckets": [0] * 120}
    return data


@router.patch("/user-content/{content_id}")
async def update_user_content(
    content_id: str,
    body: UpdateUserContentRequest,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update user_content status, notes, or rating."""
    repo = get_content_repo()
    uc = repo.get_user_content(str(user_id), content_id)
    if not uc:
        raise HTTPException(status_code=404, detail="User content not found")
    repo.update_user_content_meta(
        str(user_id),
        content_id,
        status=body.status,
        notes=body.notes,
        rating=body.rating,
    )
    return {"content_id": content_id, "updated": True}
