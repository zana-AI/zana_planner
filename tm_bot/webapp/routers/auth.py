"""
Authentication endpoints.
"""

import time
from fastapi import APIRouter, HTTPException, Request
from ..auth import validate_telegram_widget_auth, extract_user_id
from ..schemas import TelegramLoginRequest, TelegramLoginResponse
from utils.logger import get_logger

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = get_logger(__name__)


@router.post("/telegram-login", response_model=TelegramLoginResponse)
async def telegram_login(request: Request, login_request: TelegramLoginRequest):
    """
    Authenticate using Telegram Login Widget data.
    Validates the widget auth data and returns a session token.
    """
    try:
        auth_data = login_request.auth_data
        
        # Validate widget auth data
        validated = validate_telegram_widget_auth(
            auth_data,
            request.app.state.bot_token
        )
        
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
        
        # Get auth_date from original auth_data
        telegram_auth_date = auth_data.get("auth_date", 0)
        try:
            telegram_auth_date = int(telegram_auth_date)
        except (ValueError, TypeError):
            telegram_auth_date = int(time.time())
        
        # Create auth session
        auth_session_repo = request.app.state.auth_session_repo
        session = auth_session_repo.create_session(
            user_id=user_id,
            telegram_auth_date=telegram_auth_date,
            expires_in_days=7
        )
        
        return TelegramLoginResponse(
            session_token=session.session_token,
            user_id=session.user_id,
            expires_at=session.expires_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in telegram login: {e}")
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


@router.get("/bot-username")
async def get_bot_username_endpoint(request: Request):
    """
    Get bot username for Login Widget configuration (public endpoint).
    """
    bot_username = request.app.state.bot_username
    if not bot_username or not bot_username.strip():
        logger.warning("Bot username endpoint called but username not available")
        raise HTTPException(
            status_code=503,
            detail="Bot username not available. Please check TELEGRAM_BOT_USERNAME environment variable or bot token configuration."
        )
    return {"bot_username": bot_username.strip()}
