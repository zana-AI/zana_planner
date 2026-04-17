"""
Community-related endpoints (suggestions, public promises, follows).
"""

from datetime import datetime
from typing import List
import asyncio
import os
import uuid

from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy import text
from ..dependencies import get_current_user
from ..schemas import (
    ClubMemberSummary,
    CreateClubRequest,
    ClubsResponse,
    ClubSummary,
    CreateSuggestionRequest,
    PublicPromiseBadge,
)
from models.models import Promise
from repositories.clubs_repo import ClubsRepository
from repositories.settings_repo import SettingsRepository
from repositories.suggestions_repo import SuggestionsRepository
from repositories.templates_repo import TemplatesRepository
from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from services.reports import ReportsService
from db.postgres_db import get_db_session, resolve_promise_uuid, utc_now_iso, date_to_iso
from ..notifications import send_club_telegram_setup_request, send_suggestion_notifications
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
        columns = session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'clubs';
            """),
        ).fetchall()
        club_columns = {row[0] for row in columns}

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
                SELECT
                    c.club_id,
                    c.name,
                    c.visibility,
                    {telegram_status_select},
                    {telegram_invite_select},
                    cm.role,
                    COALESCE(member_counts.member_count, 0) AS member_count,
                    p.current_id AS promise_id,
                    p.text AS promise_text,
                    pi.target_value AS target_count_per_week
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
                ORDER BY c.created_at_utc DESC;
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
            promise_text=str(row["promise_text"]) if row["promise_text"] else None,
            target_count_per_week=float(row["target_count_per_week"]) if row["target_count_per_week"] is not None else None,
        )
        for row in rows
    ]


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
                
                # Calculate progress percentage
                hours_promised = promise.hours_per_week
                if hours_promised > 0:
                    progress_percentage = min(100, (weekly_hours / hours_promised) * 100)
                else:
                    # For check-based promises, use total actions or count
                    progress_percentage = 0.0
                
                badges.append(
                    PublicPromiseBadge(
                        promise_id=promise.id,
                        text=promise.text.replace('_', ' '),  # Convert underscores to spaces for display
                        hours_promised=hours_promised,
                        hours_spent=total_hours,
                        weekly_hours=weekly_hours,
                        streak=streak,
                        progress_percentage=progress_percentage,
                        metric_type="hours",  # Default to hours
                        target_value=hours_promised,
                        achieved_value=weekly_hours,
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
