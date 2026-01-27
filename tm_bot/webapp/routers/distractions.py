"""
Distraction-related endpoints.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from ..dependencies import get_current_user, get_settings_repo
from ..schemas import LogDistractionRequest
from repositories.distractions_repo import DistractionsRepository
from utils.time_utils import get_week_range
from utils.logger import get_logger
from datetime import datetime

router = APIRouter(prefix="/api", tags=["distractions"])
logger = get_logger(__name__)


@router.post("/distractions")
async def log_distraction(
    request: Request,
    distraction_request: LogDistractionRequest,
    user_id: int = Depends(get_current_user)
):
    """Log a distraction event (for budget templates)."""
    try:
        from dateutil.parser import parse as parse_datetime
        
        distractions_repo = DistractionsRepository(request.app.state.root_dir)
        
        at = None
        if distraction_request.at_utc:
            try:
                at = parse_datetime(distraction_request.at_utc)
                if at.tzinfo is not None:
                    import pytz
                    settings_repo = get_settings_repo(request)
                    settings = settings_repo.get_settings(user_id)
                    user_tz = settings.timezone if settings and settings.timezone not in (None, "DEFAULT") else "UTC"
                    tz = pytz.timezone(user_tz)
                    at = at.astimezone(tz).replace(tzinfo=None)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid at_utc format")
        
        event_uuid = distractions_repo.log_distraction(
            user_id, distraction_request.category, distraction_request.minutes, at
        )
        
        return {"status": "success", "event_uuid": event_uuid, "message": "Distraction logged"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error logging distraction: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to log distraction: {str(e)}")


@router.get("/distractions/weekly")
async def get_weekly_distractions(
    request: Request,
    ref_time: Optional[str] = Query(None, description="Reference time (ISO datetime)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    user_id: int = Depends(get_current_user)
):
    """Get weekly distraction summary."""
    try:
        from dateutil.parser import parse as parse_datetime
        
        distractions_repo = DistractionsRepository(request.app.state.root_dir)
        
        if ref_time:
            try:
                ref_dt = parse_datetime(ref_time)
                if ref_dt.tzinfo is not None:
                    ref_dt = ref_dt.replace(tzinfo=None)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid ref_time format")
        else:
            ref_dt = datetime.now()
        
        week_start, week_end = get_week_range(ref_dt)
        summary = distractions_repo.get_weekly_distractions(
            user_id, week_start, week_end, category
        )
        
        return summary
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting weekly distractions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get weekly distractions: {str(e)}")
