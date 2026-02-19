"""
YouTube watch Mini App: serve watch page and accept stats report.
"""

import os
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional

from utils.logger import get_logger
from ..telegram_init_data import validate_init_data
from ..youtube_watch_stats import append_stats, format_summary_message, verify_user_token

router = APIRouter(tags=["youtube_watch"])
logger = get_logger(__name__)


def _get_html_path() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "static", "youtube_watch.html")


@router.get("/youtube-watch", response_class=HTMLResponse)
async def youtube_watch_page(request: Request, video_id: Optional[str] = None):
    """Serve the YouTube Mini App HTML (Telegram + iframe + tracking)."""
    if not video_id or not video_id.strip():
        raise HTTPException(status_code=400, detail="video_id is required")
    # Basic sanity: video_id should be alphanumeric + _ -
    if len(video_id) > 20 or not all(c.isalnum() or c in "_-" for c in video_id):
        raise HTTPException(status_code=400, detail="Invalid video_id")
    html_path = _get_html_path()
    if not os.path.isfile(html_path):
        raise HTTPException(status_code=500, detail="Mini App template not found")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(content=html)


@router.post("/api/youtube/report_stats")
async def report_stats(request: Request):
    """
    Accept stats from the Mini App (init_data + stats).
    Validate init_data, append to JSONL, send Telegram message to user.
    """
    logger.info("youtube report_stats: request received")
    try:
        body = await request.json()
    except Exception as e:
        logger.warning("youtube report_stats: request.json() failed, trying body: %s", e)
        raw = await request.body()
        try:
            import json as _json
            body = _json.loads(raw.decode("utf-8"))
        except Exception as e2:
            logger.warning("youtube report_stats: body parse failed: %s", e2)
            raise HTTPException(status_code=400, detail="Invalid JSON body")
    init_data = body.get("init_data") or ""
    user_token = body.get("user_token") or ""
    stats = body.get("stats") or {}
    if not isinstance(stats, dict):
        raise HTTPException(status_code=400, detail="stats must be an object")
    video_id = stats.get("video_id") or ""
    time_spent = float(stats.get("time_spent_seconds") or 0)
    segments = stats.get("segments") or []
    if not isinstance(segments, list):
        segments = []
    closed_via = stats.get("closed_via") or "unknown"

    logger.info(
        "youtube report_stats: video_id=%s time_spent=%.1f segments=%s closed_via=%s init_data_len=%s user_token=%s",
        video_id, time_spent, len(segments), closed_via, len(init_data), "yes" if user_token else "no",
    )

    bot_token = getattr(request.app.state, "bot_token", None)
    if not bot_token:
        logger.error("youtube report_stats: bot_token not configured")
        raise HTTPException(status_code=500, detail="Bot token not configured")
    root_dir = getattr(request.app.state, "root_dir", None)
    if not root_dir or not os.path.isdir(root_dir):
        logger.error("youtube report_stats: root_dir not set or not a dir: %s", root_dir)
        raise HTTPException(status_code=500, detail="root_dir not configured")

    valid, user_id = validate_init_data(init_data, bot_token)
    if not valid or user_id is None:
        user_id = verify_user_token(user_token, bot_token)
        if user_id is not None:
            logger.info("youtube report_stats: using user_id from user_token (init_data empty/invalid)")
        else:
            logger.warning(
                "youtube report_stats: init_data invalid and no valid user_token (valid=%s). "
                "If init_data is empty, Mini App may have been opened from inline button.",
                valid,
            )
            return JSONResponse(status_code=401, content={"error": "Invalid or expired init_data"})

    logger.info("youtube report_stats: validated user_id=%s, appending stats", user_id)
    append_stats(
        root_dir=root_dir,
        user_id=user_id,
        video_id=video_id,
        time_spent_seconds=time_spent,
        segments=segments,
        closed_via=closed_via,
    )
    summary = format_summary_message(video_id, time_spent, segments)

    try:
        from telegram import Bot
        bot = Bot(token=bot_token)
        await bot.send_message(chat_id=user_id, text=summary)
        logger.info("youtube report_stats: Telegram message sent to user_id=%s", user_id)
    except Exception as e:
        logger.warning("youtube report_stats: Failed to send Telegram message to user_id=%s: %s", user_id, e)

    return JSONResponse(content={"ok": True})
