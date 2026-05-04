"""
Content consumption manager API: resolve URL, user library, consume events, heatmap.
"""
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import FileResponse
from ..dependencies import get_current_user
from ..schemas import (
    ResolveContentRequest,
    AddUserContentRequest,
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


@router.get("/content/{content_id}/pdf")
async def get_pdf_content_open(
    content_id: str,
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Return latest PDF asset + signed URL + resume fields for a user's content item.
    """
    uid = str(user_id)
    repo = get_content_repo()
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

    return {
        "content_id": content_id,
        "asset_id": asset["id"],
        "pdf_url": pdf_url,
        "expires_at": expires_at,
        "last_position": uc.get("last_position"),
        "progress_ratio": uc.get("progress_ratio") if uc.get("progress_ratio") is not None else 0.0,
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
    user_id: int = Depends(get_current_user),
) -> Dict[str, Any]:
    """List highlights for a user/content and asset version."""
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

    items = repo.list_highlights(uid, content_id, str(resolved_asset_id))
    return {"asset_id": str(resolved_asset_id), "items": items, "count": len(items)}


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
