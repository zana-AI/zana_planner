"""
Plan session endpoints: Promise → PlanSessions → Checklist.
"""

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy import text

from ..dependencies import get_current_user
from ..schemas import (
    PlanSessionIn,
    PlanSessionOut,
    PlanSessionStatusUpdate,
    PlanSessionUpdate,
    ChecklistItemToggle,
)
from repositories.plan_sessions_repo import PlanSessionsRepository
from repositories.settings_repo import SettingsRepository
from db.postgres_db import get_db_session, resolve_promise_uuid
from utils.logger import get_logger

router = APIRouter(prefix="/api", tags=["plan_sessions"])
logger = get_logger(__name__)


def _promise_text_for_uuid(promise_uuid: str) -> str:
    """Look up a promise's text by its internal uuid (for calendar event titles)."""
    if not promise_uuid:
        return ""
    try:
        with get_db_session() as session:
            row = session.execute(
                text("SELECT text FROM promises WHERE promise_uuid = :uuid"),
                {"uuid": promise_uuid},
            ).fetchone()
        return (row[0] if row else "") or ""
    except Exception:
        return ""


def _fire_session_saved_dm(
    request: Request,
    user_id: int,
    session_row: dict,
    is_edit: bool,
) -> None:
    """Best-effort: DM the user calendar options after they schedule/edit a session.

    Never raises — calendar delivery must not break the API response.
    """
    try:
        if not session_row or not session_row.get("planned_start"):
            return
        bot_token = getattr(request.app.state, "bot_token", None)
        if not bot_token:
            return
        promise_text = _promise_text_for_uuid(session_row.get("promise_uuid"))

        from ..notifications import send_plan_session_saved_notification

        asyncio.create_task(
            send_plan_session_saved_notification(
                bot_token=bot_token,
                user_id=user_id,
                promise_text=promise_text,
                title=session_row.get("title"),
                planned_start=session_row.get("planned_start"),
                planned_duration_min=session_row.get("planned_duration_min"),
                reminder_enabled=bool(session_row.get("reminder_enabled", True)),
                reminder_offset_min=int(session_row.get("reminder_offset_min") or 10),
                is_edit=is_edit,
            )
        )
    except Exception as e:
        logger.warning("Could not schedule session-saved DM: %s", e)


def _resolve_uuid(user_id: int, promise_id: str) -> str:
    """Resolve user-facing promise_id (current_id or alias) to internal promise_uuid."""
    with get_db_session() as session:
        p_uuid = resolve_promise_uuid(session, str(user_id), promise_id)
    if not p_uuid:
        raise HTTPException(status_code=404, detail="Promise not found")
    return p_uuid


def _user_timezone(user_id: int) -> ZoneInfo:
    try:
        settings = SettingsRepository().get_settings(user_id)
        tz_name = settings.timezone if settings and settings.timezone else "UTC"
        if tz_name == "DEFAULT" or tz_name == "DISABLED":
            tz_name = "UTC"
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def _normalize_planned_start(value: str | None, user_id: int) -> str | None:
    if not value:
        return value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid planned_start datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_user_timezone(user_id))
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _session_payload(data: dict, user_id: int) -> dict:
    if "planned_start" in data:
        data["planned_start"] = _normalize_planned_start(data.get("planned_start"), user_id)
    if data.get("reminder_offset_min") is not None:
        data["reminder_offset_min"] = int(data["reminder_offset_min"])
    return data


@router.get("/promises/{promise_id}/plan-sessions", response_model=list[PlanSessionOut])
async def list_plan_sessions(
    promise_id: str,
    user_id: int = Depends(get_current_user),
):
    p_uuid = _resolve_uuid(user_id, promise_id)
    return PlanSessionsRepository().list_for_promise(p_uuid, user_id)


@router.post("/promises/{promise_id}/plan-sessions", response_model=PlanSessionOut, status_code=201)
async def create_plan_session(
    promise_id: str,
    body: PlanSessionIn,
    request: Request,
    user_id: int = Depends(get_current_user),
):
    p_uuid = _resolve_uuid(user_id, promise_id)
    result = PlanSessionsRepository().create(p_uuid, user_id, _session_payload(body.model_dump(), user_id))
    _fire_session_saved_dm(request, user_id, result, is_edit=False)
    return result


@router.patch("/plan-sessions/{session_id}/status", response_model=PlanSessionOut)
async def update_plan_session_status(
    session_id: int,
    body: PlanSessionStatusUpdate,
    user_id: int = Depends(get_current_user),
):
    if body.status not in ("planned", "done", "skipped"):
        raise HTTPException(status_code=400, detail="status must be planned | done | skipped")
    result = PlanSessionsRepository().update_status(session_id, user_id, body.status)
    if not result:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.patch("/plan-sessions/{session_id}/checklist/{item_id}", response_model=PlanSessionOut)
async def toggle_checklist_item(
    session_id: int,
    item_id: int,
    body: ChecklistItemToggle,
    user_id: int = Depends(get_current_user),
):
    result = PlanSessionsRepository().toggle_checklist_item(item_id, session_id, user_id, body.done)
    if not result:
        raise HTTPException(status_code=404, detail="Item not found")
    return result


@router.delete("/plan-sessions/{session_id}", status_code=204)
async def delete_plan_session(
    session_id: int,
    user_id: int = Depends(get_current_user),
):
    if not PlanSessionsRepository().delete(session_id, user_id):
        raise HTTPException(status_code=404, detail="Session not found")


@router.patch("/plan-sessions/{session_id}", response_model=PlanSessionOut)
async def update_plan_session(
    session_id: int,
    body: PlanSessionUpdate,
    request: Request,
    user_id: int = Depends(get_current_user),
):
    result = PlanSessionsRepository().update(
        session_id,
        user_id,
        _session_payload(body.model_dump(exclude_none=True), user_id),
    )
    if not result:
        raise HTTPException(status_code=404, detail="Session not found")
    _fire_session_saved_dm(request, user_id, result, is_edit=True)
    return result
