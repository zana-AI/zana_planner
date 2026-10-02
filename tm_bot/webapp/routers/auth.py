"""
Authentication endpoints.
"""

import time
from urllib.parse import urlsplit, parse_qsl, quote
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from uuid import UUID
from pydantic import BaseModel, Field
from repositories.browser_login_repo import BrowserLoginRepository
from ..auth import validate_telegram_widget_auth, validate_telegram_init_data, extract_user_id
from ..schemas import TelegramLoginRequest, TelegramLoginResponse
from utils.dev_auth import get_dev_admin_user_id, is_dev_auth_enabled
from utils.logger import get_logger

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = get_logger(__name__)


class ClubMiniAppOpen(BaseModel):
    content_id: UUID
    club_id: UUID
    language: str = Field(default='en', pattern=r'^[a-zA-Z]{2,3}(?:-[a-zA-Z]{2})?$')


@router.post('/club-miniapp-open')
def open_club_miniapp(body: ClubMiniAppOpen, request: Request, response: Response):
    """Exchange the current Telegram Mini App identity for a reader session."""
    from repositories.content_share_repo import ContentShareRepository, content_share_path
    from repositories.content_repo import ContentRepository

    response.headers['Cache-Control'] = 'no-store'
    init_data = request.headers.get('X-Telegram-Init-Data', '')
    # A remembered browser account must never replace the current Telegram user.
    validated = validate_telegram_init_data(init_data, request.app.state.bot_token)
    try:
        user_id = extract_user_id(validated) if validated else None
    except (TypeError, ValueError):
        user_id = None
    auth_date = validated.get('auth_date') if validated else None
    if not user_id or user_id <= 0 or not auth_date or not 0 <= time.time() - auth_date <= 86400:
        raise HTTPException(401, 'Open this item inside Telegram', headers={'Cache-Control': 'no-store'})
    content_id, club_id = str(body.content_id), str(body.club_id)
    if not ContentShareRepository().is_active_member_of_share(content_id, club_id, str(user_id)):
        raise HTTPException(403, 'This item is not shared with your club')
    content = ContentRepository().get_content_by_id(content_id)
    if not content:
        raise HTTPException(404, 'Content not found')
    path = content_share_path(content, club_id)
    if not path.startswith(('/youtube-watch?', '/pdf-reader?')):
        raise HTTPException(400, 'This item has no Xaana reader')
    path += '&' + 'lang=' + quote(body.language, safe='')
    session = request.app.state.auth_session_repo.create_session(
        user_id=user_id, telegram_auth_date=auth_date, expires_in_days=1, auth_method='miniapp',
    )
    return {'path': path, 'session_token': session.session_token}


@router.get('/telegram-open')
def telegram_open(request: Request):
    """Telegram LoginUrl handoff to a same-origin reader after signed login."""
    headers = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'}
    params = request.query_params
    # Duplicate parameters can give the browser and signature validator different
    # interpretations. Accept only Telegram's documented identity fields + next.
    allowed = {'next', 'id', 'first_name', 'last_name', 'username', 'photo_url', 'auth_date', 'hash'}
    if any(key not in allowed or len(params.getlist(key)) != 1 for key in params):
        raise HTTPException(400, 'Invalid sign-in link', headers=headers)
    target = params.get('next', '')
    try:
        parts = urlsplit(target)
    except ValueError:
        raise HTTPException(400, 'Invalid reader destination', headers=headers)
    if (not target.startswith('/') or parts.scheme or parts.netloc or parts.fragment
            or parts.path not in {'/youtube-watch', '/pdf-reader'}
            or any(ord(char) < 32 or char == '\\' for char in target)):
        raise HTTPException(400, 'Invalid reader destination', headers=headers)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if any(key not in {'video_id', 'content_id', 'club_id', 'lang', 'start', 'word', 'pid'} for key, _ in query):
        raise HTTPException(400, 'Invalid reader destination', headers=headers)
    # Telegram opens the original URL without identity fields if login is declined.
    if not params.get('hash') and not any(key in params for key in {'id', 'auth_date'}):
        return RedirectResponse(target, status_code=303, headers=headers)
    data = {key: value for key, value in params.items() if key != 'next'}
    try:
        auth_date, user_id = int(data['auth_date']), int(data['id'])
    except (KeyError, ValueError):
        raise HTTPException(401, 'Invalid Telegram sign-in', headers=headers)
    if user_id <= 0 or not 0 <= time.time() - auth_date <= 300:
        raise HTTPException(401, 'Telegram sign-in expired', headers=headers)
    validated = validate_telegram_widget_auth(data, request.app.state.bot_token, max_age_seconds=300)
    if not validated:
        raise HTTPException(401, 'Invalid Telegram sign-in', headers=headers)
    session = request.app.state.auth_session_repo.create_session(
        user_id=user_id, telegram_auth_date=auth_date, auth_method='widget', expires_in_days=90,
    )
    return RedirectResponse(target + '#session_token=' + quote(session.session_token, safe=''),
                            status_code=303, headers=headers)


class BrowserLoginCode(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


class BrowserLoginConfirmation(BrowserLoginCode):
    expected_user_id: int = Field(gt=0)


@router.post("/browser-login/preview")
def preview_browser_login(body: BrowserLoginCode, response: Response):
    response.headers["Cache-Control"] = "no-store"
    account = BrowserLoginRepository().preview(body.code)
    if not account:
        raise HTTPException(401, "Sign-in link expired or already used. Request a new link with /login.")
    return account


@router.post("/browser-login/redeem", response_model=TelegramLoginResponse)
def redeem_browser_login(body: BrowserLoginConfirmation, response: Response):
    response.headers["Cache-Control"] = "no-store"
    session = BrowserLoginRepository().redeem(body.code, body.expected_user_id)
    if not session:
        raise HTTPException(401, "Sign-in link expired or already used. Request a new link with /login.")
    return session


@router.post("/dev-admin-login")
async def dev_admin_login(request: Request):
    """
    Create a browser session for a synthetic admin user.
    This endpoint is disabled unless WEBAPP_DEV_AUTH_ENABLED=1 and ENVIRONMENT is not production.
    """
    if not is_dev_auth_enabled():
        raise HTTPException(
            status_code=404,
            detail="Development admin login is not enabled"
        )

    user_id = get_dev_admin_user_id()
    auth_session_repo = request.app.state.auth_session_repo
    session = auth_session_repo.create_session(
        user_id=user_id,
        telegram_auth_date=int(time.time()),
        expires_in_days=1
    )

    return {
        "session_token": session.session_token,
        "user_id": session.user_id,
        "expires_at": session.expires_at.isoformat(),
        "is_admin": True,
    }


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
            expires_in_days=90,
            auth_method="widget",
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
