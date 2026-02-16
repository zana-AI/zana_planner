"""
Community-related endpoints (suggestions, public promises, follows).
"""

from typing import List
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from ..dependencies import get_current_user
from ..schemas import CreateSuggestionRequest, PublicPromiseBadge
from repositories.suggestions_repo import SuggestionsRepository
from repositories.templates_repo import TemplatesRepository
from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from services.reports import ReportsService
from ..notifications import send_suggestion_notifications
from utils.logger import get_logger
import asyncio

router = APIRouter(prefix="/api", tags=["community"])
logger = get_logger(__name__)


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
