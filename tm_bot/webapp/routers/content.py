"""
Content consumption manager API: resolve URL, user library, consume events, heatmap.
"""
import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, RedirectResponse
from ..dependencies import get_current_user
from ..schemas import (
    ResolveContentRequest,
    AddUserContentRequest,
    AssignUserContentRequest,
    ConsumeEventRequest,
    UpdateUserContentRequest,
    CreateHighlightRequest,
    UpdateHighlightRequest,
    AnalyzeContentRequest,
    AskContentRequest,
    CreateQuizRequest,
    SubmitQuizRequest,
)
from utils.logger import get_logger
from utils.admin_utils import is_admin
from services.explore_config import separate_level
from datetime import datetime, timedelta, timezone

if TYPE_CHECKING:
    from services.content_resolve_service import ContentResolveService
    from services.content_progress_service import ContentProgressService
    from services.learning_pipeline.service import LearningPipelineService
    from services.object_storage_service import ObjectStorageService
    from repositories.content_repo import ContentRepository

try:
    from services.learning_pipeline.embedding_service import VectorStoreUnavailableError
except Exception:  # pragma: no cover - fallback for partial environments
    class VectorStoreUnavailableError(Exception):
        pass

router = APIRouter(prefix="/api", tags=["content"])
logger = get_logger(__name__)


class ShareContentRequest(BaseModel):
    destination: Literal["link", "explore"]
    language: Optional[str] = Field(default=None, pattern=r"^[a-zA-Z]{2,3}(?:-[a-zA-Z]{2})?$")
    level: Optional[Literal["A1", "A2", "B1", "B2", "C1", "C2"]] = None


class ClubVideoAnnotationRequest(BaseModel):
    club_id: str = Field(min_length=1, max_length=128)
    position_seconds: int = Field(ge=0, le=604800)
    body: str = Field(min_length=1, max_length=2000)


def _require_club_share(content_id: str, club_id: str, user_id: str):
    from repositories.content_share_repo import ContentShareRepository

    share_repo = ContentShareRepository()
    if not share_repo.is_active_member_of_share(content_id, club_id, user_id):
        raise HTTPException(status_code=403, detail="This item is not shared with your club")
    return share_repo


class ClubContentShareRequest(BaseModel):
    club_id: str = Field(min_length=1, max_length=128)


def get_content_repo() -> "ContentRepository":
    from repositories.content_repo import ContentRepository

    return ContentRepository()


def get_resolve_service() -> "ContentResolveService":
    from services.content_resolve_service import ContentResolveService

    return ContentResolveService(content_repo=get_content_repo())


def get_progress_service() -> "ContentProgressService":
    from services.content_progress_service import ContentProgressService

    return ContentProgressService(content_repo=get_content_repo())


def get_learning_service() -> "LearningPipelineService":
    from services.learning_pipeline.service import LearningPipelineService

    return LearningPipelineService()


def get_object_storage_service() -> "ObjectStorageService":
    from services.object_storage_service import ObjectStorageService

    return ObjectStorageService()


def _club_teacher_for_content(content: Dict[str, Any]) -> Optional[str]:
    """Return the club-owner user_id for club-shared content, else None.

    A club's owner is its teacher for this content-sharing feature — see
    AGENTS.md's teacher/club-owner assumption. Content that isn't shared to a
    club (visibility != 'club', or no club_id) has no teacher.
    """
    if not content or content.get("visibility") != "club" or not content.get("club_id"):
        return None
    from repositories.clubs_repo import ClubsRepository

    club = ClubsRepository().get_club(str(content["club_id"]))
    owner = club.get("owner_user_id") if club else None
    return str(owner) if owner else None


@router.post("/content/resolve")
async def resolve_content(
    body: ResolveContentRequest,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """Resolve URL to content metadata and upsert into catalog. Returns content row with content_id."""
    try:
        service = get_resolve_service()
        row = service.resolve(body.url)
        content_id = str(row.get("content_id") or row.get("id") or "")
        if content_id:
            repo = get_content_repo()
            repo.claim_content_owner(content_id, str(user_id))
            refreshed = repo.get_content_by_id(content_id)
            if refreshed:
                refreshed["content_id"] = content_id
                return refreshed
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
    if not is_admin(user_id) and not repo.can_access_content(str(user_id), body.content_id):
        from repositories.explore_repo import _youtube_video_id
        from services.explore_config import catalog_video_ids, explore_config_loader
        video_id = _youtube_video_id(content) if content.get("provider") == "youtube" else None
        if video_id and video_id in catalog_video_ids(explore_config_loader.load()):
            repo.make_curated_video_public(body.content_id)
        if not repo.can_access_content(str(user_id), body.content_id):
            raise HTTPException(status_code=403, detail="This content is not shared with you")
    repo.claim_content_owner(body.content_id, str(user_id))
    uc_id = repo.add_user_content(str(user_id), body.content_id)
    return {"user_content_id": uc_id, "status": "saved"}


@router.post("/content/{content_id}/share")
async def share_content(content_id: str, body: ShareContentRequest,
                        user_id: int = Depends(get_current_user)) -> Dict[str, Any]:
    """Share a Library item by link or explicitly publish it to Explore."""
    from repositories.explore_repo import ExploreRepository
    from services.explore_config import explore_config_loader

    try:
        result = ExploreRepository().share_library_content(
            content_id, str(user_id), body.destination, body.language, body.level)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.destination == "explore":
        explore_config_loader.invalidate()
    return result


@router.post("/content/{content_id}/share/club")
async def share_content_to_club(content_id: str, body: ClubContentShareRequest,
                                user_id: int = Depends(get_current_user)) -> Dict[str, Any]:
    """Post to one of the user's clubs and add the item to its shared shelf."""
    from services.content_share_service import share_content_with_club

    try:
        return await share_content_with_club(content_id, body.club_id, str(user_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/club-shared-content")
async def get_club_shared_content(club_id: Optional[str] = None, q: Optional[str] = None,
                                  offset: int = 0, limit: int = 30,
                                  user_id: int = Depends(get_current_user)) -> Dict[str, Any]:
    from repositories.content_share_repo import ContentShareRepository

    safe_offset = max(0, offset)
    safe_limit = max(1, min(limit, 100))
    rows = ContentShareRepository().list_for_member(str(user_id), club_id=club_id,
                                                    q=q, limit=safe_limit + 1, offset=safe_offset)
    return {"items": rows[:safe_limit],
            "next_offset": safe_offset + safe_limit if len(rows) > safe_limit else None}


@router.delete("/content/{content_id}/share/club/{club_id}")
async def remove_club_content_share(content_id: str, club_id: str,
                                    user_id: int = Depends(get_current_user)) -> Dict[str, str]:
    from repositories.content_share_repo import ContentShareRepository

    if not ContentShareRepository().remove_club_share(content_id, club_id, str(user_id)):
        raise HTTPException(status_code=404, detail="Club share not found or not removable")
    return {"status": "removed"}


@router.get("/my-contents")
async def get_my_contents(
    status: Optional[str] = None,
    q: Optional[str] = None,
    content_type: Optional[str] = None,
    language: Optional[str] = None,
    sort: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = 20,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """Paginated list of user's content with content + user_content + rollup buckets."""
    repo = get_content_repo()
    safe_limit = max(1, min(int(limit or 20), 100))
    resolved_status = None if status in (None, "", "all") else status
    resolved_type = None if content_type in (None, "", "all") else content_type
    resolved_language = None if language in (None, "", "all") else language
    if resolved_language and resolved_language != "unknown" and not re.fullmatch(r"[A-Za-z]{2,3}", resolved_language):
        raise HTTPException(status_code=400, detail="Invalid language filter")
    rows = repo.get_user_contents(
        str(user_id),
        status=resolved_status,
        cursor=cursor,
        limit=safe_limit + 1,
        q=q,
        content_type=resolved_type,
        language=resolved_language,
        sort=sort,
    )
    has_next = len(rows) > safe_limit
    visible_rows = rows[:safe_limit]
    # Normalize for JSON: ensure buckets is list, metadata_json is dict
    items: List[Dict[str, Any]] = []
    for r in visible_rows:
        item = dict(r)
        if "buckets" in item and item["buckets"] is not None:
            b = item["buckets"]
            item["buckets"] = b if isinstance(b, list) else []
        if "metadata_json" in item and item["metadata_json"] is not None:
            m = item["metadata_json"]
            item["metadata_json"] = m if isinstance(m, dict) else {}
        level, item["description"] = separate_level(
            item.get("description"), (item.get("metadata_json") or {}).get("level"))
        if level:
            item["metadata_json"] = {**(item.get("metadata_json") or {}), "level": level}
        items.append(item)
    # Older curated videos carried an estimated CEFR level at the start of
    # their Explore subtitle. Show the same level as a Library badge.
    if any(item.get("provider") == "youtube" for item in items):
        from repositories.explore_repo import _youtube_video_id
        from services.explore_config import catalog_video_levels, explore_config_loader
        levels = catalog_video_levels(explore_config_loader.load())
        for item in items:
            video_id = _youtube_video_id(item) if item.get("provider") == "youtube" else None
            if video_id and video_id in levels:
                item["metadata_json"] = {**(item.get("metadata_json") or {}), "level":
                                         (item.get("metadata_json") or {}).get("level") or levels[video_id]}
    next_cursor = None
    if has_next and visible_rows:
        current_offset = 0
        if cursor and cursor.startswith("offset:"):
            try:
                current_offset = max(0, int(cursor.split(":", 1)[1]))
            except (TypeError, ValueError):
                current_offset = 0
        next_cursor = f"offset:{current_offset + len(visible_rows)}"
    return {
        "items": items,
        "count": len(items),
        "next_cursor": next_cursor,
        "facets": repo.get_user_content_facets(str(user_id), q=q, status=resolved_status),
    }


@router.post("/user-content/{content_id}/assign")
async def assign_user_content(
    content_id: str,
    body: AssignUserContentRequest,
    request: Request,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """Link a library item to one of the authenticated user's tasks."""
    repo = get_content_repo()
    if not repo.get_user_content(str(user_id), content_id):
        raise HTTPException(status_code=404, detail="User content not found")

    from services.planner_api_adapter import PlannerAPIAdapter

    root_dir = getattr(request.app.state, "root_dir", None)
    if not root_dir:
        raise HTTPException(status_code=503, detail="Task service is unavailable")
    promise = PlannerAPIAdapter(root_dir=root_dir).get_promise(user_id, body.promise_id)
    if not promise:
        raise HTTPException(status_code=404, detail="Task not found")

    repo.assign_user_content_to_promise(str(user_id), content_id, str(body.promise_id))
    return {"content_id": content_id, "promise_id": str(body.promise_id), "assigned": True}


@router.post("/consume-event")
async def post_consume_event(
    request: Request,
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
    try:
        repo = get_content_repo()
        uc = repo.get_user_content(str(user_id), body.content_id)
        promise_id = str((uc or {}).get("assigned_promise_id") or "").strip()
        if (
            promise_id
            and body.position_unit == "ratio"
            and body.client == "web_pdf_reader_read"
            and body.end_position > body.start_position
        ):
            content = repo.get_content_by_id(body.content_id) or {}
            estimated_seconds = content.get("estimated_read_seconds") or content.get("duration_seconds")
            if estimated_seconds:
                consumed_seconds = (float(body.end_position) - float(body.start_position)) * float(estimated_seconds)
                if consumed_seconds >= 2.0:
                    from services.planner_api_adapter import PlannerAPIAdapter

                    root_dir = getattr(request.app.state, "root_dir", None)
                    if root_dir:
                        planner = PlannerAPIAdapter(root_dir=root_dir)
                        if planner.get_promise(user_id, promise_id):
                            title = content.get("title") or body.content_id
                            planner.add_action(
                                user_id=user_id,
                                promise_id=promise_id,
                                time_spent=round(consumed_seconds / 3600.0, 4),
                                notes=f"Content reading: {title}",
                            )
    except Exception as exc:
        logger.debug("consume-event promise logging skipped: %s", exc)
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


def _transcript_for_video(video_id: str, url: Optional[str] = None) -> Dict[str, Any]:
    """Read the cache or request a durable fetch; never scrape in an HTTP request."""
    from repositories.video_transcript_repo import VideoTranscriptRepository

    cached = VideoTranscriptRepository().get(video_id)
    if cached and cached.get("cues"):
        return cached

    from repositories.video_transcript_fetch_queue_repo import VideoTranscriptFetchQueueRepository
    try:
        queue = VideoTranscriptFetchQueueRepository()
        queue.enqueue(video_id)
        state = queue.fetch_state(video_id)
        if state["status"] == "completed":
            # The worker may have published captions after our first cache read.
            cached = VideoTranscriptRepository().get(video_id)
            if cached and cached.get("cues"):
                return cached
        pending = state["status"] in ("queued", "processing")
        # Expose only a stable public reason, never worker/third-party errors.
        status = "pending" if pending else (
            "unavailable" if state.get("last_error") in ("no_captions", "unavailable") else "failed")
    except ValueError:
        raise HTTPException(400, "Invalid video ID")
    except Exception:
        logger.warning("Could not queue transcript fetch for %s", video_id, exc_info=True)
        pending = False
        status = "failed"
    return {"available": False, "cues": [], "pending": pending, "status": status}


@router.get("/content/{content_id}/transcript")
async def get_youtube_transcript(
    content_id: str,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return timestamped YouTube captions for a content item, if available."""
    repo = get_content_repo()
    if not repo.get_user_content(str(user_id), content_id):
        raise HTTPException(status_code=404, detail="User content not found")
    content = repo.get_content_by_id(content_id) or {}
    if str(content.get("provider") or "").lower() != "youtube":
        return {"available": False, "cues": []}
    from utils.youtube_utils import extract_video_id
    video_id = extract_video_id(content.get("original_url") or content.get("canonical_url") or "")
    if not video_id:
        return {"available": False, "cues": []}
    return _transcript_for_video(video_id, url=content.get("original_url"))


@router.get("/youtube/{video_id}/transcript")
async def get_youtube_transcript_by_video(
    video_id: str,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return captions for a bare video id, with no content row required.

    A flashcard cites a video the learner may never have added as content, so
    the watch page needs a way to ask for a transcript by video id alone.
    """
    if len(video_id) > 20 or not all(c.isalnum() or c in "_-" for c in video_id):
        raise HTTPException(status_code=400, detail="Invalid video_id")
    return _transcript_for_video(video_id)


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


@router.get("/content/{content_id}/thumbnail")
async def get_content_thumbnail(
    content_id: str,
    user_id: int = Depends(get_current_user),
):
    """Serve the latest generated preview for content in the caller's library."""
    from services.pdf_thumbnail_service import PDF_THUMBNAIL_ASSET_TYPE

    repo = get_content_repo()
    if not repo.get_user_content(str(user_id), content_id):
        raise HTTPException(status_code=404, detail="User content not found")
    asset = repo.get_latest_content_asset(content_id, PDF_THUMBNAIL_ASSET_TYPE)
    if not asset:
        raise HTTPException(status_code=404, detail="Content thumbnail not found")

    storage_uri = str(asset.get("storage_uri") or "")
    storage = get_object_storage_service()
    if storage_uri.startswith("local://"):
        try:
            path = storage.resolve_local_storage_uri(storage_uri)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        if not path.exists():
            raise HTTPException(status_code=404, detail="Content thumbnail file missing")
        return FileResponse(path=str(path), media_type="image/jpeg")

    try:
        signed_url, _expires_at = storage.build_signed_get_url(storage_uri)
    except Exception as exc:
        logger.exception("thumbnail signed url generation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to open content thumbnail")
    return RedirectResponse(signed_url, status_code=307)


@router.get("/content/{content_id}/pdf")
async def get_pdf_content_open(
    content_id: str,
    club_id: Optional[str] = None,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Return latest PDF asset + signed URL + resume fields for a user's content item.
    """
    uid = str(user_id)
    if club_id:
        _require_club_share(content_id, club_id, uid)
    repo = get_content_repo()
    uc = repo.get_user_content(uid, content_id)
    if not uc:
        # A public or club-shared PDF may be opened from a link before the
        # recipient has explicitly saved it. Saving on first open makes that
        # link useful while preserving the existing access policy.
        if not repo.can_access_content(uid, content_id):
            raise HTTPException(status_code=404, detail="User content not found")
        repo.add_user_content(uid, content_id)
        uc = repo.get_user_content(uid, content_id)
        if not uc:
            raise HTTPException(status_code=404, detail="User content not found")

    asset = repo.get_latest_content_asset(content_id, asset_type="pdf_source")
    if not asset:
        raise HTTPException(status_code=404, detail="PDF asset not found")

    storage_uri = asset.get("storage_uri")
    if not storage_uri:
        raise HTTPException(status_code=500, detail="Invalid PDF asset storage URI")

    storage = get_object_storage_service()
    if str(storage_uri).startswith("local://"):
        pdf_url = storage.build_local_file_url(content_id=content_id, asset_id=str(asset["id"]))
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=storage.presign_ttl)).isoformat()
    else:
        try:
            pdf_url, expires_at = storage.build_signed_get_url(str(storage_uri))
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except Exception as exc:
            logger.exception("pdf signed url generation failed: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to create signed URL")

    heatmap = repo.get_heatmap(uid, content_id)
    buckets = list((heatmap or {}).get("buckets") or [])
    bucket_count = int((heatmap or {}).get("bucket_count") or len(buckets) or 0)
    read_progress_ratio = (
        min(1.0, sum(1 for b in buckets if (b or 0) > 0) / bucket_count)
        if bucket_count > 0
        else 0.0
    )

    content = repo.get_content_by_id(content_id)
    teacher_id = _club_teacher_for_content(content or {})

    return {
        "content_id": content_id,
        "asset_id": asset["id"],
        "pdf_url": pdf_url,
        "expires_at": expires_at,
        "last_position": uc.get("last_position"),
        "progress_ratio": read_progress_ratio,
        "title": (content or {}).get("title"),
        "language": (content or {}).get("language"),
        "club_id": club_id or ((content or {}).get("club_id") if teacher_id else None),
        "is_teacher": bool(teacher_id) and teacher_id == uid,
    }


@router.get("/content/{content_id}/pdf/file")
async def get_pdf_content_file(
    content_id: str,
    asset_id: Optional[str] = None,
    user_id: int = Depends(get_current_user),
):
    """
    Stream a locally stored PDF file for an owned content item.
    Used for local-storage MVP fallback when S3/object storage is unavailable.
    """
    uid = str(user_id)
    repo = get_content_repo()
    uc = repo.get_user_content(uid, content_id)
    if not uc:
        if not repo.can_access_content(uid, content_id):
            raise HTTPException(status_code=404, detail="User content not found")
        repo.add_user_content(uid, content_id)

    resolved_asset_id = asset_id
    if not resolved_asset_id:
        latest_asset = repo.get_latest_content_asset(content_id, asset_type="pdf_source")
        if not latest_asset:
            raise HTTPException(status_code=404, detail="PDF asset not found")
        resolved_asset_id = str(latest_asset["id"])

    asset = repo.get_content_asset(content_id=content_id, asset_id=str(resolved_asset_id))
    if not asset:
        raise HTTPException(status_code=404, detail="PDF asset not found")

    storage_uri = str(asset.get("storage_uri") or "")
    if not storage_uri.startswith("local://"):
        raise HTTPException(status_code=400, detail="PDF file endpoint only supports local storage")

    storage = get_object_storage_service()
    try:
        path = storage.resolve_local_storage_uri(storage_uri)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF file missing on server")

    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=f"{content_id}.pdf",
    )


@router.get("/content/{content_id}/highlights")
async def get_pdf_highlights(
    content_id: str,
    asset_id: Optional[str] = None,
    as_user_id: Optional[str] = None,
    club_id: Optional[str] = None,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """List highlights for a user/content and asset version.

    On content shared to a club, this also returns the club owner's (the
    teacher's) highlights alongside the caller's own — so a co-reading
    session or a pre-highlighted passage shows up for everyone. The teacher
    may pass `as_user_id` to look at one specific student's highlights.
    """
    uid = str(user_id)
    repo = get_content_repo()
    uc = repo.get_user_content(uid, content_id)
    if not uc:
        raise HTTPException(status_code=404, detail="User content not found")

    resolved_asset_id = asset_id
    if not resolved_asset_id:
        latest_asset = repo.get_latest_content_asset(content_id, asset_type="pdf_source")
        if not latest_asset:
            raise HTTPException(status_code=404, detail="PDF asset not found")
        resolved_asset_id = str(latest_asset["id"])

    asset = repo.get_content_asset(content_id=content_id, asset_id=str(resolved_asset_id))
    if not asset:
        raise HTTPException(status_code=404, detail="PDF asset not found")

    if club_id:
        share_repo = _require_club_share(content_id, club_id, uid)
        items = share_repo.list_club_highlights(content_id, club_id, str(resolved_asset_id), uid, as_user_id)
        return {"asset_id": str(resolved_asset_id), "items": items, "count": len(items)}

    content = repo.get_content_by_id(content_id)
    teacher_id = _club_teacher_for_content(content or {})
    try:
        items = repo.list_visible_highlights(
            viewer_user_id=uid,
            content_id=content_id,
            asset_id=str(resolved_asset_id),
            teacher_user_id=teacher_id,
            as_user_id=as_user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return {"asset_id": str(resolved_asset_id), "items": items, "count": len(items)}


@router.get("/content/{content_id}/co-readers")
async def get_content_co_readers(
    content_id: str,
    club_id: Optional[str] = None,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """Roster and reading progress for club shares or legacy class material."""
    uid = str(user_id)
    if club_id:
        share_repo = _require_club_share(content_id, club_id, uid)
        return {"items": share_repo.list_activity(content_id, club_id)}
    repo = get_content_repo()
    content = repo.get_content_by_id(content_id)
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    teacher_id = _club_teacher_for_content(content)
    if not teacher_id or teacher_id != uid:
        raise HTTPException(status_code=403, detail="Only the club owner can view the class roster")

    from repositories.clubs_repo import ClubsRepository

    members = ClubsRepository().get_members(str(content["club_id"]))
    member_ids = [str(m["user_id"]) for m in members if str(m["user_id"]) != uid]
    items = repo.list_co_readers(content_id, member_ids)
    return {"items": items}


@router.get("/content/{content_id}/club-video-annotations")
async def get_club_video_annotations(content_id: str, club_id: str,
                                     user_id: int = Depends(get_current_user)) -> Dict[str, Any]:
    repo = _require_club_share(content_id, club_id, str(user_id))
    return {"items": repo.list_video_annotations(content_id, club_id, str(user_id))}


@router.post("/content/{content_id}/club-video-annotations")
async def create_club_video_annotation(content_id: str, body: ClubVideoAnnotationRequest,
                                       user_id: int = Depends(get_current_user)) -> Dict[str, Any]:
    if not body.body.strip():
        raise HTTPException(status_code=422, detail="Annotation cannot be blank")
    repo = _require_club_share(content_id, body.club_id, str(user_id))
    from repositories.explore_repo import _youtube_video_id

    content = get_content_repo().get_content_by_id(content_id)
    if not content or content.get("provider") != "youtube" or not _youtube_video_id(content):
        raise HTTPException(status_code=400, detail="Club annotations are for videos")
    annotation_id = repo.add_video_annotation(content_id, body.club_id, str(user_id),
                                              body.position_seconds, body.body.strip())
    return {"annotation_id": annotation_id}


@router.delete("/content/{content_id}/club-video-annotations/{annotation_id}")
async def delete_club_video_annotation(content_id: str, annotation_id: str, club_id: str,
                                       user_id: int = Depends(get_current_user)) -> Dict[str, Any]:
    repo = _require_club_share(content_id, club_id, str(user_id))
    if not repo.remove_video_annotation(content_id, club_id, str(user_id), annotation_id):
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"deleted": True}


@router.post("/content/{content_id}/highlights")
async def create_pdf_highlight(
    content_id: str,
    body: CreateHighlightRequest,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """Create one PDF highlight on a given asset version."""
    uid = str(user_id)
    repo = get_content_repo()
    uc = repo.get_user_content(uid, content_id)
    if not uc:
        raise HTTPException(status_code=404, detail="User content not found")
    asset = repo.get_content_asset(content_id=content_id, asset_id=body.asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="PDF asset not found")

    highlight_id = repo.create_highlight(
        user_id=uid,
        content_id=content_id,
        asset_id=body.asset_id,
        page_index=int(body.page_index),
        rects=[r.model_dump() for r in body.rects],
        selected_text=body.selected_text,
        note=body.note,
        color=body.color,
    )
    return {"highlight_id": highlight_id, "created": True}


@router.patch("/content/{content_id}/highlights/{highlight_id}")
async def update_pdf_highlight(
    content_id: str,
    highlight_id: str,
    body: UpdateHighlightRequest,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update a PDF highlight owned by the caller."""
    uid = str(user_id)
    repo = get_content_repo()
    existing = repo.get_highlight(uid, content_id, highlight_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Highlight not found")
    updated = repo.update_highlight(
        user_id=uid,
        content_id=content_id,
        highlight_id=highlight_id,
        rects=[r.model_dump() for r in body.rects] if body.rects is not None else None,
        selected_text=body.selected_text,
        note=body.note,
        color=body.color,
        club_visible=body.club_visible,
    )
    return {"highlight_id": highlight_id, "updated": bool(updated)}


@router.delete("/content/{content_id}/highlights/{highlight_id}")
async def delete_pdf_highlight(
    content_id: str,
    highlight_id: str,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """Delete a PDF highlight owned by the caller."""
    uid = str(user_id)
    repo = get_content_repo()
    deleted = repo.delete_highlight(uid, content_id, highlight_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Highlight not found")
    return {"highlight_id": highlight_id, "deleted": True}


@router.post("/content/{content_id}/analyze")
async def analyze_content(
    content_id: str,
    body: AnalyzeContentRequest,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    service = get_learning_service()
    try:
        return service.enqueue_analysis(
            user_id=user_id,
            content_id=content_id,
            force_rebuild=bool(body.force_rebuild),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)
    except Exception as exc:
        logger.exception("enqueue analysis failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to enqueue content analysis")


@router.get("/content/jobs/{job_id}")
async def get_content_job(
    job_id: str,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    service = get_learning_service()
    try:
        return service.get_job_status(job_id, user_id=user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("get content job failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch content job")


@router.get("/content/{content_id}/summary")
async def get_content_summary(
    content_id: str,
    level: str = "global",
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    service = get_learning_service()
    try:
        return service.get_summary(content_id=content_id, user_id=user_id, level=level)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)
    except Exception as exc:
        logger.exception("get content summary failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch content summary")


@router.post("/content/{content_id}/ask")
async def ask_content_question(
    content_id: str,
    body: AskContentRequest,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    service = get_learning_service()
    try:
        return service.ask(content_id=content_id, user_id=user_id, question=body.question)
    except VectorStoreUnavailableError:
        raise HTTPException(status_code=503, detail={"message": "Vector search is temporarily unavailable", "retryable": True})
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)
    except Exception as exc:
        logger.exception("content ask failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to answer content question")


@router.post("/content/{content_id}/quiz")
async def create_content_quiz(
    content_id: str,
    body: CreateQuizRequest,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    service = get_learning_service()
    try:
        return service.create_quiz(
            content_id=content_id,
            user_id=user_id,
            difficulty=body.difficulty or "medium",
            question_count=int(body.question_count or 8),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)
    except Exception as exc:
        logger.exception("content quiz creation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create content quiz")


@router.post("/quiz/{quiz_set_id}/submit")
async def submit_content_quiz(
    quiz_set_id: str,
    body: SubmitQuizRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    service = get_learning_service()
    try:
        answers = [{"question_id": item.question_id, "answer": item.answer} for item in body.answers]
        return service.submit_quiz(
            user_id=user_id,
            quiz_set_id=quiz_set_id,
            answers=answers,
            idempotency_key=idempotency_key,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)
    except Exception as exc:
        logger.exception("content quiz submit failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to submit content quiz")


@router.get("/content/{content_id}/concepts")
async def get_content_concepts(
    content_id: str,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    service = get_learning_service()
    try:
        return service.get_concepts(content_id=content_id, user_id=user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)
    except Exception as exc:
        logger.exception("get content concepts failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch content concepts")
