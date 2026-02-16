"""
Shared dependencies for FastAPI routes.
"""

from typing import Optional
from fastapi import HTTPException, Header, Depends, Request
from webapp.auth import validate_telegram_init_data, extract_user_id
from repositories.auth_session_repo import AuthSessionRepository
from services.reports import ReportsService
from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from repositories.settings_repo import SettingsRepository
from utils.admin_utils import is_admin
from utils.logger import get_logger
from datetime import datetime

logger = get_logger(__name__)


async def get_current_user(
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
    authorization: Optional[str] = Header(None),
) -> int:
    """
    Validate Telegram auth and return user_id.
    Supports both:
    1. Session token (browser login): Authorization: Bearer <session_token>
    2. Telegram Mini App initData: X-Telegram-Init-Data or Authorization header
    """
    app = request.app
    
    # First, check for session token (browser login)
    if authorization and authorization.startswith("Bearer "):
        session_token = authorization[7:]
        auth_session_repo = app.state.auth_session_repo
        session = auth_session_repo.get_session(session_token)
        
        if session:
            return session.user_id
        # If session not found, fall through to initData check
    
    # Fall back to Telegram Mini App initData validation
    init_data = x_telegram_init_data
    
    # Also check Authorization header (Bearer <initData> or plain initData)
    if not init_data and authorization:
        if authorization.startswith("Bearer "):
            init_data = authorization[7:]
        else:
            init_data = authorization
    
    if not init_data:
        raise HTTPException(
            status_code=401,
            detail="Missing Telegram authentication data"
        )
    
    validated = validate_telegram_init_data(init_data, app.state.bot_token)
    if not validated:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired Telegram authentication"
        )
    
    user_id = extract_user_id(validated)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Could not extract user ID from authentication data"
        )
    
    return user_id


async def get_current_user_optional(
    request: Request,
    x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
    authorization: Optional[str] = Header(None),
) -> Optional[int]:
    """Optional version of get_current_user that returns None if not authenticated."""
    try:
        return await get_current_user(request, x_telegram_init_data, authorization)
    except HTTPException:
        return None


async def get_admin_user(
    request: Request,
    user_id: int = Depends(get_current_user),
) -> int:
    """
    Validate that the current user is an admin.
    Raises 403 if user is not an admin.
    """
    if not is_admin(user_id):
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )
    return user_id


def get_reports_service(request: Request, user_id: int = Depends(get_current_user)) -> ReportsService:
    """Get ReportsService instance for a user."""
    promises_repo = PromisesRepository()
    actions_repo = ActionsRepository()
    return ReportsService(promises_repo, actions_repo)


def get_settings_repo(request: Request) -> SettingsRepository:
    """Get SettingsRepository instance."""
    return SettingsRepository()


def update_user_activity(request: Request, user_id: int = Depends(get_current_user)) -> None:
    """Update user's last_seen_utc to mark them as active."""
    try:
        settings_repo = get_settings_repo(request)
        settings = settings_repo.get_settings(user_id)
        settings.last_seen = datetime.now()
        settings_repo.save_settings(settings)
    except Exception as e:
        logger.warning(f"Failed to update user activity for user {user_id}: {e}")
