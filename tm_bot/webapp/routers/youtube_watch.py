"""YouTube viewer and authenticated, acknowledged watch-progress reports."""
import math
import os
import re
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from utils.logger import get_logger
from ..dependencies import get_current_user
from ..telegram_init_data import validate_init_data
from ..youtube_watch_stats import append_stats, verify_user_token

router = APIRouter(tags=["youtube_watch"])
logger = get_logger(__name__)


def _get_html_path():
    return os.path.join(os.path.dirname(__file__), "..", "static", "youtube_watch.html")


@router.get("/youtube-watch", response_class=HTMLResponse)
async def youtube_watch_page(request: Request, video_id: Optional[str] = None):
    if not video_id or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise HTTPException(400, "Invalid video_id")
    with open(_get_html_path(), encoding="utf-8") as stream:
        return HTMLResponse(stream.read(), headers={"Cache-Control": "no-store"})


def validate_stats(stats):
    if not isinstance(stats, dict) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", str(stats.get("video_id", ""))):
        raise HTTPException(400, "Invalid video_id")
    try:
        report_id = str(uuid.UUID(stats["report_id"])) if stats.get("report_id") else str(uuid.uuid4())
        duration = float(stats.get("duration_seconds") or 0)
        if not math.isfinite(duration) or not 0 <= duration <= 604800:
            raise ValueError()
        raw = stats.get("segments") or []
        if not isinstance(raw, list) or len(raw) > 1000:
            raise ValueError()
        segments = []
        for seg in raw:
            if not isinstance(seg, (list, tuple)) or len(seg) != 2:
                raise ValueError()
            start, end = map(float, seg)
            if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end <= 604800):
                raise ValueError()
            if duration:
                start, end = min(start, duration), min(end, duration)
            if end > start:
                segments.append([start, end])
    except (ValueError, TypeError, KeyError):
        raise HTTPException(400, "Invalid watch report")
    return report_id, segments, duration or None


async def _watch_user(request, init_data="", user_token=""):
    """Browser/Telegram auth, with compatibility for older signed watch links."""
    try:
        return await get_current_user(request, request.headers.get("X-Telegram-Init-Data"),
                                      request.headers.get("Authorization"))
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
        bot_token = request.app.state.bot_token
        valid, user_id = validate_init_data(init_data, bot_token)
        if not valid or user_id is None:
            user_id = verify_user_token(user_token, bot_token)
        if user_id is None:
            raise HTTPException(401, "Sign in to access watch progress")
        return user_id


def _watch_content(repo, video_id, content_id):
    from utils.youtube_utils import extract_video_id
    content = repo.get_content_by_id(content_id) if content_id else repo.get_content_by_canonical_url(
        f"https://www.youtube.com/watch?v={video_id}")
    if content_id and (not content or extract_video_id(content["canonical_url"]) != video_id):
        raise HTTPException(400, "Content does not match video")
    return content


@router.get("/api/youtube/{video_id}/progress")
async def watch_progress(request: Request, video_id: str, content_id: Optional[str] = None):
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise HTTPException(400, "Invalid video_id")
    user_id = await _watch_user(request, user_token=request.headers.get("X-YouTube-User-Token", ""))
    from repositories.content_repo import ContentRepository
    from repositories.youtube_progress_repo import YoutubeProgressRepository
    repo = ContentRepository()
    content = _watch_content(repo, video_id, content_id)
    if not content:
        data = {"duration_seconds": None, "segments": []}
    else:
        if not repo.can_access_content(str(user_id), content["id"]):
            raise HTTPException(403, "Content access denied")
        data = YoutubeProgressRepository().get_progress(user_id, content["id"], content.get("duration_seconds"))
    return JSONResponse(data, headers={"Cache-Control": "no-store"})


@router.post("/api/youtube/report_stats")
async def report_stats(request: Request):
    if len(await request.body()) > 60000:
        raise HTTPException(413, "Watch report too large")
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "Invalid JSON")
    if not isinstance(body, dict):
        raise HTTPException(400, "Invalid watch report")
    user_id = await _watch_user(request, body.get("init_data") or "", body.get("user_token") or "")

    stats = body.get("stats")
    report_id, segments, duration = validate_stats(stats)
    if not segments:
        return JSONResponse({"ok": True, "empty": True})
    video_id = stats["video_id"]
    from repositories.content_repo import ContentRepository
    from repositories.youtube_progress_repo import YoutubeProgressRepository
    repo = ContentRepository()
    # Update the actual Library item, including old youtu.be aliases. Never
    # refetch metadata on each heartbeat for an already-known item.
    content_id = stats.get("content_id")
    content = _watch_content(repo, video_id, content_id)
    if not content:
        from services.content_resolve_service import ContentResolveService
        content = ContentResolveService().resolve(f"https://www.youtube.com/watch?v={video_id}")
        repo.claim_content_owner(content["id"], str(user_id))
    content_id = content["id"]
    if not repo.can_access_content(str(user_id), content_id):
        raise HTTPException(403, "Content access denied")
    try:
        result = YoutubeProgressRepository().record(
            user_id, content_id, video_id, report_id, segments, duration,
            str(stats.get("promise_id") or "").strip())
    except Exception:
        logger.exception("YouTube progress save failed: video_id=%s", video_id)
        raise HTTPException(503, "Progress not saved; retry this report")
    if not result["duplicate"]:
        try:
            append_stats(root_dir=request.app.state.root_dir, user_id=user_id, video_id=video_id,
                         time_spent_seconds=sum(end-start for start, end in segments), segments=segments,
                         closed_via=str(stats.get("closed_via") or "unknown")[:40])
        except Exception:
            # The database committed; an optional audit file must not undo its acknowledgement.
            logger.warning("YouTube watch audit unavailable: video_id=%s", video_id)
    return JSONResponse(result)
