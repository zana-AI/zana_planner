"""
Plan session endpoints: Promise → PlanSessions → Checklist.
"""

from fastapi import APIRouter, HTTPException, Depends

from ..dependencies import get_current_user
from ..schemas import (
    PlanSessionIn,
    PlanSessionOut,
    PlanSessionStatusUpdate,
    PlanSessionUpdate,
    ChecklistItemToggle,
)
from repositories.plan_sessions_repo import PlanSessionsRepository
from db.postgres_db import get_db_session, resolve_promise_uuid
from utils.logger import get_logger

router = APIRouter(prefix="/api", tags=["plan_sessions"])
logger = get_logger(__name__)


def _resolve_uuid(user_id: int, promise_id: str) -> str:
    """Resolve user-facing promise_id (current_id or alias) to internal promise_uuid."""
    with get_db_session() as session:
        p_uuid = resolve_promise_uuid(session, str(user_id), promise_id)
    if not p_uuid:
        raise HTTPException(status_code=404, detail="Promise not found")
    return p_uuid


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
    user_id: int = Depends(get_current_user),
):
    p_uuid = _resolve_uuid(user_id, promise_id)
    return PlanSessionsRepository().create(p_uuid, user_id, body.model_dump())


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
    user_id: int = Depends(get_current_user),
):
    result = PlanSessionsRepository().update(session_id, user_id, body.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(status_code=404, detail="Session not found")
    return result
