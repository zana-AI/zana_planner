"""
Community-related endpoints (suggestions, public promises, follows).
"""

from datetime import datetime
from typing import List
import asyncio
import os
import uuid

import httpx

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy import text
from ..dependencies import get_current_user
from ..schemas import (
    AddClubPromiseRequest,
    ClubActionResponse,
    ClubMemberSummary,
    CreateClubRequest,
    ClubsResponse,
    ClubSummary,
    CreateSuggestionRequest,
    PublicPromiseBadge,
    UpdateClubPromiseRequest,
    UpdateClubSettingsRequest,
)
from models.models import Promise
from repositories.clubs_repo import ClubsRepository, ensure_club_telegram_columns, get_club_columns
from repositories.settings_repo import SettingsRepository
from repositories.suggestions_repo import SuggestionsRepository
from repositories.templates_repo import TemplatesRepository
from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from services.reports import ReportsService
from db.postgres_db import get_db_session, resolve_promise_uuid, utc_now_iso, date_to_iso
from ..notifications import (
    send_club_pending_notification,
    send_club_telegram_setup_request,
    send_suggestion_notifications,
)
from utils.logger import get_logger

router = APIRouter(prefix="/api", tags=["community"])
logger = get_logger(__name__)


def _generate_club_promise_id(user_id: int) -> str:
    promises = PromisesRepository().list_promises(user_id)
    numbers = []
    for promise in promises:
        pid = (promise.id or "").upper()
        if not pid.startswith("C"):
            continue
        try:
            numbers.append(int(pid[1:]))
        except ValueError:
            continue
    return f"C{(max(numbers) if numbers else 0) + 1:02d}"


def _ensure_user_exists(user_id: int) -> None:
    settings_repo = SettingsRepository()
    settings = settings_repo.get_settings(user_id)
    settings_repo.save_settings(settings)


def _create_club_promise(
    user_id: int,
    club_id: str,
    club_name: str,
    promise_text: str,
    target_count_per_week: float,
) -> tuple[str, str]:
    user = str(user_id)
    promise_id = _generate_club_promise_id(user_id)
    now = utc_now_iso()
    today = datetime.now().date()

    template_id = TemplatesRepository().create_template({
        "title": promise_text.strip(),
        "description": f"Shared promise for {club_name}",
        "category": "club",
        "target_value": target_count_per_week,
        "metric_type": "count",
        "emoji": None,
        "is_active": False,
        "created_by_user_id": user,
    })

    promise = Promise(
        user_id=user,
        id=promise_id,
        text=promise_text.strip(),
        hours_per_week=0.0,
        recurring=True,
        start_date=today,
        visibility="clubs",
        description=f"Shared with club: {club_name}",
    )
    PromisesRepository().upsert_promise(user_id, promise)

    with get_db_session() as session:
        promise_uuid = resolve_promise_uuid(session, user, promise_id)
        if not promise_uuid:
            raise RuntimeError("Failed to resolve club promise")

        session.execute(
            text("""
                INSERT INTO promise_instances (
                    instance_id, user_id, template_id, promise_uuid, status,
                    metric_type, target_value, estimated_hours_per_unit,
                    start_date, end_date, created_at_utc, updated_at_utc
                ) VALUES (
                    :instance_id, :user_id, :template_id, :promise_uuid, 'active',
                    'count', :target_value, 1.0,
                    :start_date, NULL, :now, :now
                );
            """),
            {
                "instance_id": str(uuid.uuid4()),
                "user_id": user,
                "template_id": template_id,
                "promise_uuid": promise_uuid,
                "target_value": float(target_count_per_week),
                "start_date": date_to_iso(today),
                "now": now,
            },
        )

    ClubsRepository().share_promise_to_club(promise_uuid, club_id)
    return promise_id, promise_uuid


def _list_user_clubs(user_id: int) -> List[ClubSummary]:
    user = str(user_id)
    with get_db_session() as session:
        ensure_club_telegram_columns(session)
        club_columns = get_club_columns(session)

        telegram_status_select = (
            "c.telegram_status"
            if "telegram_status" in club_columns
            else "'not_connected' AS telegram_status"
        )
        telegram_invite_select = (
            "c.telegram_invite_link"
            if "telegram_invite_link" in club_columns
            else "CAST(NULL AS TEXT) AS telegram_invite_link"
        )

        rows = session.execute(
            text(f"""
                SELECT DISTINCT ON (c.club_id)
                    c.club_id,
                    c.name,
                    c.visibility,
                    {telegram_status_select},
                    {telegram_invite_select},
                    cm.role,
                    COALESCE(member_counts.member_count, 0) AS member_count,
                    p.current_id AS promise_id,
                    p.promise_uuid AS promise_uuid,
                    p.text AS promise_text,
                    pi.target_value AS target_count_per_week,
                    c.reminder_time,
                    c.language
                FROM clubs c
                INNER JOIN club_members cm
                    ON cm.club_id = c.club_id
                   AND cm.user_id = :user_id
                   AND cm.status = 'active'
                LEFT JOIN (
                    SELECT club_id, COUNT(*) AS member_count
                    FROM club_members
                    WHERE status = 'active'
                    GROUP BY club_id
                ) member_counts ON member_counts.club_id = c.club_id
                LEFT JOIN promise_club_shares pcs ON pcs.club_id = c.club_id
                LEFT JOIN promises p
                    ON p.promise_uuid = pcs.promise_uuid
                   AND p.is_deleted = 0
                LEFT JOIN promise_instances pi
                    ON pi.promise_uuid = p.promise_uuid
                   AND pi.user_id = p.user_id
                   AND pi.status = 'active'
                WHERE COALESCE(c.status, 'active') = 'active'
                ORDER BY c.club_id, pcs.created_at_utc ASC;
            """),
            {"user_id": user},
        ).mappings().fetchall()

        club_ids = [str(row["club_id"]) for row in rows]
        member_rows = []
        if club_ids:
            member_rows = session.execute(
                text("""
                    SELECT
                        cm.club_id,
                        cm.user_id,
                        u.first_name,
                        u.username,
                        u.avatar_path
                    FROM club_members cm
                    LEFT JOIN users u ON u.user_id = cm.user_id
                    WHERE cm.status = 'active'
                      AND cm.club_id = ANY(:club_ids)
                    ORDER BY cm.joined_at_utc ASC;
                """),
                {"club_ids": club_ids},
            ).mappings().fetchall()

    members_by_club: dict[str, List[ClubMemberSummary]] = {}
    for member in member_rows:
        club_id = str(member["club_id"])
        members_by_club.setdefault(club_id, []).append(
            ClubMemberSummary(
                user_id=str(member["user_id"]),
                first_name=str(member["first_name"]) if member["first_name"] else None,
                username=str(member["username"]) if member["username"] else None,
                avatar_path=str(member["avatar_path"]) if member["avatar_path"] else None,
            )
        )

    return [
        ClubSummary(
            club_id=str(row["club_id"]),
            name=str(row["name"]),
            visibility=str(row["visibility"] or "private"),
            role=str(row["role"] or "member"),
            member_count=int(row["member_count"] or 0),
            members=members_by_club.get(str(row["club_id"]), []),
            telegram_status=str(row["telegram_status"] or "not_connected"),
            telegram_invite_link=str(row["telegram_invite_link"]) if row["telegram_invite_link"] else None,
            promise_id=str(row["promise_id"]) if row["promise_id"] else None,
            promise_uuid=str(row["promise_uuid"]) if row["promise_uuid"] else None,
            promise_text=str(row["promise_text"]) if row["promise_text"] else None,
            target_count_per_week=float(row["target_count_per_week"]) if row["target_count_per_week"] is not None else None,
            reminder_time=str(row["reminder_time"]) if row["reminder_time"] else None,
            language=str(row["language"]) if row["language"] else None,
        )
        for row in rows
    ]


async def _is_club_admin(user_id: int, club: dict, bot_token: str) -> bool:
    """Return True if user is the club owner, or a Telegram group admin."""
    if str(club.get("owner_user_id")) == str(user_id):
        return True
    telegram_chat_id = club.get("telegram_chat_id")
    if not telegram_chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getChatAdministrators"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params={"chat_id": telegram_chat_id})
        if resp.status_code == 200:
            admins = resp.json().get("result", [])
            admin_ids = {str(m["user"]["id"]) for m in admins}
            return str(user_id) in admin_ids
    except Exception:
        pass
    return False


@router.get("/clubs", response_model=ClubsResponse)
async def list_my_clubs(user_id: int = Depends(get_current_user)):
    """List clubs where the current user is an active member."""
    try:
        clubs = _list_user_clubs(user_id)
        return ClubsResponse(clubs=clubs, total=len(clubs))
    except Exception as e:
        logger.exception(f"Error listing clubs for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load clubs: {str(e)}")


@router.post("/clubs", response_model=ClubSummary)
async def create_club(
    request: Request,
    club_request: CreateClubRequest,
    user_id: int = Depends(get_current_user),
):
    """Create a minimal Xaana club with one shared count-based promise."""
    try:
        _ensure_user_exists(user_id)
        name = club_request.name.strip()
        promise_text = club_request.promise_text.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Club name is required")
        if not promise_text:
            raise HTTPException(status_code=400, detail="Shared promise is required")

        clubs_repo = ClubsRepository()
        club_id = clubs_repo.create_club(
            owner_user_id=user_id,
            name=name,
            description=None,
            visibility=club_request.visibility,
        )
        _create_club_promise(
            user_id=user_id,
            club_id=club_id,
            club_name=name,
            promise_text=promise_text,
            target_count_per_week=club_request.target_count_per_week,
        )
        asyncio.create_task(
            send_club_telegram_setup_request(
                bot_token=request.app.state.bot_token,
                club_id=club_id,
                club_name=name,
                creator_user_id=user_id,
                promise_text=promise_text,
                miniapp_url=os.getenv("MINIAPP_URL", "https://xaana.club"),
            )
        )
        asyncio.create_task(
            send_club_pending_notification(
                bot_token=request.app.state.bot_token,
                user_id=user_id,
                club_id=club_id,
                club_name=name,
            )
        )
        clubs = _list_user_clubs(user_id)
        created = next((club for club in clubs if club.club_id == club_id), None)
        if not created:
            raise RuntimeError("Club was created but could not be loaded")
        return created
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating club for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create club: {str(e)}")


@router.put("/clubs/{club_id}", response_model=ClubSummary)
async def update_club_settings(
    request: Request,
    club_id: str,
    body: UpdateClubSettingsRequest,
    user_id: int = Depends(get_current_user),
):
    """Update club settings (reminder_time, language). Only club admins may call this."""
    try:
        clubs_repo = ClubsRepository()
        club = clubs_repo.get_club(club_id)
        if not club or str(club.get("status") or "active") != "active":
            raise HTTPException(status_code=404, detail="Club not found")

        if not await _is_club_admin(user_id, club, request.app.state.bot_token):
            raise HTTPException(status_code=403, detail="Only club admins can update club settings")

        updates: dict = {}
        if body.reminder_time is not None:
            updates["reminder_time"] = body.reminder_time
        if body.language is not None:
            updates["language"] = body.language

        if updates:
            now = utc_now_iso()
            set_clause = ", ".join(f"{k} = :{k}" for k in updates)
            updates["club_id"] = club_id
            updates["updated_at_utc"] = now
            with get_db_session() as session:
                session.execute(
                    text(f"UPDATE clubs SET {set_clause}, updated_at_utc = :updated_at_utc WHERE club_id = :club_id;"),
                    updates,
                )

        clubs = _list_user_clubs(user_id)
        updated = next((c for c in clubs if c.club_id == club_id), None)
        if not updated:
            raise RuntimeError("Club updated but could not be reloaded")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating club settings {club_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update club: {str(e)}")


@router.post("/clubs/{club_id}/promises", response_model=ClubSummary)
async def add_club_promise(
    request: Request,
    club_id: str,
    body: AddClubPromiseRequest,
    user_id: int = Depends(get_current_user),
):
    """Add a club-level promise. Only the club owner or a Telegram group admin may do this."""
    try:
        clubs_repo = ClubsRepository()
        club = clubs_repo.get_club(club_id)
        if not club or str(club.get("status") or "active") != "active":
            raise HTTPException(status_code=404, detail="Club not found")

        if not await _is_club_admin(user_id, club, request.app.state.bot_token):
            raise HTTPException(status_code=403, detail="Only club admins can define club promises")

        promise_text = body.promise_text.strip()
        if not promise_text:
            raise HTTPException(status_code=400, detail="Promise text is required")

        _ensure_user_exists(user_id)
        _create_club_promise(
            user_id=user_id,
            club_id=club_id,
            club_name=str(club["name"]),
            promise_text=promise_text,
            target_count_per_week=body.target_count_per_week,
        )

        clubs = _list_user_clubs(user_id)
        updated = next((c for c in clubs if c.club_id == club_id), None)
        if not updated:
            raise RuntimeError("Club promise created but club could not be reloaded")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error adding promise to club {club_id} for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add club promise: {str(e)}")


@router.put("/clubs/{club_id}/promises/{promise_uuid}", response_model=ClubSummary)
async def update_club_promise(
    request: Request,
    club_id: str,
    promise_uuid: str,
    body: UpdateClubPromiseRequest,
    user_id: int = Depends(get_current_user),
):
    """Edit a club-level promise. Only the club owner or a Telegram group admin may do this."""
    try:
        clubs_repo = ClubsRepository()
        club = clubs_repo.get_club(club_id)
        if not club or str(club.get("status") or "active") != "active":
            raise HTTPException(status_code=404, detail="Club not found")

        if not await _is_club_admin(user_id, club, request.app.state.bot_token):
            raise HTTPException(status_code=403, detail="Only club admins can edit club promises")

        now = utc_now_iso()
        with get_db_session() as session:
            # Verify the promise is actually shared to this club
            shared = session.execute(
                text("SELECT 1 FROM promise_club_shares WHERE promise_uuid = :uuid AND club_id = :club_id LIMIT 1;"),
                {"uuid": promise_uuid, "club_id": club_id},
            ).fetchone()
            if not shared:
                raise HTTPException(status_code=404, detail="Promise not found in this club")

            if body.promise_text is not None:
                session.execute(
                    text("UPDATE promises SET text = :text, updated_at_utc = :now WHERE promise_uuid = :uuid;"),
                    {"text": body.promise_text.strip(), "now": now, "uuid": promise_uuid},
                )
            if body.target_count_per_week is not None:
                session.execute(
                    text("UPDATE promise_instances SET target_value = :val, updated_at_utc = :now WHERE promise_uuid = :uuid AND status = 'active';"),
                    {"val": float(body.target_count_per_week), "now": now, "uuid": promise_uuid},
                )

        clubs = _list_user_clubs(user_id)
        updated = next((c for c in clubs if c.club_id == club_id), None)
        if not updated:
            raise RuntimeError("Club promise updated but club could not be reloaded")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating promise {promise_uuid} in club {club_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update club promise: {str(e)}")


@router.delete("/clubs/{club_id}/promises/{promise_uuid}", response_model=ClubActionResponse)
async def delete_club_promise(
    request: Request,
    club_id: str,
    promise_uuid: str,
    user_id: int = Depends(get_current_user),
):
    """Delete a club-level promise. Only the club owner or a Telegram group admin may do this."""
    try:
        clubs_repo = ClubsRepository()
        club = clubs_repo.get_club(club_id)
        if not club or str(club.get("status") or "active") != "active":
            raise HTTPException(status_code=404, detail="Club not found")

        if not await _is_club_admin(user_id, club, request.app.state.bot_token):
            raise HTTPException(status_code=403, detail="Only club admins can delete club promises")

        now = utc_now_iso()
        with get_db_session() as session:
            shared = session.execute(
                text("SELECT 1 FROM promise_club_shares WHERE promise_uuid = :uuid AND club_id = :club_id LIMIT 1;"),
                {"uuid": promise_uuid, "club_id": club_id},
            ).fetchone()
            if not shared:
                raise HTTPException(status_code=404, detail="Promise not found in this club")

            session.execute(
                text("DELETE FROM promise_club_shares WHERE promise_uuid = :uuid AND club_id = :club_id;"),
                {"uuid": promise_uuid, "club_id": club_id},
            )
            session.execute(
                text("UPDATE promises SET is_deleted = 1, updated_at_utc = :now WHERE promise_uuid = :uuid;"),
                {"now": now, "uuid": promise_uuid},
            )

        return ClubActionResponse(status="deleted", club_id=club_id, message="Club promise deleted.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting promise {promise_uuid} from club {club_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete club promise: {str(e)}")


@router.post("/clubs/{club_id}/sync-description", response_model=ClubActionResponse)
async def sync_club_description(
    request: Request,
    club_id: str,
    user_id: int = Depends(get_current_user),
):
    """Push current club promise + reminder as the Telegram group description."""
    try:
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        club = ClubsRepository().get_club(club_id)
        if not club:
            raise HTTPException(status_code=404, detail="Club not found")

        if not await _is_club_admin(user_id, club, bot_token):
            raise HTTPException(status_code=403, detail="Only club admins can update the group description")

        chat_id = club.get("telegram_chat_id")
        if not chat_id:
            raise HTTPException(status_code=400, detail="No Telegram group connected to this club")

        # Build description
        parts = []
        promise_text = club.get("promise_text") or ""
        if not promise_text:
            # Fetch from promise_club_shares
            with get_db_session() as session:
                row = session.execute(
                    text("""
                        SELECT p.text, pi.target_value
                        FROM promise_club_shares pcs
                        JOIN promises p ON p.promise_uuid = pcs.promise_uuid AND p.is_deleted = 0
                        LEFT JOIN promise_instances pi ON pi.promise_uuid = p.promise_uuid AND pi.status = 'active'
                        WHERE pcs.club_id = :club_id
                        LIMIT 1
                    """),
                    {"club_id": club_id},
                ).fetchone()
                if row:
                    promise_text = row["text"] or ""
                    target = row["target_value"]
                    if promise_text:
                        parts.append(f"{promise_text}{f' · {int(target)}×/week' if target else ''}")
        else:
            parts.append(promise_text)

        reminder = club.get("reminder_time") or "21:00"
        parts.append(f"Reminder: {reminder}")
        description = " | ".join(parts)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/setChatDescription",
                json={"chat_id": chat_id, "description": description},
                timeout=10,
            )
        if not resp.is_success or not resp.json().get("ok"):
            detail = resp.json().get("description", "Failed to update group description")
            raise HTTPException(status_code=502, detail=detail)

        return ClubActionResponse(status="updated", club_id=club_id, message="Group description updated.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error syncing description for club {club_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clubs/{club_id}", response_model=ClubActionResponse)
async def remove_my_club(
    club_id: str,
    user_id: int = Depends(get_current_user),
):
    """Cancel a pending owner-created club, or leave a club as a non-owner."""
    try:
        clubs_repo = ClubsRepository()
        club = clubs_repo.get_club(club_id)
        if not club or str(club.get("status") or "active") != "active":
            raise HTTPException(status_code=404, detail="Club not found")

        with get_db_session() as session:
            member_row = session.execute(
                text("""
                    SELECT role
                    FROM club_members
                    WHERE club_id = :club_id
                      AND user_id = :user_id
                      AND status = 'active'
                    LIMIT 1;
                """),
                {"club_id": club_id, "user_id": str(user_id)},
            ).mappings().fetchone()

        if not member_row:
            raise HTTPException(status_code=404, detail="Club not found")

        if str(club.get("owner_user_id")) == str(user_id):
            if str(club.get("telegram_status") or "") != "pending_admin_setup":
                raise HTTPException(status_code=409, detail="Active clubs cannot be cancelled yet.")
            if not clubs_repo.cancel_pending_club(club_id, user_id):
                raise HTTPException(status_code=409, detail="Club could not be cancelled.")
            return ClubActionResponse(status="cancelled", club_id=club_id, message="Club cancelled.")

        if not clubs_repo.remove_member(club_id, user_id):
            raise HTTPException(status_code=409, detail="Club could not be left.")
        return ClubActionResponse(status="left", club_id=club_id, message="You left the club.")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error removing club {club_id} for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update club: {str(e)}")


@router.post("/suggestions")
async def create_suggestion(
    request: Request,
    suggestion_request: CreateSuggestionRequest,
    user_id: int = Depends(get_current_user)
):
    """Create a promise suggestion for another user."""
    try:
        # Validate: must have either template_id or freeform_text
        if not suggestion_request.template_id and not suggestion_request.freeform_text:
            raise HTTPException(status_code=400, detail="Must provide either template_id or freeform_text")
        
        # Can't suggest to yourself
        if str(user_id) == str(suggestion_request.to_user_id):
            raise HTTPException(status_code=400, detail="Cannot suggest a promise to yourself")
        
        suggestions_repo = SuggestionsRepository()
        suggestion_id = suggestions_repo.create_suggestion(
            from_user_id=str(user_id),
            to_user_id=str(suggestion_request.to_user_id),
            template_id=suggestion_request.template_id,
            freeform_text=suggestion_request.freeform_text,
            message=suggestion_request.message
        )
        
        logger.info(f"User {user_id} created suggestion {suggestion_id} for user {suggestion_request.to_user_id}")
        
        # Get template title if template-based suggestion
        template_title = None
        if suggestion_request.template_id:
            templates_repo = TemplatesRepository()
            template = templates_repo.get_template(suggestion_request.template_id)
            if template:
                template_title = template.get("title")
        
        # Send Telegram notifications to both sender and receiver
        asyncio.create_task(
            send_suggestion_notifications(
                bot_token=request.app.state.bot_token,
                sender_id=user_id,
                receiver_id=int(suggestion_request.to_user_id),
                suggestion_id=suggestion_id,
                template_title=template_title,
                freeform_text=suggestion_request.freeform_text,
                message=suggestion_request.message,
            )
        )
        
        return {"status": "success", "suggestion_id": suggestion_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating suggestion: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create suggestion: {str(e)}")


@router.get("/suggestions/pending")
async def get_pending_suggestions(
    request: Request,
    user_id: int = Depends(get_current_user)
):
    """Get pending suggestions sent to the current user."""
    try:
        suggestions_repo = SuggestionsRepository()
        suggestions = suggestions_repo.get_pending_suggestions_for_user(str(user_id))
        
        return {"suggestions": suggestions}
    except Exception as e:
        logger.exception(f"Error getting pending suggestions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get suggestions: {str(e)}")


@router.put("/suggestions/{suggestion_id}/respond")
async def respond_to_suggestion(
    request: Request,
    suggestion_id: str,
    response: str = Query(..., regex="^(accept|decline)$"),
    user_id: int = Depends(get_current_user)
):
    """Accept or decline a suggestion."""
    try:
        suggestions_repo = SuggestionsRepository()
        
        new_status = "accepted" if response == "accept" else "declined"
        success = suggestions_repo.update_suggestion_status(
            suggestion_id=suggestion_id,
            new_status=new_status,
            user_id=str(user_id)
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Suggestion not found or not authorized")
        
        logger.info(f"User {user_id} {response}ed suggestion {suggestion_id}")
        return {"status": "success", "new_status": new_status}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error responding to suggestion: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to respond to suggestion: {str(e)}")


@router.get("/users/{user_id}/public-promises", response_model=List[PublicPromiseBadge])
async def get_public_promises(
    request: Request,
    user_id: int,
    current_user_id: int = Depends(get_current_user),
):
    """
    Get public promises for a user with stats (streak, progress, etc.).
    Authentication required.
    """
    try:
        promises_repo = PromisesRepository()
        actions_repo = ActionsRepository()
        reports_service = ReportsService(promises_repo, actions_repo)
        
        # Get all promises for the user
        all_promises = promises_repo.list_promises(user_id)
        
        # Filter to only public promises
        public_promises = [p for p in all_promises if p.visibility == "public"]
        
        # Get current time for calculations
        from datetime import datetime
        ref_time = datetime.now()
        
        # Calculate stats for each public promise
        badges = []
        for promise in public_promises:
            try:
                # Get promise summary with stats
                summary = reports_service.get_promise_summary(user_id, promise.id, ref_time)
                
                if not summary:
                    continue
                
                weekly_hours = summary.get('weekly_hours', 0.0)
                total_hours = summary.get('total_hours', 0.0)
                streak = summary.get('streak', 0)
                weekly_count = summary.get('weekly_count', 0)
                target_value = summary.get('target_value', 0)

                # Calculate progress percentage
                hours_promised = promise.hours_per_week
                if hours_promised > 0:
                    progress_percentage = min(100, (weekly_hours / hours_promised) * 100)
                elif target_value > 0:
                    # Count-based promise (e.g. check-in 3x/week)
                    progress_percentage = min(100, (weekly_count / target_value) * 100)
                else:
                    progress_percentage = 0.0
                
                is_count_based = hours_promised == 0 and target_value > 0
                badges.append(
                    PublicPromiseBadge(
                        promise_id=promise.id,
                        text=promise.text.replace('_', ' '),
                        hours_promised=hours_promised,
                        hours_spent=total_hours,
                        weekly_hours=weekly_hours,
                        streak=streak,
                        progress_percentage=progress_percentage,
                        metric_type="count" if is_count_based else "hours",
                        target_value=target_value if is_count_based else hours_promised,
                        achieved_value=weekly_count if is_count_based else weekly_hours,
                    )
                )
            except Exception as e:
                logger.warning(f"Error calculating stats for promise {promise.id}: {e}")
                continue
        
        return badges
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting public promises for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get public promises: {str(e)}")
