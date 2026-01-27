"""
FastAPI web application for Telegram Mini App.
Provides API endpoints for the React frontend.
"""

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from webapp.auth import validate_telegram_init_data, extract_user_id, validate_telegram_widget_auth
from repositories.auth_session_repo import AuthSessionRepository
from services.reports import ReportsService
from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from repositories.settings_repo import SettingsRepository
from repositories.follows_repo import FollowsRepository
from repositories.broadcasts_repo import BroadcastsRepository
from repositories.bot_tokens_repo import BotTokensRepository
from repositories.templates_repo import TemplatesRepository
from repositories.instances_repo import InstancesRepository
from repositories.reviews_repo import ReviewsRepository
from repositories.distractions_repo import DistractionsRepository
from repositories.schedules_repo import SchedulesRepository
from repositories.reminders_repo import RemindersRepository
from services.template_unlocks import TemplateUnlocksService
from services.reminder_dispatch import ReminderDispatchService
from db.postgres_db import get_db_session, utc_now_iso, resolve_promise_uuid, date_from_iso, dt_to_utc_iso
from sqlalchemy import text
from utils.time_utils import get_week_range
from utils.logger import get_logger
from utils.admin_utils import is_admin
from fastapi.responses import FileResponse
from telegram import Bot
from telegram.error import TelegramError
from llms.llm_env_utils import load_llm_env
from langchain_google_vertexai import ChatVertexAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import json
import uuid


logger = get_logger(__name__)

# Admin stats cache (module-level)
_admin_stats_cache: Optional[Dict[str, Any]] = None
_admin_stats_cache_timestamp: Optional[datetime] = None
ADMIN_STATS_CACHE_TTL = timedelta(minutes=5)

# Pending follow-notification jobs: (follower_id, followee_id) -> job_name
# NOTE: This is in-memory; if the server restarts within the 2-minute window,
# the job will be lost and no notification will be sent (acceptable for best-effort).
_pending_follow_notification_jobs: Dict[tuple, str] = {}


async def send_follow_notification(bot_token: str, follower_id: int, followee_id: int, root_dir: str) -> None:
    """
    Send a Telegram notification to the followee when someone follows them.
    
    Args:
        bot_token: Telegram bot token
        follower_id: User ID of the person who followed
        followee_id: User ID of the person being followed
        root_dir: Root directory for accessing repositories
    """
    try:
        # Get follower's name
        settings_repo = SettingsRepository(root_dir)
        follower_settings = settings_repo.get_settings(follower_id)
        
        # Determine follower's display name
        follower_name = follower_settings.first_name or follower_settings.username or f"User {follower_id}"
        if follower_settings.username:
            follower_name = f"@{follower_settings.username}"
        elif follower_settings.first_name:
            follower_name = follower_settings.first_name
        
        # Get mini app URL for community link
        miniapp_url = os.getenv("MINIAPP_URL", "https://xaana.club")
        community_url = f"{miniapp_url}/community"
        
        # Create bot instance
        bot = Bot(token=bot_token)
        
        # Construct notification message with profile link if username exists
        if follower_settings.username:
            message = (
                f"👤 [@{follower_settings.username}](t.me/{follower_settings.username}) started following you!\n\n"
                f"See your Xaana community from here [Community]({community_url})"
            )
            parse_mode = "Markdown"
        else:
            message = (
                f"👤 {follower_name} started following you!\n\n"
                f"See your Xaana community from here [Community]({community_url})"
            )
            parse_mode = "Markdown"
        
        # Send notification
        await bot.send_message(
            chat_id=followee_id,
            text=message,
            parse_mode=parse_mode
        )
        
        logger.info(f"Sent follow notification to user {followee_id} from follower {follower_id}")
    except TelegramError as e:
        # Handle cases where user blocked bot or other Telegram errors
        error_msg = str(e).lower()
        if "blocked" in error_msg or "chat not found" in error_msg or "forbidden" in error_msg:
            logger.debug(f"Could not send follow notification to user {followee_id}: user blocked bot or chat not found")
        else:
            logger.warning(f"Error sending follow notification to user {followee_id}: {e}")
    except Exception as e:
        logger.warning(f"Unexpected error sending follow notification to user {followee_id}: {e}")


async def send_suggestion_notifications(
    bot_token: str,
    sender_id: int,
    receiver_id: int,
    suggestion_id: str,
    template_title: Optional[str],
    freeform_text: Optional[str],
    message: Optional[str],
    root_dir: str
) -> None:
    """
    Send Telegram notifications for a promise suggestion.
    
    Args:
        bot_token: Telegram bot token
        sender_id: User ID of the person who sent the suggestion
        receiver_id: User ID of the person receiving the suggestion
        suggestion_id: ID of the suggestion for callback buttons
        template_title: Title of the template if template-based suggestion
        freeform_text: Freeform text if custom suggestion
        message: Optional personal message
        root_dir: Root directory for accessing repositories
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from cbdata import encode_cb
    
    try:
        settings_repo = SettingsRepository(root_dir)
        sender_settings = settings_repo.get_settings(sender_id)
        receiver_settings = settings_repo.get_settings(receiver_id)
        
        # Get names
        sender_name = sender_settings.first_name or sender_settings.username or f"User {sender_id}"
        if sender_settings.username:
            sender_display = f"@{sender_settings.username}"
        else:
            sender_display = sender_name
            
        receiver_name = receiver_settings.first_name or receiver_settings.username or f"User {receiver_id}"
        
        # Determine what was suggested
        if template_title:
            suggestion_text = f"📋 Template: {template_title}"
        elif freeform_text:
            suggestion_text = f"✍️ {freeform_text[:100]}{'...' if len(freeform_text) > 100 else ''}"
        else:
            suggestion_text = "a promise"
        
        bot = Bot(token=bot_token)
        
        # 1. Send notification to RECEIVER with Accept/Decline buttons
        receiver_message = f"💡 {sender_display} suggested a promise for you!\n\n{suggestion_text}"
        if message:
            receiver_message += f"\n\n💬 Message: \"{message}\""
        
        # Create inline keyboard with Accept/Decline buttons
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Accept", callback_data=encode_cb("suggest_accept", sid=suggestion_id)),
                InlineKeyboardButton("❌ Decline", callback_data=encode_cb("suggest_decline", sid=suggestion_id))
            ]
        ])
        
        try:
            await bot.send_message(
                chat_id=receiver_id,
                text=receiver_message,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            logger.info(f"Sent suggestion notification to receiver {receiver_id}")
        except TelegramError as e:
            error_msg = str(e).lower()
            if "blocked" in error_msg or "chat not found" in error_msg or "forbidden" in error_msg:
                logger.debug(f"Could not send suggestion notification to receiver {receiver_id}: user blocked bot")
            else:
                logger.warning(f"Error sending suggestion notification to receiver {receiver_id}: {e}")
        
        # 2. Send confirmation to SENDER
        sender_message = f"✅ Your suggestion was sent to {receiver_name}!\n\n{suggestion_text}"
        if message:
            sender_message += f"\n\n💬 Your message: \"{message}\""
        sender_message += "\n\nThey'll be notified and can accept or decline."
        
        try:
            await bot.send_message(
                chat_id=sender_id,
                text=sender_message,
                parse_mode="Markdown"
            )
            logger.info(f"Sent suggestion confirmation to sender {sender_id}")
        except TelegramError as e:
            error_msg = str(e).lower()
            if "blocked" in error_msg or "chat not found" in error_msg or "forbidden" in error_msg:
                logger.debug(f"Could not send suggestion confirmation to sender {sender_id}: user blocked bot")
            else:
                logger.warning(f"Error sending suggestion confirmation to sender {sender_id}: {e}")
                
    except Exception as e:
        logger.warning(f"Unexpected error sending suggestion notifications: {e}")


class WeeklyReportResponse(BaseModel):
    """Response model for weekly report endpoint."""
    week_start: str
    week_end: str
    total_promised: float
    total_spent: float
    promises: Dict[str, Any]


class UserInfoResponse(BaseModel):
    """Response model for user info endpoint."""
    user_id: int
    timezone: str
    language: str
    first_name: Optional[str] = None


class PublicUser(BaseModel):
    """Public user information for community page."""
    user_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None
    username: Optional[str] = None
    avatar_path: Optional[str] = None
    avatar_file_unique_id: Optional[str] = None
    activity_count: int = 0
    promise_count: int = 0
    last_seen_utc: Optional[str] = None


class PublicUsersResponse(BaseModel):
    """Response model for public users endpoint."""
    users: List[PublicUser]
    total: int


class PublicPromiseBadge(BaseModel):
    """Public promise badge with stats."""
    promise_id: str
    text: str
    hours_promised: float
    hours_spent: float
    weekly_hours: float
    streak: int
    progress_percentage: float
    metric_type: str = "hours"  # Default to hours for now
    target_value: float = 0.0
    achieved_value: float = 0.0


class TimezoneUpdateRequest(BaseModel):
    """Request model for timezone update."""
    tz: str  # IANA timezone name (e.g., "America/New_York")
    offset_min: Optional[int] = None  # UTC offset in minutes (optional, for fallback)
    force: Optional[bool] = False  # If True, update timezone even if already set


def create_webapp_api(
    root_dir: str,
    bot_token: str,
    static_dir: Optional[str] = None
) -> FastAPI:
    """
    Create and configure the FastAPI application for the web app.
    
    Args:
        root_dir: Root directory for user data
        bot_token: Telegram bot token for auth validation
        static_dir: Optional path to static files directory (React build)
    
    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Xaana Web App",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json"
    )
    
    # CORS middleware for development and production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:3000",
            "https://web.telegram.org",
            "https://*.telegram.org",
            "https://xaana.club",
            "https://www.xaana.club",
            "http://xaana.club",  # Allow HTTP during initial setup
            "http://www.xaana.club",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Store config in app state
    app.state.root_dir = root_dir
    app.state.bot_token = bot_token
    
    # Initialize auth session repository
    auth_session_repo = AuthSessionRepository()
    app.state.auth_session_repo = auth_session_repo
    
    # Initialize bot_username (will be set in startup)
    app.state.bot_username = ""
    
    # Initialize delayed message service
    from platforms.fastapi.scheduler import FastAPIJobScheduler
    from services.delayed_message_service import DelayedMessageService
    scheduler = FastAPIJobScheduler()
    delayed_message_service = DelayedMessageService(scheduler, root_dir)
    app.state.delayed_message_service = delayed_message_service
    
    # Startup event to log registered routes and fetch bot username
    @app.on_event("startup")
    async def startup_event():
        logger.info(f"[VERSION_CHECK] v2.0 - App startup, registered routes:")
        for route in app.routes:
            if hasattr(route, 'path'):
                methods = getattr(route, 'methods', set())
                logger.info(f"[VERSION_CHECK] v2.0 - Route: {route.path} {methods}")
        
        # Get bot username from env or fetch from API
        username = os.getenv("TELEGRAM_BOT_USERNAME")
        if username:
            logger.info(f"Using bot username from env: {username}")
            app.state.bot_username = username
        else:
            # Fetch from Telegram API
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"https://api.telegram.org/bot{bot_token}/getMe",
                        timeout=10.0
                    )
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("ok"):
                            username = data["result"].get("username")
                            if username:
                                logger.info(f"Fetched bot username from API: {username}")
                                app.state.bot_username = username
                            else:
                                logger.warning("Bot username not found in API response")
                    else:
                        logger.warning(f"Failed to fetch bot username: HTTP {response.status_code}")
            except Exception as e:
                logger.warning(f"Failed to fetch bot username from API: {e}")
            
            if not app.state.bot_username:
                logger.warning("Bot username not found in env or API, Login Widget may not work")
        
        # Start background task for session cleanup
        import asyncio
        async def cleanup_task():
            while True:
                await asyncio.sleep(3600)  # Run every hour
                auth_session_repo.cleanup_expired()
        
        asyncio.create_task(cleanup_task())
        logger.info("Started auth session cleanup task")
    
    # Dependency to validate Telegram auth and get user_id
    async def get_current_user_optional(
        x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
        authorization: Optional[str] = Header(None),
    ) -> Optional[int]:
        """Optional version of get_current_user that returns None if not authenticated."""
        try:
            return await get_current_user(x_telegram_init_data, authorization)
        except HTTPException:
            return None
    
    async def get_current_user(
        x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
        authorization: Optional[str] = Header(None),
    ) -> int:
        """
        Validate Telegram auth and return user_id.
        Supports both:
        1. Session token (browser login): Authorization: Bearer <session_token>
        2. Telegram Mini App initData: X-Telegram-Init-Data or Authorization header
        """
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
    
    def get_reports_service(user_id: int) -> ReportsService:
        """Get ReportsService instance for a user."""
        promises_repo = PromisesRepository(app.state.root_dir)
        actions_repo = ActionsRepository(app.state.root_dir)
        return ReportsService(promises_repo, actions_repo, root_dir=app.state.root_dir)
    
    def get_settings_repo() -> SettingsRepository:
        """Get SettingsRepository instance."""
        return SettingsRepository(app.state.root_dir)
    
    def update_user_activity(user_id: int) -> None:
        """Update user's last_seen_utc to mark them as active."""
        try:
            settings_repo = get_settings_repo()
            settings = settings_repo.get_settings(user_id)
            from datetime import datetime
            settings.last_seen = datetime.now()
            settings_repo.save_settings(settings)
        except Exception as e:
            logger.warning(f"Failed to update user activity for user {user_id}: {e}")
    
    # Admin dependency - validates admin status
    async def get_admin_user(
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
    
    # Admin check endpoint - lightweight check for UI
    @app.get("/api/admin/check")
    async def check_admin_status(
        user_id: int = Depends(get_current_user)
    ):
        """Check if the current user is an admin."""
        return {"is_admin": is_admin(user_id)}
    
    # Admin stats endpoint - reuse existing bot_stats code
    @app.get("/api/admin/stats")
    async def get_admin_stats(
        admin_id: int = Depends(get_admin_user)
    ):
        """
        Get app statistics (admin only).
        Returns cached results for 5 minutes to reduce database load.
        """
        global _admin_stats_cache, _admin_stats_cache_timestamp
        
        now = datetime.now()
        
        # Return cached stats if still valid
        if _admin_stats_cache and _admin_stats_cache_timestamp and (now - _admin_stats_cache_timestamp) < ADMIN_STATS_CACHE_TTL:
            logger.debug("Returning cached admin stats")
            return _admin_stats_cache
        
        try:
            # Compute stats directly from PostgreSQL
            with get_db_session() as session:
                # Total users (distinct user_ids from any table)
                total_users = session.execute(
                    text("""
                        SELECT COUNT(DISTINCT user_id) 
                        FROM (
                            SELECT user_id FROM users
                            UNION
                            SELECT user_id FROM promises
                            UNION
                            SELECT user_id FROM actions
                        ) AS all_users;
                    """)
                ).scalar() or 0
                
                # Active users in last 7 days (users with actions in last 7 days)
                seven_days_ago_dt = datetime.now(timezone.utc) - timedelta(days=7)
                seven_days_ago = dt_to_utc_iso(seven_days_ago_dt) or utc_now_iso()
                active_users = session.execute(
                    text("""
                        SELECT COUNT(DISTINCT user_id)
                        FROM actions
                        WHERE at_utc >= :seven_days_ago;
                    """),
                    {"seven_days_ago": seven_days_ago}
                ).scalar() or 0
                
                # Users with promises (non-deleted)
                users_with_promises = session.execute(
                    text("""
                        SELECT COUNT(DISTINCT user_id)
                        FROM promises
                        WHERE is_deleted = 0;
                    """)
                ).scalar() or 0
            
            # Return simplified stats for admin panel
            result = {
                "total_users": int(total_users),
                "active_users": int(active_users),
                "total_promises": int(users_with_promises),  # Users with promises, not total promise count
            }
            
            # Cache the result
            _admin_stats_cache = result
            _admin_stats_cache_timestamp = now
            
            logger.info(f"Admin stats computed: {result}")
            return result
            
        except Exception as e:
            logger.exception(f"Error computing admin stats: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to compute stats: {str(e)}")
    
    @app.get("/")
    async def root():
        """Static landing page or serve React app if static_dir is set."""
        # If static_dir is set, serve the React app
        if static_dir and os.path.isdir(static_dir):
            index_path = os.path.join(static_dir, "index.html")
            if os.path.exists(index_path):
                # Prevent caching of index.html to ensure users get latest version
                response = FileResponse(index_path)
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                return response
        
        # Otherwise, serve static landing page
        from fastapi.responses import HTMLResponse
        
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Xaana - Your Personal Planning Assistant</title>
            <link rel="icon" type="image/png" href="/assets/zana_icon.png" />
            <link rel="apple-touch-icon" href="/assets/zana_icon.png" />
            <style>
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 20px;
                }
                .container {
                    background: white;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
                    padding: 60px 40px;
                    max-width: 600px;
                    width: 100%;
                    text-align: center;
                }
                h1 {
                    color: #667eea;
                    font-size: 3em;
                    margin-bottom: 20px;
                    font-weight: 700;
                }
                .subtitle {
                    color: #666;
                    font-size: 1.2em;
                    margin-bottom: 40px;
                    line-height: 1.6;
                }
                .features {
                    text-align: left;
                    margin: 40px 0;
                }
                .feature {
                    padding: 15px 0;
                    border-bottom: 1px solid #eee;
                }
                .feature:last-child {
                    border-bottom: none;
                }
                .feature-title {
                    color: #333;
                    font-size: 1.1em;
                    font-weight: 600;
                    margin-bottom: 5px;
                }
                .feature-desc {
                    color: #666;
                    font-size: 0.95em;
                }
                .status {
                    display: inline-block;
                    background: #10b981;
                    color: white;
                    padding: 8px 20px;
                    border-radius: 20px;
                    font-size: 0.9em;
                    margin-top: 30px;
                }
                .links {
                    margin-top: 40px;
                    display: flex;
                    gap: 15px;
                    justify-content: center;
                    flex-wrap: wrap;
                }
                .link {
                    color: #667eea;
                    text-decoration: none;
                    padding: 10px 20px;
                    border: 2px solid #667eea;
                    border-radius: 8px;
                    transition: all 0.3s;
                }
                .link:hover {
                    background: #667eea;
                    color: white;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>✨ Xaana</h1>
                <p class="subtitle">Your intelligent planning and productivity assistant</p>
                
                <div class="features">
                    <div class="feature">
                        <div class="feature-title">📅 Smart Planning</div>
                        <div class="feature-desc">Plan your time effectively with AI-powered assistance</div>
                    </div>
                    <div class="feature">
                        <div class="feature-title">📊 Weekly Reports</div>
                        <div class="feature-desc">Track your progress and stay accountable</div>
                    </div>
                    <div class="feature">
                        <div class="feature-title">🤖 AI-Powered</div>
                        <div class="feature-desc">Get personalized recommendations and insights</div>
                    </div>
                </div>
                
                <div class="status">🟢 Server Running</div>
                
                <div class="links">
                    <a href="https://t.me/zana_planner_bot" class="link" target="_blank" rel="noopener noreferrer">
                        💬 Open in Telegram
                    </a>
                </div>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    
    @app.get("/api/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "zana-webapp"}
    
    # Authentication endpoints
    class TelegramLoginRequest(BaseModel):
        """Request model for Telegram Login Widget authentication."""
        auth_data: Dict[str, Any]
    
    class TelegramLoginResponse(BaseModel):
        """Response model for Telegram login."""
        session_token: str
        user_id: int
        expires_at: str
    
    @app.post("/api/auth/telegram-login", response_model=TelegramLoginResponse)
    async def telegram_login(request: TelegramLoginRequest):
        """
        Authenticate using Telegram Login Widget data.
        Validates the widget auth data and returns a session token.
        """
        try:
            auth_data = request.auth_data
            
            # Validate widget auth data
            validated = validate_telegram_widget_auth(
                auth_data,
                app.state.bot_token
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
            auth_session_repo = app.state.auth_session_repo
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
    
    @app.get("/api/auth/bot-username")
    async def get_bot_username_endpoint():
        """
        Get bot username for Login Widget configuration (public endpoint).
        """
        bot_username = app.state.bot_username
        if not bot_username or not bot_username.strip():
            logger.warning("Bot username endpoint called but username not available")
            raise HTTPException(
                status_code=503,
                detail="Bot username not available. Please check TELEGRAM_BOT_USERNAME environment variable or bot token configuration."
            )
        return {"bot_username": bot_username.strip()}
    
    @app.get("/api/weekly", response_model=WeeklyReportResponse)
    async def get_weekly_report(
        user_id: int = Depends(get_current_user),
        ref_time: Optional[str] = None
    ):
        """
        Get weekly report for the authenticated user.
        
        Args:
            ref_time: Optional ISO format datetime string for reference time.
                     Defaults to current time in user's timezone.
        """
        try:
            # Get user timezone (fall back to UTC if not set or is DEFAULT placeholder)
            settings_repo = get_settings_repo()
            settings = settings_repo.get_settings(user_id)
            user_tz = settings.timezone if settings and settings.timezone not in (None, "DEFAULT") else "UTC"
            
            # Parse reference time or use current time
            if ref_time:
                try:
                    reference_time = datetime.fromisoformat(ref_time)
                    # If timezone-aware, convert to naive datetime in user's timezone
                    if reference_time.tzinfo is not None:
                        import pytz
                        user_tz_obj = pytz.timezone(user_tz)
                        # Convert to user timezone, then make naive
                        reference_time = reference_time.astimezone(user_tz_obj).replace(tzinfo=None)
                    logger.debug(f"[DEBUG] Parsed ref_time: {ref_time} -> {reference_time} (user_tz: {user_tz})")
                except ValueError as e:
                    logger.error(f"[ERROR] Invalid ref_time format: {ref_time}, error: {e}")
                    raise HTTPException(status_code=400, detail=f"Invalid ref_time format: {ref_time}")
            else:
                import pytz
                tz = pytz.timezone(user_tz)
                reference_time = datetime.now(tz).replace(tzinfo=None)  # Make naive
                logger.debug(f"[DEBUG] Using current time as ref_time: {reference_time} (user_tz: {user_tz})")
            
            # Get weekly summary
            reports_service = get_reports_service(user_id)
            logger.debug(f"[DEBUG] Getting weekly summary for user {user_id}, ref_time: {reference_time}")
            summary = reports_service.get_weekly_summary_with_sessions(user_id, reference_time)
            logger.debug(f"[DEBUG] Weekly summary result: {len(summary)} promises, keys: {list(summary.keys())}")
            
            # Calculate week range
            week_start, week_end = get_week_range(reference_time)
            # For display, week_end should be Sunday (6 days after Monday), not next Monday
            week_end_display = week_start + timedelta(days=6)  # Sunday
            
            # Calculate totals
            total_promised = 0.0
            total_spent = 0.0
            for data in summary.values():
                total_promised += float(data.get("hours_promised", 0) or 0)
                total_spent += float(data.get("hours_spent", 0) or 0)
            
            # Convert dates in sessions to ISO format strings
            formatted_summary = {}
            for pid, data in summary.items():
                formatted_data = dict(data)
                if "sessions" in formatted_data:
                    formatted_data["sessions"] = [
                        {
                            "date": s["date"].isoformat() if hasattr(s["date"], "isoformat") else str(s["date"]),
                            "hours": s["hours"]
                        }
                        for s in formatted_data["sessions"]
                    ]
                formatted_summary[pid] = formatted_data
            
            return WeeklyReportResponse(
                week_start=week_start.date().isoformat(),  # Send as date-only string (YYYY-MM-DD)
                week_end=week_end_display.date().isoformat(),  # Send as date-only string (YYYY-MM-DD)
                total_promised=round(total_promised, 2),
                total_spent=round(total_spent, 2),
                promises=formatted_summary
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error getting weekly report for user {user_id}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/user", response_model=UserInfoResponse)
    async def get_user_info(user_id: int = Depends(get_current_user)):
        """Get user settings/info for the authenticated user."""
        try:
            settings_repo = get_settings_repo()
            settings = settings_repo.get_settings(user_id)
            
            return UserInfoResponse(
                user_id=user_id,
                timezone=settings.timezone if settings else "UTC",
                language=settings.language if settings else "en",
                first_name=settings.first_name if settings else None
            )
        except Exception as e:
            logger.exception(f"Error getting user info for user {user_id}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/api/user/timezone")
    async def update_user_timezone(
        request: TimezoneUpdateRequest,
        user_id: int = Depends(get_current_user)
    ):
        """
        Update user timezone.
        Automatically called by Mini App on load to detect and set timezone.
        Only updates if user hasn't set a timezone yet, or if explicitly updating.
        """
        try:
            # Update user's last_seen_utc - user is active (opening Mini App)
            update_user_activity(user_id)
            
            from zoneinfo import ZoneInfo
            
            # Validate timezone
            try:
                ZoneInfo(request.tz)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid timezone: {request.tz}. Error: {str(e)}"
                )
            
            settings_repo = get_settings_repo()
            settings = settings_repo.get_settings(user_id)
            
            # Only update if timezone is not set (defaults to "DEFAULT")
            # or if explicitly updating with force=True
            current_tz = settings.timezone if settings else None
            default_tzs = ["DEFAULT"]
            
            if request.force:
                # Force update - update immediately
                if not settings:
                    from models.models import UserSettings
                    settings = UserSettings(user_id=str(user_id))
                
                settings.timezone = request.tz
                settings_repo.save_settings(settings)
                
                logger.info(f"Updated timezone for user {user_id} to {request.tz} (forced)")
                
                return {
                    "status": "success",
                    "message": f"Timezone updated to {request.tz}",
                    "timezone": request.tz
                }
            elif not current_tz or current_tz in default_tzs:
                # Timezone is DEFAULT - queue delayed message instead of updating immediately
                # Cancel any existing pending timezone messages for this user
                delayed_service = app.state.delayed_message_service
                delayed_service.cancel_pending(user_id)
                
                # Queue message to be sent after 2 minutes of inactivity
                async def send_timezone_message():
                    """Send timezone confirmation message to user."""
                    try:
                        # Get user settings for language
                        user_settings = settings_repo.get_settings(user_id)
                        user_lang = user_settings.language if user_settings else "en"
                        
                        # Get message translations
                        from handlers.messages_store import get_message, Language
                        lang_map = {"en": Language.EN, "fa": Language.FA, "fr": Language.FR}
                        lang = lang_map.get(user_lang, Language.EN)
                        
                        prompt_msg = get_message("timezone_detected_prompt", lang, timezone=request.tz)
                        use_btn = get_message("timezone_confirm_use_detected", lang, timezone=request.tz)
                        not_now_btn = get_message("timezone_confirm_not_now", lang)
                        choose_btn = get_message("timezone_confirm_choose_different", lang)
                        
                        # Create inline keyboard
                        from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
                        from cbdata import encode_cb
                        
                        # Get mini app URL
                        miniapp_url = os.getenv("MINIAPP_URL", "https://xaana.club")
                        timezone_url = f"{miniapp_url}/timezone"
                        
                        keyboard = InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton(use_btn, callback_data=encode_cb("tz_confirm", tz=request.tz)),
                                InlineKeyboardButton(not_now_btn, callback_data=encode_cb("tz_not_now"))
                            ],
                            [
                                InlineKeyboardButton(choose_btn, web_app=WebAppInfo(url=timezone_url))
                            ]
                        ])
                        
                        # Send message
                        bot = Bot(token=app.state.bot_token)
                        await bot.send_message(
                            chat_id=user_id,
                            text=prompt_msg,
                            reply_markup=keyboard,
                            parse_mode=None
                        )
                        
                        logger.info(f"Sent timezone confirmation message to user {user_id}")
                    except TelegramError as e:
                        error_msg = str(e).lower()
                        if "blocked" in error_msg or "chat not found" in error_msg or "forbidden" in error_msg:
                            logger.debug(f"Could not send timezone message to user {user_id}: user blocked bot")
                        else:
                            logger.warning(f"Error sending timezone message to user {user_id}: {e}")
                    except Exception as e:
                        logger.error(f"Unexpected error sending timezone message to user {user_id}: {e}", exc_info=True)
                
                # Queue the message
                message_id = f"timezone_{user_id}_{int(datetime.now().timestamp())}"
                delayed_service.queue_message(
                    user_id=user_id,
                    message_func=send_timezone_message,
                    delay_minutes=2,
                    message_id=message_id
                )
                
                logger.info(f"Queued timezone confirmation message for user {user_id}, will send in 2 minutes if inactive")
                
                return {
                    "status": "queued",
                    "message": "Timezone confirmation message queued",
                    "timezone": request.tz
                }
            else:
                # Timezone already set, return current timezone
                return {
                    "status": "unchanged",
                    "message": f"Timezone already set to {current_tz}",
                    "timezone": current_tz
                }
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error updating timezone for user {user_id}")
            raise HTTPException(status_code=500, detail=f"Failed to update timezone: {str(e)}")
    
    @app.get("/api/public/users", response_model=PublicUsersResponse)
    async def get_public_users(
        limit: int = Query(default=20, ge=1, le=100),
        user_id: int = Depends(get_current_user),
    ):
        """
        Get public list of most active users (authenticated only).
        
        Args:
            limit: Maximum number of users to return (1-100, default: 20)
        
        Returns:
            List of public user information ranked by activity
        """
        try:
            # IMPORTANT: Use the Postgres-backed DB (SQLAlchemy session) so counts and avatars
            # match followers/following + user detail pages.
            from datetime import datetime, timedelta, timezone
            from db.postgres_db import get_db_session
            from sqlalchemy import text

            since_utc = (
                (datetime.now(timezone.utc) - timedelta(days=30))
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )

            with get_db_session() as session:
                rows = session.execute(
                    text("""
                        SELECT 
                            u.user_id,
                            u.first_name,
                            u.last_name,
                            u.display_name,
                            u.username,
                            u.avatar_path,
                            u.avatar_file_unique_id,
                            u.last_seen_utc,
                            COALESCE(activity.activity_count, 0) as activity_count,
                            COALESCE(promise_counts.promise_count, 0) as promise_count
                        FROM users u
                        LEFT JOIN (
                            SELECT user_id, COUNT(*) as activity_count
                            FROM actions 
                            WHERE at_utc >= :since_utc
                            GROUP BY user_id
                        ) activity ON u.user_id = activity.user_id
                        LEFT JOIN (
                            SELECT user_id, COUNT(*) as promise_count
                            FROM promises
                            WHERE is_deleted = 0
                            GROUP BY user_id
                        ) promise_counts ON u.user_id = promise_counts.user_id
                        WHERE (u.avatar_visibility = 'public' OR u.avatar_visibility IS NULL)
                        ORDER BY activity_count DESC, u.last_seen_utc DESC NULLS LAST
                        LIMIT :limit;
                    """),
                    {"since_utc": since_utc, "limit": int(limit)},
                ).mappings().fetchall()

            users: List[PublicUser] = []
            for r in rows:
                users.append(
                    PublicUser(
                        user_id=str(r.get("user_id")),
                        first_name=r.get("first_name"),
                        last_name=r.get("last_name"),
                        display_name=r.get("display_name"),
                        username=r.get("username"),
                        avatar_path=r.get("avatar_path"),
                        avatar_file_unique_id=r.get("avatar_file_unique_id"),
                        activity_count=int(r.get("activity_count") or 0),
                        promise_count=int(r.get("promise_count") or 0),
                        last_seen_utc=r.get("last_seen_utc"),
                    )
                )

            return PublicUsersResponse(users=users, total=len(users))
                
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error getting public users: {e}")
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"Full traceback: {error_trace}")
            # Return a simpler error message for production
            raise HTTPException(status_code=500, detail=f"Failed to fetch users: {str(e)}")
    
    @app.get("/api/media/avatars/{user_id}")
    async def get_user_avatar(
        user_id: str,
        current_user_id: int = Depends(get_current_user),
    ):
        """
        Serve user avatar image.
        
        Args:
            user_id: User ID (string)
        
        Returns:
            Avatar image file or 404 if not found/not visible (auth required)
        """
        try:
            root_dir = app.state.root_dir
            if not root_dir:
                raise HTTPException(status_code=500, detail="Server configuration error: root_dir not set")

            # IMPORTANT: Use Postgres-backed DB (not legacy SQLite)
            from db.postgres_db import get_db_session
            from sqlalchemy import text

            with get_db_session() as session:
                row = session.execute(
                    text("""
                        SELECT avatar_path, avatar_visibility
                        FROM users
                        WHERE user_id = :user_id
                        LIMIT 1;
                    """),
                    {"user_id": str(user_id)},
                ).mappings().fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="User not found")

            # Check visibility (default to 'public' if not set)
            visibility = row.get("avatar_visibility") or "public"
            if visibility != "public":
                raise HTTPException(status_code=403, detail="Avatar is private")

            avatar_path = row.get("avatar_path")
            
            # If avatar_path is not in database, try standard location
            if not avatar_path:
                # Try standard avatar location: media/avatars/{user_id}.jpg
                standard_path = os.path.join("media", "avatars", f"{user_id}.jpg")
                full_path = os.path.join(root_dir, standard_path)
                # If file doesn't exist at standard location, return 404
                if not os.path.exists(full_path):
                    raise HTTPException(status_code=404, detail="Avatar not found")
            else:
                # Resolve full path from database
                # If path is relative, it's relative to root_dir
                if os.path.isabs(avatar_path):
                    full_path = avatar_path
                else:
                    full_path = os.path.join(root_dir, avatar_path)
            
            # Normalize path separators
            full_path = os.path.normpath(full_path)
            
            # Security check: ensure path is within root_dir
            root_dir_abs = os.path.abspath(root_dir)
            full_path_abs = os.path.abspath(full_path)
            if not full_path_abs.startswith(root_dir_abs):
                logger.warning(f"Attempted access outside root_dir: {full_path}")
                raise HTTPException(status_code=403, detail="Invalid path")
            
            if not os.path.exists(full_path):
                raise HTTPException(status_code=404, detail="Avatar file not found")
            
            # Determine content type from file extension
            content_type = "image/jpeg"  # Default
            if full_path.lower().endswith(".png"):
                content_type = "image/png"
            elif full_path.lower().endswith(".gif"):
                content_type = "image/gif"
            
            return FileResponse(
                full_path,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
                }
            )
                
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error serving avatar for user {user_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to serve avatar: {str(e)}")
    
    # Follow endpoints
    @app.post("/api/users/{target_user_id}/follow")
    async def follow_user(
        target_user_id: int,
        user_id: int = Depends(get_current_user)
    ):
        """Follow a user."""
        try:
            if user_id == target_user_id:
                raise HTTPException(status_code=400, detail="Cannot follow yourself")
            
            follows_repo = FollowsRepository(app.state.root_dir)
            success = follows_repo.follow(user_id, target_user_id)

            # Schedule follow notification after 2 minutes (cancellable if unfollow happens).
            # IMPORTANT: This should NOT depend on the followee's inactivity.
            if success:
                notification_key = (user_id, target_user_id)
                job_name = f"follow-notif-{user_id}-{target_user_id}"

                # Cancel any existing pending job for this relationship
                existing_job = _pending_follow_notification_jobs.get(notification_key)
                try:
                    if existing_job and getattr(app.state, "delayed_message_service", None):
                        app.state.delayed_message_service.scheduler.cancel_job(existing_job)
                except Exception as e:
                    logger.warning(f"Failed to cancel existing follow notification job {existing_job}: {e}")

                from datetime import datetime, timedelta, timezone

                async def send_follow_notification_if_still_following(context=None):
                    current_follows_repo = FollowsRepository(app.state.root_dir)
                    if not current_follows_repo.is_following(user_id, target_user_id):
                        logger.info(
                            f"Follow notification cancelled: user {user_id} unfollowed {target_user_id} before notification"
                        )
                        _pending_follow_notification_jobs.pop(notification_key, None)
                        return
                    await send_follow_notification(
                        app.state.bot_token,
                        user_id,
                        target_user_id,
                        app.state.root_dir,
                    )
                    _pending_follow_notification_jobs.pop(notification_key, None)

                when_dt = datetime.now(timezone.utc) + timedelta(minutes=2)

                try:
                    if getattr(app.state, "delayed_message_service", None):
                        app.state.delayed_message_service.scheduler.schedule_once(
                            name=job_name,
                            callback=send_follow_notification_if_still_following,
                            when_dt=when_dt,
                            data={"user_id": target_user_id, "follower_id": user_id, "followee_id": target_user_id},
                        )
                        _pending_follow_notification_jobs[notification_key] = job_name
                        logger.info(
                            f"Scheduled follow notification job {job_name} for user {target_user_id} (2-minute delay)"
                        )
                    else:
                        raise RuntimeError("No delayed_message_service available")
                except Exception as e:
                    # Fallback: send immediately
                    logger.warning(f"Failed to schedule delayed follow notification, sending immediate: {e}")
                    import asyncio

                    asyncio.create_task(
                        send_follow_notification(
                            app.state.bot_token,
                            user_id,
                            target_user_id,
                            app.state.root_dir,
                        )
                    )

                return {"status": "success", "message": "User followed successfully"}
            else:
                return {"status": "success", "message": "Already following this user"}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception(f"Error following user {target_user_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to follow user: {str(e)}")
    
    @app.delete("/api/users/{target_user_id}/follow")
    async def unfollow_user(
        target_user_id: int,
        user_id: int = Depends(get_current_user)
    ):
        """Unfollow a user."""
        try:
            follows_repo = FollowsRepository(app.state.root_dir)
            success = follows_repo.unfollow(user_id, target_user_id)
            
            if success:
                # Cancel pending follow notification if exists
                notification_key = (user_id, target_user_id)
                job_name = _pending_follow_notification_jobs.pop(notification_key, None)
                if job_name and getattr(app.state, "delayed_message_service", None):
                    try:
                        app.state.delayed_message_service.scheduler.cancel_job(job_name)
                        logger.info(
                            f"Cancelled pending follow notification job {job_name} for user {target_user_id} from follower {user_id}"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to cancel follow notification job {job_name}: {e}")

                return {"status": "success", "message": "User unfollowed successfully"}
            else:
                return {"status": "success", "message": "Not following this user"}
        except Exception as e:
            logger.exception(f"Error unfollowing user {target_user_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to unfollow user: {str(e)}")
    
    @app.get("/api/users/{user_id}", response_model=PublicUser)
    async def get_user(
        user_id: int,
        current_user_id: int = Depends(get_current_user)
    ):
        """Get public user information by ID."""
        try:
            settings_repo = SettingsRepository(app.state.root_dir)
            follows_repo = FollowsRepository(app.state.root_dir)
            
            # Get user settings
            settings = settings_repo.get_settings(user_id)
            if not settings:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Get activity count
            from db.postgres_db import get_db_session
            from sqlalchemy import text
            with get_db_session() as session:
                from datetime import datetime, timedelta, timezone
                since_utc = (
                    (datetime.now(timezone.utc) - timedelta(days=30))
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z")
                )
                activity_row = session.execute(
                    text("""
                        SELECT COUNT(*) as activity_count
                        FROM actions 
                        WHERE user_id = :user_id AND at_utc >= :since_utc
                    """),
                    {"user_id": str(user_id), "since_utc": since_utc}
                ).mappings().fetchone()
                activity_count = int(activity_row["activity_count"] or 0) if activity_row else 0
                
                promise_row = session.execute(
                    text("""
                        SELECT COUNT(*) as promise_count
                        FROM promises
                        WHERE user_id = :user_id AND is_deleted = 0
                    """),
                    {"user_id": str(user_id)}
                ).mappings().fetchone()
                promise_count = int(promise_row["promise_count"] or 0) if promise_row else 0
                
                # Get avatar path if available
                avatar_row = session.execute(
                    text("""
                        SELECT avatar_path, avatar_file_unique_id
                        FROM users
                        WHERE user_id = :user_id
                    """),
                    {"user_id": str(user_id)}
                ).mappings().fetchone()
                avatar_path = avatar_row.get("avatar_path") if avatar_row else None
                avatar_file_unique_id = avatar_row.get("avatar_file_unique_id") if avatar_row else None
                
                # Get public promises using the existing service
                from repositories.promises_repo import PromisesRepository
                from repositories.actions_repo import ActionsRepository
                from services.reports import ReportsService
                from datetime import datetime
                
                promises_repo = PromisesRepository(app.state.root_dir)
                actions_repo = ActionsRepository(app.state.root_dir)
                reports_service = ReportsService(promises_repo, actions_repo, root_dir=app.state.root_dir)
                
                # Get all promises for the user
                all_promises = promises_repo.list_promises(user_id)
                
                # Filter to only public promises
                public_promise_list = [p for p in all_promises if p.visibility == "public"]
                
                # Get current time for calculations
                ref_time = datetime.now()
                
                # Calculate stats for each public promise
                public_promises = []
                for promise in public_promise_list:
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
                            progress_percentage = 0.0
                        
                        # Get metric_type and target_value from template if available
                        metric_type = "hours"
                        target_value = hours_promised
                        with get_db_session() as template_session:
                            template_row = template_session.execute(
                                text("""
                                    SELECT pt.metric_type, pt.target_value
                                    FROM promise_instances pi
                                    JOIN promise_templates pt ON pi.template_id = pt.template_id
                                    WHERE pi.promise_uuid = :promise_uuid
                                    LIMIT 1
                                """),
                                {"promise_uuid": promise.promise_uuid}
                            ).mappings().fetchone()
                            if template_row:
                                metric_type = template_row.get("metric_type") or "hours"
                                target_value = float(template_row.get("target_value") or hours_promised)
                        
                        public_promises.append({
                            "promise_id": promise.id,
                            "text": promise.text.replace('_', ' '),
                            "hours_promised": hours_promised,
                            "hours_spent": total_hours,
                            "weekly_hours": weekly_hours,
                            "streak": streak,
                            "progress_percentage": progress_percentage,
                            "metric_type": metric_type,
                            "target_value": target_value,
                            "achieved_value": weekly_hours if metric_type == "hours" else summary.get('achieved_value', 0.0)
                        })
                    except Exception as e:
                        logger.warning(f"Error calculating stats for promise {promise.id}: {e}")
                        continue
            
            return PublicUser(
                user_id=str(user_id),
                first_name=settings.first_name,
                username=settings.username,
                display_name=None,
                avatar_path=avatar_path,
                avatar_file_unique_id=avatar_file_unique_id,
                activity_count=activity_count,
                promise_count=promise_count,
                last_seen_utc=settings.last_seen.isoformat() if settings.last_seen else None,
                public_promises=public_promises
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error getting user {user_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get user: {str(e)}")
    
    @app.get("/api/users/{target_user_id}/follow-status")
    async def get_follow_status(
        target_user_id: int,
        user_id: int = Depends(get_current_user)
    ):
        """Check if current user is following target user."""
        try:
            follows_repo = FollowsRepository(app.state.root_dir)
            is_following = follows_repo.is_following(user_id, target_user_id)
            
            return {"is_following": is_following}
        except Exception as e:
            logger.exception(f"Error getting follow status for user {target_user_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get follow status: {str(e)}")
    
    @app.get("/api/users/{user_id}/followers", response_model=PublicUsersResponse)
    async def get_followers(
        user_id: int,
        current_user_id: int = Depends(get_current_user)
    ):
        """Get list of users that follow the specified user."""
        try:
            # Only allow viewing your own followers or if viewing another user's (for future expansion)
            if user_id != current_user_id:
                # For now, only allow viewing own followers
                raise HTTPException(status_code=403, detail="Can only view your own followers")
            
            follows_repo = FollowsRepository(app.state.root_dir)
            settings_repo = SettingsRepository(app.state.root_dir)
            
            # Get follower user IDs
            follower_ids = follows_repo.get_followers(user_id)
            
            # Enrich with user info
            users = []
            for follower_id_str in follower_ids:
                try:
                    follower_id = int(follower_id_str)
                    settings = settings_repo.get_settings(follower_id)
                    
                    # Get activity count (simplified - could be optimized)
                    with get_db_session() as session:
                        from datetime import datetime, timedelta, timezone
                        since_utc = (
                            (datetime.now(timezone.utc) - timedelta(days=30))
                            .replace(microsecond=0)
                            .isoformat()
                            .replace("+00:00", "Z")
                        )
                        activity_row = session.execute(
                            text("""
                                SELECT COUNT(*) as activity_count
                                FROM actions 
                                WHERE user_id = :user_id AND at_utc >= :since_utc
                            """),
                            {"user_id": follower_id_str, "since_utc": since_utc}
                        ).mappings().fetchone()
                        activity_count = int(activity_row["activity_count"] or 0) if activity_row else 0
                        
                        promise_row = session.execute(
                            text("""
                                SELECT COUNT(*) as promise_count
                                FROM promises
                                WHERE user_id = :user_id AND is_deleted = 0
                            """),
                            {"user_id": follower_id_str}
                        ).mappings().fetchone()
                        promise_count = int(promise_row["promise_count"] or 0) if promise_row else 0
                    
                    # Get avatar path if available
                    avatar_path = None
                    avatar_file_unique_id = None
                    with get_db_session() as session:
                        avatar_row = session.execute(
                            text("""
                                SELECT avatar_path, avatar_file_unique_id
                                FROM users
                                WHERE user_id = :user_id
                            """),
                            {"user_id": follower_id_str}
                        ).mappings().fetchone()
                        if avatar_row:
                            avatar_path = avatar_row.get("avatar_path")
                            avatar_file_unique_id = avatar_row.get("avatar_file_unique_id")
                    
                    users.append(
                        PublicUser(
                            user_id=follower_id_str,
                            first_name=settings.first_name,
                            username=settings.username,
                            display_name=None,
                            last_name=None,
                            avatar_path=avatar_path,
                            avatar_file_unique_id=avatar_file_unique_id,
                            activity_count=activity_count,
                            promise_count=promise_count,
                            last_seen_utc=None,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Error enriching follower {follower_id_str}: {e}")
                    continue
            
            return PublicUsersResponse(users=users, total=len(users))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error getting followers for user {user_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get followers: {str(e)}")
    
    @app.get("/api/users/{user_id}/following", response_model=PublicUsersResponse)
    async def get_following(
        user_id: int,
        current_user_id: int = Depends(get_current_user)
    ):
        """Get list of users that the specified user follows."""
        try:
            # Only allow viewing your own following list
            if user_id != current_user_id:
                raise HTTPException(status_code=403, detail="Can only view your own following list")
            
            follows_repo = FollowsRepository(app.state.root_dir)
            settings_repo = SettingsRepository(app.state.root_dir)
            
            # Get following user IDs
            following_ids = follows_repo.get_following(user_id)
            
            # Enrich with user info
            users = []
            for following_id_str in following_ids:
                try:
                    following_id = int(following_id_str)
                    settings = settings_repo.get_settings(following_id)
                    
                    # Get activity count
                    from db.postgres_db import get_db_session
                    from sqlalchemy import text
                    with get_db_session() as session:
                        from datetime import datetime, timedelta, timezone
                        since_utc = (
                            (datetime.now(timezone.utc) - timedelta(days=30))
                            .replace(microsecond=0)
                            .isoformat()
                            .replace("+00:00", "Z")
                        )
                        activity_row = session.execute(
                            text("""
                                SELECT COUNT(*) as activity_count
                                FROM actions 
                                WHERE user_id = :user_id AND at_utc >= :since_utc
                            """),
                            {"user_id": following_id_str, "since_utc": since_utc}
                        ).mappings().fetchone()
                        activity_count = int(activity_row["activity_count"] or 0) if activity_row else 0
                        
                        promise_row = session.execute(
                            text("""
                                SELECT COUNT(*) as promise_count
                                FROM promises
                                WHERE user_id = :user_id AND is_deleted = 0
                            """),
                            {"user_id": following_id_str}
                        ).mappings().fetchone()
                        promise_count = int(promise_row["promise_count"] or 0) if promise_row else 0
                    
                    # Get avatar path if available
                    avatar_path = None
                    avatar_file_unique_id = None
                    with get_db_session() as session:
                        avatar_row = session.execute(
                            text("""
                                SELECT avatar_path, avatar_file_unique_id
                                FROM users
                                WHERE user_id = :user_id
                            """),
                            {"user_id": following_id_str}
                        ).mappings().fetchone()
                        if avatar_row:
                            avatar_path = avatar_row.get("avatar_path")
                            avatar_file_unique_id = avatar_row.get("avatar_file_unique_id")
                    
                    users.append(
                        PublicUser(
                            user_id=following_id_str,
                            first_name=settings.first_name,
                            username=settings.username,
                            display_name=None,
                            last_name=None,
                            avatar_path=avatar_path,
                            avatar_file_unique_id=avatar_file_unique_id,
                            activity_count=activity_count,
                            promise_count=promise_count,
                            last_seen_utc=None,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Error enriching following {following_id_str}: {e}")
                    continue
            
            return PublicUsersResponse(users=users, total=len(users))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error getting following for user {user_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get following: {str(e)}")
    
    # Promise Suggestions endpoints
    class CreateSuggestionRequest(BaseModel):
        to_user_id: str
        template_id: Optional[str] = None
        freeform_text: Optional[str] = None
        message: Optional[str] = None
    
    @app.post("/api/suggestions")
    async def create_suggestion(
        request: CreateSuggestionRequest,
        user_id: int = Depends(get_current_user)
    ):
        """Create a promise suggestion for another user."""
        try:
            from repositories.suggestions_repo import SuggestionsRepository
            
            # Validate: must have either template_id or freeform_text
            if not request.template_id and not request.freeform_text:
                raise HTTPException(status_code=400, detail="Must provide either template_id or freeform_text")
            
            # Can't suggest to yourself
            if str(user_id) == str(request.to_user_id):
                raise HTTPException(status_code=400, detail="Cannot suggest a promise to yourself")
            
            suggestions_repo = SuggestionsRepository(app.state.root_dir)
            suggestion_id = suggestions_repo.create_suggestion(
                from_user_id=str(user_id),
                to_user_id=str(request.to_user_id),
                template_id=request.template_id,
                freeform_text=request.freeform_text,
                message=request.message
            )
            
            logger.info(f"User {user_id} created suggestion {suggestion_id} for user {request.to_user_id}")
            
            # Get template title if template-based suggestion
            template_title = None
            if request.template_id:
                templates_repo = TemplatesRepository(app.state.root_dir)
                template = templates_repo.get_template(request.template_id)
                if template:
                    template_title = template.get("title")
            
            # Send Telegram notifications to both sender and receiver
            import asyncio
            asyncio.create_task(
                send_suggestion_notifications(
                    bot_token=app.state.bot_token,
                    sender_id=user_id,
                    receiver_id=int(request.to_user_id),
                    suggestion_id=suggestion_id,
                    template_title=template_title,
                    freeform_text=request.freeform_text,
                    message=request.message,
                    root_dir=app.state.root_dir
                )
            )
            
            return {"status": "success", "suggestion_id": suggestion_id}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error creating suggestion: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create suggestion: {str(e)}")
    
    @app.get("/api/suggestions/pending")
    async def get_pending_suggestions(
        user_id: int = Depends(get_current_user)
    ):
        """Get pending suggestions sent to the current user."""
        try:
            from repositories.suggestions_repo import SuggestionsRepository
            
            suggestions_repo = SuggestionsRepository(app.state.root_dir)
            suggestions = suggestions_repo.get_pending_suggestions_for_user(str(user_id))
            
            return {"suggestions": suggestions}
        except Exception as e:
            logger.exception(f"Error getting pending suggestions: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get suggestions: {str(e)}")
    
    @app.put("/api/suggestions/{suggestion_id}/respond")
    async def respond_to_suggestion(
        suggestion_id: str,
        response: str = Query(..., regex="^(accept|decline)$"),
        user_id: int = Depends(get_current_user)
    ):
        """Accept or decline a suggestion."""
        try:
            from repositories.suggestions_repo import SuggestionsRepository
            
            suggestions_repo = SuggestionsRepository(app.state.root_dir)
            
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
    
    @app.get("/api/users/{user_id}/public-promises", response_model=List[PublicPromiseBadge])
    async def get_public_promises(
        user_id: int,
        current_user_id: int = Depends(get_current_user),
    ):
        """
        Get public promises for a user with stats (streak, progress, etc.).
        Authentication required.
        """
        try:
            promises_repo = PromisesRepository(app.state.root_dir)
            actions_repo = ActionsRepository(app.state.root_dir)
            reports_service = ReportsService(promises_repo, actions_repo, root_dir=app.state.root_dir)
            
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
    
    # Promise visibility endpoint
    class UpdateVisibilityRequest(BaseModel):
        visibility: str  # "private" or "public"
    
    @app.patch("/api/promises/{promise_id}/visibility")
    async def update_promise_visibility(
        promise_id: str,
        request: UpdateVisibilityRequest,
        user_id: int = Depends(get_current_user)
    ):
        """Update promise visibility. If making public, creates/links to marketplace template."""
        try:
            if request.visibility not in ["private", "public"]:
                raise HTTPException(status_code=400, detail="Visibility must be 'private' or 'public'")
            
            promises_repo = PromisesRepository(app.state.root_dir)
            promise = promises_repo.get_promise(user_id, promise_id)
            
            if not promise:
                raise HTTPException(status_code=404, detail="Promise not found")
            
            was_public = promise.visibility == "public"
            promise.visibility = request.visibility
            promises_repo.upsert_promise(user_id, promise)
            
            # If making public, create/upsert marketplace template
            if request.visibility == "public" and not was_public:
                templates_repo = TemplatesRepository(app.state.root_dir)
                instances_repo = InstancesRepository(app.state.root_dir)
                
                # Get promise_uuid first
                user_str = str(user_id)
                with get_db_session() as session:
                    promise_uuid = resolve_promise_uuid(session, user_str, promise_id)
                
                if not promise_uuid:
                    logger.warning(f"Could not resolve promise_uuid for promise {promise_id}, skipping template creation")
                else:
                    # Build canonical key: normalized text + metric type + target
                    normalized_text = promise.text.lower().strip().replace("_", " ").replace("  ", " ")
                    # Determine metric type from promise (hours_per_week > 0 = hours, else count)
                    metric_type = "hours" if promise.hours_per_week > 0 else "count"
                    target_value = promise.hours_per_week if metric_type == "hours" else 0.0
                    canonical_key = f"{normalized_text}|{metric_type}|{target_value}"
                    
                    # Check if template with this canonical_key exists
                    with get_db_session() as session:
                        existing_template = session.execute(
                            text("""
                                SELECT template_id FROM promise_templates
                                WHERE canonical_key = :canonical_key
                                LIMIT 1
                            """),
                            {"canonical_key": canonical_key}
                        ).fetchone()
                    
                    template_id = None
                    if existing_template:
                        template_id = existing_template[0]
                    else:
                        # Create new template from promise
                        template_data = {
                            "title": promise.text.replace("_", " "),
                            "category": "general",
                            "level": "beginner",
                            "why": f"Track progress on {promise.text.replace('_', ' ')}",
                            "done": f"Complete {promise.text.replace('_', ' ')}",
                            "effort": "medium",
                            "template_kind": "commitment",
                            "metric_type": metric_type,
                            "target_value": target_value,
                            "target_direction": "at_least",
                            "estimated_hours_per_unit": 1.0,
                            "duration_type": "week" if promise.recurring else "one_time",
                            "duration_weeks": 1 if promise.recurring else None,
                            "is_active": True,
                            "canonical_key": canonical_key,
                            "created_by_user_id": str(user_id),
                            "source_promise_uuid": promise_uuid,
                            "origin": "user_public"
                        }
                        template_id = templates_repo.create_template(template_data)
                    
                    # Link promise to template via promise_instances (idempotent due to unique constraint)
                    with get_db_session() as session:
                        if promise_uuid:
                            # Upsert instance link (ON CONFLICT DO NOTHING if unique constraint exists)
                            try:
                                session.execute(
                                    text("""
                                        INSERT INTO promise_instances (
                                            instance_id, user_id, template_id, promise_uuid, status,
                                            metric_type, target_value, estimated_hours_per_unit,
                                            start_date, end_date, created_at_utc, updated_at_utc
                                        ) VALUES (
                                            gen_random_uuid()::text, :user_id, :template_id, :promise_uuid, 'active',
                                            :metric_type, :target_value, 1.0,
                                            COALESCE(:start_date, CURRENT_DATE::text), :end_date,
                                            :now, :now
                                        )
                                        ON CONFLICT (promise_uuid) DO UPDATE SET
                                            template_id = EXCLUDED.template_id,
                                            updated_at_utc = EXCLUDED.updated_at_utc
                                    """),
                                    {
                                        "user_id": user_str,
                                        "template_id": template_id,
                                        "promise_uuid": promise_uuid,
                                        "metric_type": metric_type,
                                        "target_value": target_value,
                                        "start_date": promise.start_date.isoformat() if promise.start_date else None,
                                        "end_date": promise.end_date.isoformat() if promise.end_date else None,
                                        "now": utc_now_iso()
                                    }
                                )
                            except Exception as e:
                                # If unique constraint doesn't exist yet, try without ON CONFLICT
                                logger.warning(f"Could not upsert instance link (may need migration): {e}")
                                # Try simple insert (will fail if duplicate, that's OK)
                                try:
                                    session.execute(
                                        text("""
                                            INSERT INTO promise_instances (
                                                instance_id, user_id, template_id, promise_uuid, status,
                                                metric_type, target_value, estimated_hours_per_unit,
                                                start_date, end_date, created_at_utc, updated_at_utc
                                            ) VALUES (
                                                gen_random_uuid()::text, :user_id, :template_id, :promise_uuid, 'active',
                                                :metric_type, :target_value, 1.0,
                                                COALESCE(:start_date, CURRENT_DATE::text), :end_date,
                                                :now, :now
                                            )
                                        """),
                                        {
                                            "user_id": user_str,
                                            "template_id": template_id,
                                            "promise_uuid": promise_uuid,
                                            "metric_type": metric_type,
                                            "target_value": target_value,
                                            "start_date": promise.start_date.isoformat() if promise.start_date else None,
                                            "end_date": promise.end_date.isoformat() if promise.end_date else None,
                                            "now": utc_now_iso()
                                        }
                                    )
                                except Exception:
                                    # Already linked, ignore
                                    pass
            
            return {"status": "success", "visibility": promise.visibility}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error updating promise visibility: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to update visibility: {str(e)}")
    
    # Promise recurring endpoint
    class UpdateRecurringRequest(BaseModel):
        recurring: bool
    
    @app.patch("/api/promises/{promise_id}/recurring")
    async def update_promise_recurring(
        promise_id: str,
        request: UpdateRecurringRequest,
        user_id: int = Depends(get_current_user)
    ):
        """Update promise recurring status."""
        try:
            promises_repo = PromisesRepository(app.state.root_dir)
            promise = promises_repo.get_promise(user_id, promise_id)
            
            if not promise:
                raise HTTPException(status_code=404, detail="Promise not found")
            
            promise.recurring = request.recurring
            promises_repo.upsert_promise(user_id, promise)
            
            return {"status": "success", "recurring": promise.recurring}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error updating promise recurring status: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to update recurring status: {str(e)}")
    
    # Promise update endpoint
    class UpdatePromiseRequest(BaseModel):
        text: Optional[str] = None
        hours_per_week: Optional[float] = None
        end_date: Optional[str] = None  # ISO date string (YYYY-MM-DD)
    
    @app.patch("/api/promises/{promise_id}")
    async def update_promise(
        promise_id: str,
        request: UpdatePromiseRequest,
        user_id: int = Depends(get_current_user)
    ):
        """Update promise fields (text, hours_per_week, end_date)."""
        try:
            from services.planner_api_adapter import PlannerAPIAdapter
            from datetime import date as date_type
            
            plan_keeper = PlannerAPIAdapter(app.state.root_dir)
            
            # Parse end_date if provided
            end_date_obj = None
            if request.end_date:
                try:
                    end_date_obj = date_type.fromisoformat(request.end_date)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=f"Invalid end_date format: {request.end_date}. Expected YYYY-MM-DD")
            
            # Get current promise to validate end_date >= start_date
            promises_repo = PromisesRepository(app.state.root_dir)
            current_promise = promises_repo.get_promise(user_id, promise_id)
            
            if not current_promise:
                raise HTTPException(status_code=404, detail="Promise not found")
            
            # Validate end_date >= start_date if both are set
            if end_date_obj and current_promise.start_date:
                if end_date_obj < current_promise.start_date:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"end_date ({end_date_obj}) must be >= start_date ({current_promise.start_date})"
                    )
            
            # Validate hours_per_week if provided
            if request.hours_per_week is not None:
                if request.hours_per_week <= 0:
                    raise HTTPException(status_code=400, detail="hours_per_week must be a positive number")
            
            # Update promise using PlannerAPIAdapter
            result = plan_keeper.update_promise(
                user_id=user_id,
                promise_id=promise_id,
                promise_text=request.text,
                hours_per_week=request.hours_per_week,
                end_date=end_date_obj
            )
            
            # Check if update was successful (returns error message string on failure)
            if result and result.startswith("Promise with ID"):
                raise HTTPException(status_code=404, detail=result)
            elif result and ("must be" in result or "must be a" in result):
                raise HTTPException(status_code=400, detail=result)
            
            return {"status": "success", "message": result or "Promise updated successfully"}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error updating promise: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to update promise: {str(e)}")
    
    # Action logging endpoint
    class LogActionRequest(BaseModel):
        promise_id: str
        time_spent: float
        action_datetime: Optional[str] = None  # ISO format datetime string
        notes: Optional[str] = None  # Optional notes for this action
    
    @app.post("/api/actions")
    async def log_action(
        request: LogActionRequest,
        user_id: int = Depends(get_current_user)
    ):
        """Log an action (time spent) for a promise."""
        try:
            if request.time_spent <= 0:
                raise HTTPException(status_code=400, detail="Time spent must be positive")
            
            # Parse datetime if provided, otherwise use current time
            if request.action_datetime:
                try:
                    action_datetime = datetime.fromisoformat(request.action_datetime)
                    # If timezone-aware, convert to naive datetime
                    if action_datetime.tzinfo is not None:
                        import pytz
                        settings_repo = get_settings_repo()
                        settings = settings_repo.get_settings(user_id)
                        user_tz = settings.timezone if settings and settings.timezone not in (None, "DEFAULT") else "UTC"
                        tz = pytz.timezone(user_tz)
                        action_datetime = action_datetime.astimezone(tz).replace(tzinfo=None)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid action_datetime format")
            else:
                action_datetime = datetime.now()
            
            # Verify promise exists
            promises_repo = PromisesRepository(app.state.root_dir)
            promise = promises_repo.get_promise(user_id, request.promise_id)
            if not promise:
                raise HTTPException(status_code=404, detail="Promise not found")
            
            # Create and save action
            from models.models import Action
            action = Action(
                user_id=str(user_id),
                promise_id=request.promise_id,
                action="log_time",
                time_spent=request.time_spent,
                at=action_datetime,
                notes=request.notes if request.notes and request.notes.strip() else None
            )
            
            actions_repo = ActionsRepository(app.state.root_dir)
            actions_repo.append_action(action)
            
            return {"status": "success", "message": "Action logged successfully"}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error logging action: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to log action: {str(e)}")
    
    # Snooze promise endpoint
    @app.post("/api/promises/{promise_id}/snooze")
    async def snooze_promise(
        promise_id: str,
        user_id: int = Depends(get_current_user)
    ):
        """Snooze a promise until next week (hide from current week)."""
        try:
            promises_repo = PromisesRepository(app.state.root_dir)
            promise = promises_repo.get_promise(user_id, promise_id)
            
            if not promise:
                raise HTTPException(status_code=404, detail="Promise not found")
            
            # Calculate next week's start date (Monday)
            from datetime import timedelta
            today = datetime.now().date()
            days_until_monday = (7 - today.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7  # If today is Monday, go to next Monday
            next_monday = today + timedelta(days=days_until_monday)
            
            # Update promise start_date to next week
            promise.start_date = next_monday
            promises_repo.upsert_promise(user_id, promise)
            
            return {"status": "success", "message": f"Promise snoozed until {next_monday.isoformat()}"}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error snoozing promise: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to snooze promise: {str(e)}")
    
    # Schedule endpoints
    @app.get("/api/promises/{promise_id}/schedule")
    async def get_promise_schedule(
        promise_id: str,
        user_id: int = Depends(get_current_user)
    ):
        """Get schedule slots for a promise."""
        try:
            promises_repo = PromisesRepository(app.state.root_dir)
            schedules_repo = SchedulesRepository(app.state.root_dir)
            
            promise = promises_repo.get_promise(user_id, promise_id)
            if not promise:
                raise HTTPException(status_code=404, detail="Promise not found")
            
            # Get promise_uuid
            user_str = str(user_id)
            with get_db_session() as session:
                promise_uuid = resolve_promise_uuid(session, user_str, promise_id)
                if not promise_uuid:
                    raise HTTPException(status_code=404, detail="Promise UUID not found")
            
            slots = schedules_repo.list_slots(promise_uuid, is_active=True)
            return {"slots": slots}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error getting promise schedule: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get schedule: {str(e)}")
    
    class ScheduleSlotRequest(BaseModel):
        weekday: int  # 0-6
        start_local_time: str  # HH:MM:SS or HH:MM
        end_local_time: Optional[str] = None
        tz: Optional[str] = None
        start_date: Optional[str] = None  # ISO date
        end_date: Optional[str] = None  # ISO date
    
    class UpdateScheduleRequest(BaseModel):
        slots: List[ScheduleSlotRequest]
    
    @app.put("/api/promises/{promise_id}/schedule")
    async def update_promise_schedule(
        promise_id: str,
        request: UpdateScheduleRequest,
        user_id: int = Depends(get_current_user)
    ):
        """Replace schedule slots for a promise."""
        try:
            from datetime import time as time_type
            promises_repo = PromisesRepository(app.state.root_dir)
            schedules_repo = SchedulesRepository(app.state.root_dir)
            
            promise = promises_repo.get_promise(user_id, promise_id)
            if not promise:
                raise HTTPException(status_code=404, detail="Promise not found")
            
            # Get promise_uuid
            user_str = str(user_id)
            with get_db_session() as session:
                promise_uuid = resolve_promise_uuid(session, user_str, promise_id)
                if not promise_uuid:
                    raise HTTPException(status_code=404, detail="Promise UUID not found")
            
            # Validate weekdays
            for slot_req in request.slots:
                if slot_req.weekday < 0 or slot_req.weekday > 6:
                    raise HTTPException(status_code=400, detail="Weekday must be 0-6")
            
            # Convert to slot data format
            slots_data = []
            for slot_req in request.slots:
                start_time = time_type.fromisoformat(slot_req.start_local_time) if ":" in slot_req.start_local_time else time_type.fromisoformat(slot_req.start_local_time + ":00")
                end_time = None
                if slot_req.end_local_time:
                    end_time = time_type.fromisoformat(slot_req.end_local_time) if ":" in slot_req.end_local_time else time_type.fromisoformat(slot_req.end_local_time + ":00")
                
                slot_data = {
                    "promise_uuid": promise_uuid,
                    "weekday": slot_req.weekday,
                    "start_local_time": start_time,
                    "end_local_time": end_time,
                    "tz": slot_req.tz,
                    "start_date": date_from_iso(slot_req.start_date) if slot_req.start_date else None,
                    "end_date": date_from_iso(slot_req.end_date) if slot_req.end_date else None,
                    "is_active": True
                }
                slots_data.append(slot_data)
            
            schedules_repo.replace_slots(promise_uuid, slots_data)
            
            return {"status": "success", "message": "Schedule updated", "slots_count": len(slots_data)}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error updating promise schedule: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to update schedule: {str(e)}")
    
    @app.get("/api/promises/{promise_id}/reminders")
    async def get_promise_reminders(
        promise_id: str,
        user_id: int = Depends(get_current_user)
    ):
        """Get reminders for a promise."""
        try:
            promises_repo = PromisesRepository(app.state.root_dir)
            reminders_repo = RemindersRepository(app.state.root_dir)
            
            promise = promises_repo.get_promise(user_id, promise_id)
            if not promise:
                raise HTTPException(status_code=404, detail="Promise not found")
            
            # Get promise_uuid
            user_str = str(user_id)
            with get_db_session() as session:
                promise_uuid = resolve_promise_uuid(session, user_str, promise_id)
                if not promise_uuid:
                    raise HTTPException(status_code=404, detail="Promise UUID not found")
            
            reminders = reminders_repo.list_reminders(promise_uuid, enabled=None)
            return {"reminders": reminders}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error getting promise reminders: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get reminders: {str(e)}")
    
    class ReminderRequest(BaseModel):
        kind: str  # "slot_offset" or "fixed_time"
        slot_id: Optional[str] = None  # Required for slot_offset
        offset_minutes: Optional[int] = None  # For slot_offset
        weekday: Optional[int] = None  # For fixed_time (0-6)
        time_local: Optional[str] = None  # For fixed_time (HH:MM:SS or HH:MM)
        tz: Optional[str] = None
        enabled: Optional[bool] = True
    
    class UpdateRemindersRequest(BaseModel):
        reminders: List[ReminderRequest]
    
    @app.put("/api/promises/{promise_id}/reminders")
    async def update_promise_reminders(
        promise_id: str,
        request: UpdateRemindersRequest,
        user_id: int = Depends(get_current_user)
    ):
        """Replace reminders for a promise."""
        try:
            from datetime import time as time_type
            promises_repo = PromisesRepository(app.state.root_dir)
            reminders_repo = RemindersRepository(app.state.root_dir)
            dispatch_service = ReminderDispatchService(app.state.root_dir)
            
            promise = promises_repo.get_promise(user_id, promise_id)
            if not promise:
                raise HTTPException(status_code=404, detail="Promise not found")
            
            # Get promise_uuid
            user_str = str(user_id)
            with get_db_session() as session:
                promise_uuid = resolve_promise_uuid(session, user_str, promise_id)
                if not promise_uuid:
                    raise HTTPException(status_code=404, detail="Promise UUID not found")
            
            # Validate reminders
            for rem_req in request.reminders:
                if rem_req.kind not in ["slot_offset", "fixed_time"]:
                    raise HTTPException(status_code=400, detail="Reminder kind must be 'slot_offset' or 'fixed_time'")
                
                if rem_req.kind == "slot_offset":
                    if not rem_req.slot_id:
                        raise HTTPException(status_code=400, detail="slot_id required for slot_offset reminders")
                elif rem_req.kind == "fixed_time":
                    if rem_req.weekday is None or not rem_req.time_local:
                        raise HTTPException(status_code=400, detail="weekday and time_local required for fixed_time reminders")
                    if rem_req.weekday < 0 or rem_req.weekday > 6:
                        raise HTTPException(status_code=400, detail="weekday must be 0-6")
            
            # Convert to reminder data format
            reminders_data = []
            for rem_req in request.reminders:
                reminder_data = {
                    "promise_uuid": promise_uuid,
                    "kind": rem_req.kind,
                    "slot_id": rem_req.slot_id,
                    "offset_minutes": rem_req.offset_minutes,
                    "weekday": rem_req.weekday,
                    "time_local": time_type.fromisoformat(rem_req.time_local) if rem_req.time_local and ":" in rem_req.time_local else (time_type.fromisoformat(rem_req.time_local + ":00") if rem_req.time_local else None),
                    "tz": rem_req.tz,
                    "enabled": rem_req.enabled if rem_req.enabled is not None else True
                }
                
                # Compute next_run_at_utc
                next_run = dispatch_service.compute_next_run_at_utc(reminder_data, user_id)
                if next_run:
                    reminder_data["next_run_at_utc"] = dt_to_utc_iso(next_run)
                
                reminders_data.append(reminder_data)
            
            reminders_repo.replace_reminders(promise_uuid, reminders_data)
            
            return {"status": "success", "message": "Reminders updated", "reminders_count": len(reminders_data)}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error updating promise reminders: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to update reminders: {str(e)}")
    
    # Admin template management endpoints
    @app.get("/api/admin/templates")
    async def list_admin_templates(
        admin_id: int = Depends(get_admin_user)
    ):
        """List all templates (admin only, includes inactive)."""
        try:
            templates_repo = TemplatesRepository(app.state.root_dir)
            # Get all templates, including inactive
            templates = templates_repo.list_templates(is_active=None)
            return {"templates": templates}
        except Exception as e:
            logger.exception(f"Error listing admin templates: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to list templates: {str(e)}")
    
    @app.post("/api/admin/templates")
    async def create_admin_template(
        template_data: Dict[str, Any],
        admin_id: int = Depends(get_admin_user)
    ):
        """Create a new template (admin only)."""
        try:
            templates_repo = TemplatesRepository(app.state.root_dir)
            
            # Validate required fields (simplified schema)
            required_fields = ["title", "category", "target_value"]
            for field in required_fields:
                if field not in template_data:
                    raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
            
            # Set defaults for optional fields
            template_data.setdefault("metric_type", "count")
            template_data.setdefault("is_active", True)
            
            template_id = templates_repo.create_template(template_data)
            logger.info(f"Admin {admin_id} created template {template_id}")
            return {"status": "success", "template_id": template_id}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error creating template: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create template: {str(e)}")
    
    @app.put("/api/admin/templates/{template_id}")
    async def update_admin_template(
        template_id: str,
        template_data: Dict[str, Any],
        admin_id: int = Depends(get_admin_user)
    ):
        """Update an existing template (admin only)."""
        try:
            templates_repo = TemplatesRepository(app.state.root_dir)
            
            # Check if template exists
            existing = templates_repo.get_template(template_id)
            if not existing:
                raise HTTPException(status_code=404, detail="Template not found")
            
            success = templates_repo.update_template(template_id, template_data)
            if not success:
                raise HTTPException(status_code=400, detail="No fields to update")
            
            logger.info(f"Admin {admin_id} updated template {template_id}")
            return {"status": "success", "message": "Template updated successfully"}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error updating template: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to update template: {str(e)}")
    
    @app.delete("/api/admin/templates/{template_id}")
    async def delete_admin_template(
        template_id: str,
        admin_id: int = Depends(get_admin_user)
    ):
        """Delete a template (admin only, with safety checks)."""
        try:
            templates_repo = TemplatesRepository(app.state.root_dir)
            
            # Check if template exists
            existing = templates_repo.get_template(template_id)
            if not existing:
                raise HTTPException(status_code=404, detail="Template not found")
            
            # Check if template is in use
            in_use_check = templates_repo.check_template_in_use(template_id)
            if in_use_check["in_use"]:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Template cannot be deleted because it is in use",
                        "reasons": in_use_check["reasons"]
                    }
                )
            
            # Delete template
            success = templates_repo.delete_template(template_id)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to delete template")
            
            logger.info(f"Admin {admin_id} deleted template {template_id}")
            return {"status": "success", "message": "Template deleted successfully"}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error deleting template: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete template: {str(e)}")
    
    class GenerateTemplateRequest(BaseModel):
        prompt: str
    
    @app.post("/api/admin/templates/generate")
    async def generate_template_draft(
        request: GenerateTemplateRequest,
        admin_id: int = Depends(get_admin_user)
    ):
        """Generate a template draft from a prompt using AI (admin only)."""
        try:
            # Load LLM config
            cfg = load_llm_env()
            
            # Initialize chat model (same as LLMHandler)
            chat_model = None
            if cfg.get("GCP_PROJECT_ID", ""):
                chat_model = ChatVertexAI(
                    model=cfg["GCP_GEMINI_MODEL"],
                    project=cfg["GCP_PROJECT_ID"],
                    location=cfg["GCP_LOCATION"],
                    temperature=0.7,
                )
            
            if not chat_model and cfg.get("OPENAI_API_KEY", ""):
                chat_model = ChatOpenAI(
                    openai_api_key=cfg["OPENAI_API_KEY"],
                    temperature=0.7,
                    model="gpt-4o-mini",
                )
            
            if not chat_model:
                raise HTTPException(status_code=500, detail="No LLM configured")
            
            # Create prompt for template generation (simplified schema)
            system_prompt = """You are a template generator for a goal-tracking app. Generate a promise template from a user's description.

Output ONLY valid JSON with these fields:
{
  "title": "string (short, clear title, e.g., 'Exercise Daily', 'Read Books')",
  "description": "string (optional - brief motivation or details, 1 sentence max)",
  "category": "string (one of: 'health', 'fitness', 'learning', 'productivity', 'mindfulness', 'creativity', 'finance', 'social', 'self-care', 'other')",
  "target_value": number (how many per week, e.g., 7 for daily, 3 for 3x/week),
  "metric_type": "string ('count' for times/week or 'hours' for hours/week)",
  "emoji": "string (single emoji that represents this activity, e.g., '🏃', '📚', '💪')"
}

Rules:
- title should be short and actionable (2-4 words)
- If user mentions hours/week, use metric_type='hours'
- If user mentions times/week, days/week, or daily, use metric_type='count'
- For daily habits, target_value=7; for 3x/week, target_value=3; etc.
- Pick a relevant emoji from: 🏃📚💪🧘🎯✍️🎨🎵💻🌱💧😴🍎💰🧠❤️
- Output ONLY the JSON object, no markdown, no explanation"""
            
            user_prompt = f"Generate a promise template for: {request.prompt}"
            
            # Call LLM
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = chat_model.invoke(messages)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Parse JSON (handle markdown code blocks if present)
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            draft = json.loads(content)
            
            # Validate required fields
            if "title" not in draft:
                raise HTTPException(status_code=500, detail="Generated template missing required field: title")
            if "target_value" not in draft:
                draft["target_value"] = 7  # Default to daily
            
            # Set defaults for optional fields
            draft.setdefault("description", "")
            draft.setdefault("category", "other")
            draft.setdefault("metric_type", "count")
            draft.setdefault("emoji", "🎯")
            
            # Validate enums
            valid_categories = ['health', 'fitness', 'learning', 'productivity', 'mindfulness', 'creativity', 'finance', 'social', 'self-care', 'other']
            if draft["category"] not in valid_categories:
                draft["category"] = "other"
            if draft["metric_type"] not in ["hours", "count"]:
                draft["metric_type"] = "count"
            
            # Clamp target_value
            if draft["target_value"] <= 0:
                draft["target_value"] = 1
            
            # Set is_active default
            draft["is_active"] = True
            
            logger.info(f"Admin {admin_id} generated template draft from prompt: {request.prompt[:50]}")
            return draft
            
        except json.JSONDecodeError as e:
            logger.exception(f"Failed to parse LLM response as JSON: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to parse AI response: {str(e)}")
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error generating template draft: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to generate template draft: {str(e)}")
    
    # Admin create promise endpoint
    class DayReminder(BaseModel):
        weekday: int  # 0-6 (Monday-Sunday)
        time: str  # HH:MM format
        enabled: bool = True
    
    class CreatePromiseForUserRequest(BaseModel):
        target_user_id: int
        text: str
        hours_per_week: float
        recurring: bool = True
        start_date: Optional[str] = None  # ISO date string (YYYY-MM-DD)
        end_date: Optional[str] = None  # ISO date string (YYYY-MM-DD)
        visibility: str = "private"  # 'private' | 'followers' | 'clubs' | 'public'
        description: Optional[str] = None
        reminders: Optional[List[DayReminder]] = None
    
    @app.post("/api/admin/promises")
    async def create_promise_for_user(
        request: CreatePromiseForUserRequest,
        admin_id: int = Depends(get_admin_user)
    ):
        """Create a promise for a user (admin only)."""
        try:
            from services.planner_api_adapter import PlannerAPIAdapter
            from datetime import date as date_type
            from datetime import time as time_type
            
            # Validate visibility
            if request.visibility not in ["private", "followers", "clubs", "public"]:
                raise HTTPException(status_code=400, detail="Visibility must be 'private', 'followers', 'clubs', or 'public'")
            
            # Parse dates
            start_date_obj = None
            end_date_obj = None
            if request.start_date:
                try:
                    start_date_obj = date_type.fromisoformat(request.start_date)
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid start_date format: {request.start_date}. Expected YYYY-MM-DD")
            
            if request.end_date:
                try:
                    end_date_obj = date_type.fromisoformat(request.end_date)
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid end_date format: {request.end_date}. Expected YYYY-MM-DD")
            
            # Validate dates
            if start_date_obj and end_date_obj and start_date_obj > end_date_obj:
                raise HTTPException(status_code=400, detail="start_date must be <= end_date")
            
            # Validate hours_per_week
            if request.hours_per_week < 0:
                raise HTTPException(status_code=400, detail="hours_per_week must be >= 0")
            
            # Create promise using PlannerAPIAdapter
            plan_keeper = PlannerAPIAdapter(app.state.root_dir)
            result = plan_keeper.add_promise(
                user_id=request.target_user_id,
                promise_text=request.text,
                num_hours_promised_per_week=request.hours_per_week,
                recurring=request.recurring,
                start_date=start_date_obj,
                end_date=end_date_obj
            )
            
            # Extract promise_id from result message (format: "#P123456 Promise 'text' added successfully.")
            import re
            match = re.search(r'#([PT]\w+)', result)
            if not match:
                raise HTTPException(status_code=500, detail="Failed to extract promise ID from creation result")
            promise_id = match.group(1)
            
            # Update visibility and description if provided
            promises_repo = PromisesRepository(app.state.root_dir)
            promise = promises_repo.get_promise(request.target_user_id, promise_id)
            if not promise:
                raise HTTPException(status_code=500, detail="Failed to retrieve created promise")
            
            if request.visibility != "private" or request.description:
                promise.visibility = request.visibility
                if request.description:
                    promise.description = request.description
                promises_repo.upsert_promise(request.target_user_id, promise)
            
            # Create reminders if provided
            if request.reminders:
                # Get user's timezone
                settings_repo = SettingsRepository(app.state.root_dir)
                settings = settings_repo.get_settings(request.target_user_id)
                user_tz = settings.timezone if settings and settings.timezone and settings.timezone != "DEFAULT" else "UTC"
                
                # Get promise_uuid
                user_str = str(request.target_user_id)
                with get_db_session() as session:
                    promise_uuid = resolve_promise_uuid(session, user_str, promise_id)
                    if not promise_uuid:
                        raise HTTPException(status_code=500, detail="Failed to resolve promise UUID")
                
                # Convert reminders to ReminderRequest format
                reminders_repo = RemindersRepository(app.state.root_dir)
                dispatch_service = ReminderDispatchService(app.state.root_dir)
                
                reminders_data = []
                for rem in request.reminders:
                    if not rem.enabled:
                        continue
                    
                    # Validate weekday
                    if rem.weekday < 0 or rem.weekday > 6:
                        raise HTTPException(status_code=400, detail=f"Invalid weekday: {rem.weekday}. Must be 0-6 (Monday-Sunday)")
                    
                    # Validate time format
                    try:
                        time_parts = rem.time.split(":")
                        if len(time_parts) != 2:
                            raise ValueError
                        hour = int(time_parts[0])
                        minute = int(time_parts[1])
                        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                            raise ValueError
                        time_obj = time_type(hour, minute)
                    except (ValueError, IndexError):
                        raise HTTPException(status_code=400, detail=f"Invalid time format: {rem.time}. Expected HH:MM")
                    
                    reminder_data = {
                        "promise_uuid": promise_uuid,
                        "kind": "fixed_time",
                        "weekday": rem.weekday,
                        "time_local": time_obj,
                        "tz": user_tz,
                        "enabled": True
                    }
                    
                    # Compute next_run_at_utc
                    next_run = dispatch_service.compute_next_run_at_utc(reminder_data, request.target_user_id)
                    if next_run:
                        reminder_data["next_run_at_utc"] = dt_to_utc_iso(next_run)
                    
                    reminders_data.append(reminder_data)
                
                # Replace reminders
                if reminders_data:
                    reminders_repo.replace_reminders(promise_uuid, reminders_data)
            
            logger.info(f"Admin {admin_id} created promise {promise_id} for user {request.target_user_id}")
            return {"status": "success", "promise_id": promise_id, "message": result}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error creating promise for user: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create promise: {str(e)}")
    
    @app.post("/api/admin/promote")
    async def promote_staging_to_prod(
        admin_id: int = Depends(get_admin_user)
    ):
        """
        Promote staging database to production (admin only).
        This copies all data from staging to production database.
        WARNING: This will overwrite all production data!
        """
        try:
            import subprocess
            import os
            
            prod_url = os.getenv("DATABASE_URL_PROD")
            staging_url = os.getenv("DATABASE_URL_STAGING")
            
            if not prod_url:
                raise HTTPException(status_code=500, detail="DATABASE_URL_PROD environment variable is not set")
            
            if not staging_url:
                raise HTTPException(status_code=500, detail="DATABASE_URL_STAGING environment variable is not set")
            
            logger.warning(f"Admin {admin_id} initiated staging to production promotion")
            logger.warning(f"Staging: {staging_url}")
            logger.warning(f"Production: {prod_url}")
            
            # Dump staging database
            logger.info("Dumping staging database...")
            dump_process = subprocess.run(
                ["pg_dump", staging_url],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if dump_process.returncode != 0:
                error_msg = dump_process.stderr or "Unknown error during pg_dump"
                logger.error(f"pg_dump failed: {error_msg}")
                raise HTTPException(status_code=500, detail=f"Failed to dump staging database: {error_msg}")
            
            dump_sql = dump_process.stdout
            
            # Restore to production
            logger.info("Restoring to production database...")
            restore_process = subprocess.run(
                ["psql", prod_url],
                input=dump_sql,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            if restore_process.returncode != 0:
                error_msg = restore_process.stderr or "Unknown error during psql restore"
                logger.error(f"psql restore failed: {error_msg}")
                raise HTTPException(status_code=500, detail=f"Failed to restore to production: {error_msg}")
            
            # CRITICAL: Sync sequences after restore
            # pg_dump includes explicit IDs, but sequences don't auto-update
            # This prevents duplicate key errors on the next insert
            logger.info("Syncing PostgreSQL sequences after restore...")
            sync_sequences_sql = """
                DO $$
                DECLARE
                    r RECORD;
                    seq_name TEXT;
                    max_val BIGINT;
                BEGIN
                    FOR r IN (
                        SELECT 
                            t.table_name,
                            c.column_name
                        FROM information_schema.tables t
                        JOIN information_schema.columns c 
                            ON t.table_name = c.table_name 
                            AND t.table_schema = c.table_schema
                        WHERE t.table_schema = 'public'
                            AND t.table_type = 'BASE TABLE'
                            AND c.column_default LIKE 'nextval%'
                    )
                    LOOP
                        seq_name := pg_get_serial_sequence('public.' || r.table_name, r.column_name);
                        IF seq_name IS NOT NULL THEN
                            EXECUTE format('SELECT COALESCE(MAX(%I), 0) FROM %I', r.column_name, r.table_name) INTO max_val;
                            EXECUTE format('SELECT setval(%L, GREATEST(%s, 1))', seq_name, max_val);
                            RAISE NOTICE 'Synced sequence % to %', seq_name, max_val;
                        END IF;
                    END LOOP;
                END $$;
            """
            
            sync_process = subprocess.run(
                ["psql", prod_url, "-c", sync_sequences_sql],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if sync_process.returncode != 0:
                # Log warning but don't fail - data was restored successfully
                logger.warning(f"Sequence sync warning (data restored OK): {sync_process.stderr}")
            else:
                logger.info("Sequences synced successfully")
            
            logger.info(f"Admin {admin_id} successfully promoted staging to production")
            return {
                "status": "success",
                "message": "Staging database successfully promoted to production"
            }
            
        except subprocess.TimeoutExpired:
            logger.error("Promotion operation timed out")
            raise HTTPException(status_code=500, detail="Promotion operation timed out. Please check database status.")
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error promoting staging to production: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to promote staging to production: {str(e)}")
    
    # Template API endpoints
    @app.get("/api/templates")
    async def list_templates(
        category: Optional[str] = Query(None, description="Filter by category"),
        program_key: Optional[str] = Query(None, description="Filter by program key"),
        user_id: int = Depends(get_current_user)
    ):
        """List templates with unlock status."""
        try:
            templates_repo = TemplatesRepository(app.state.root_dir)
            unlocks_service = TemplateUnlocksService(app.state.root_dir)
            
            templates = templates_repo.list_templates(category=category, program_key=program_key, is_active=True)
            templates_with_status = unlocks_service.annotate_templates_with_unlock_status(user_id, templates)
            
            return {"templates": templates_with_status}
        except Exception as e:
            logger.exception(f"Error listing templates: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to list templates: {str(e)}")
    
    @app.get("/api/templates/{template_id}")
    async def get_template(
        template_id: str,
        user_id: int = Depends(get_current_user)
    ):
        """Get template details (simplified schema)."""
        try:
            templates_repo = TemplatesRepository(app.state.root_dir)
            
            template = templates_repo.get_template(template_id)
            if not template:
                raise HTTPException(status_code=404, detail="Template not found")
            
            # All templates are now unlocked (simplified schema)
            return {
                **template,
                "unlocked": True,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error getting template: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get template: {str(e)}")
    
    @app.get("/api/templates/{template_id}/users")
    async def get_template_users(
        template_id: str,
        limit: int = Query(8, ge=1, le=20),
        user_id: int = Depends(get_current_user)
    ):
        """Get users using this template (for 'used by' badges)."""
        try:
            templates_repo = TemplatesRepository(app.state.root_dir)
            settings_repo = SettingsRepository(app.state.root_dir)
            
            # Verify template exists
            template = templates_repo.get_template(template_id)
            if not template:
                raise HTTPException(status_code=404, detail="Template not found")
            
            # Get users with active instances for this template
            with get_db_session() as session:
                rows = session.execute(
                    text("""
                        SELECT DISTINCT i.user_id, u.first_name, u.username, u.avatar_path, u.avatar_file_unique_id
                        FROM promise_instances i
                        JOIN users u ON i.user_id = u.user_id
                        WHERE i.template_id = :template_id
                          AND i.status = 'active'
                        ORDER BY i.created_at_utc DESC
                        LIMIT :limit
                    """),
                    {"template_id": template_id, "limit": limit}
                ).fetchall()
            
            users = []
            for row in rows:
                users.append({
                    "user_id": row[0],
                    "first_name": row[1],
                    "username": row[2],
                    "avatar_path": row[3],
                    "avatar_file_unique_id": row[4]
                })
            
            return {"users": users, "total": len(users)}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error getting template users: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get template users: {str(e)}")
    
    class SubscribeTemplateRequest(BaseModel):
        start_date: Optional[str] = None  # ISO date string
        target_date: Optional[str] = None  # ISO date string
        target_value: Optional[float] = None  # Override template's target_value
    
    @app.post("/api/templates/{template_id}/subscribe")
    async def subscribe_template(
        template_id: str,
        request: Optional[SubscribeTemplateRequest] = None,
        user_id: int = Depends(get_current_user)
    ):
        """Subscribe to a template (creates promise + instance)."""
        try:
            from datetime import date as date_type
            try:
                from dateutil.parser import parse as parse_date
            except ImportError:
                # Fallback to datetime.fromisoformat
                def parse_date(s: str) -> date_type:
                    return date_type.fromisoformat(s.split('T')[0])
            
            instances_repo = InstancesRepository(app.state.root_dir)
            unlocks_service = TemplateUnlocksService(app.state.root_dir)
            
            # Check if template is unlocked
            unlock_status = unlocks_service.get_unlock_status(user_id, template_id)
            if not unlock_status["unlocked"]:
                raise HTTPException(
                    status_code=403,
                    detail=f"Template is locked: {unlock_status['lock_reason']}"
                )
            
            # Parse dates
            start_date = None
            target_date = None
            target_value_override = None
            if request:
                if request.start_date:
                    start_date = parse_date(request.start_date).date()
                if request.target_date:
                    target_date = parse_date(request.target_date).date()
                if request.target_value is not None:
                    target_value_override = float(request.target_value)
            
            result = instances_repo.subscribe_template(user_id, template_id, start_date, target_date, target_value_override)
            
            return {"status": "success", **result}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error subscribing to template: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to subscribe: {str(e)}")
    
    @app.get("/api/instances/active")
    async def list_active_instances(
        user_id: int = Depends(get_current_user)
    ):
        """List active template instances for the user."""
        try:
            instances_repo = InstancesRepository(app.state.root_dir)
            instances = instances_repo.list_active_instances(user_id)
            return {"instances": instances}
        except Exception as e:
            logger.exception(f"Error listing instances: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to list instances: {str(e)}")
    
    # Check-in and weekly note endpoints
    class CheckinRequest(BaseModel):
        action_datetime: Optional[str] = None  # ISO datetime string
    
    @app.post("/api/promises/{promise_id}/checkin")
    async def checkin_promise(
        promise_id: str,
        request: Optional[CheckinRequest] = None,
        user_id: int = Depends(get_current_user)
    ):
        """Record a check-in for a promise (count-based templates)."""
        try:
            from datetime import datetime
            from dateutil.parser import parse as parse_datetime
            
            promises_repo = PromisesRepository(app.state.root_dir)
            promise = promises_repo.get_promise(user_id, promise_id)
            
            if not promise:
                raise HTTPException(status_code=404, detail="Promise not found")
            
            # Parse datetime if provided
            action_datetime = None
            if request and request.action_datetime:
                try:
                    action_datetime = parse_datetime(request.action_datetime)
                    if action_datetime.tzinfo is not None:
                        import pytz
                        settings_repo = get_settings_repo()
                        settings = settings_repo.get_settings(user_id)
                        user_tz = settings.timezone if settings and settings.timezone not in (None, "DEFAULT") else "UTC"
                        tz = pytz.timezone(user_tz)
                        action_datetime = action_datetime.astimezone(tz).replace(tzinfo=None)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid action_datetime format")
            else:
                action_datetime = datetime.now()
            
            # Create check-in action
            from models.models import Action
            from models.enums import ActionType
            action = Action(
                user_id=str(user_id),
                promise_id=promise_id,
                action=ActionType.CHECKIN.value,
                time_spent=0.0,
                at=action_datetime
            )
            
            actions_repo = ActionsRepository(app.state.root_dir)
            actions_repo.append_action(action)
            
            return {"status": "success", "message": "Check-in recorded successfully"}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error recording check-in: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to record check-in: {str(e)}")
    
    class WeeklyNoteRequest(BaseModel):
        week_start: str  # ISO date string
        note: Optional[str] = None
    
    @app.post("/api/promises/{promise_id}/weekly-note")
    async def update_weekly_note(
        promise_id: str,
        request: WeeklyNoteRequest,
        user_id: int = Depends(get_current_user)
    ):
        """Update weekly note for a promise instance."""
        try:
            instances_repo = InstancesRepository(app.state.root_dir)
            reviews_repo = ReviewsRepository(app.state.root_dir)
            
            # Find instance by promise_id (PostgreSQL)
            from db.postgres_db import resolve_promise_uuid, get_db_session
            user = str(user_id)
            with get_db_session() as session:
                promise_uuid = resolve_promise_uuid(session, user, promise_id)
                if not promise_uuid:
                    raise HTTPException(status_code=404, detail="Promise not found")
            
            instance = instances_repo.get_instance_by_promise_uuid(user_id, promise_uuid)
            if not instance:
                raise HTTPException(status_code=404, detail="Instance not found for this promise")
            
            success = reviews_repo.update_weekly_note(
                user_id, instance["instance_id"], request.week_start, request.note
            )
            
            if not success:
                raise HTTPException(status_code=404, detail="Weekly review not found")
            
            return {"status": "success", "message": "Weekly note updated"}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error updating weekly note: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to update weekly note: {str(e)}")
    
    # Distraction events endpoints
    class LogDistractionRequest(BaseModel):
        category: str
        minutes: float
        at_utc: Optional[str] = None  # ISO datetime string
    
    @app.post("/api/distractions")
    async def log_distraction(
        request: LogDistractionRequest,
        user_id: int = Depends(get_current_user)
    ):
        """Log a distraction event (for budget templates)."""
        try:
            from datetime import datetime
            from dateutil.parser import parse as parse_datetime
            
            distractions_repo = DistractionsRepository(app.state.root_dir)
            
            at = None
            if request.at_utc:
                try:
                    at = parse_datetime(request.at_utc)
                    if at.tzinfo is not None:
                        import pytz
                        settings_repo = get_settings_repo()
                        settings = settings_repo.get_settings(user_id)
                        user_tz = settings.timezone if settings and settings.timezone not in (None, "DEFAULT") else "UTC"
                        tz = pytz.timezone(user_tz)
                        at = at.astimezone(tz).replace(tzinfo=None)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid at_utc format")
            
            event_uuid = distractions_repo.log_distraction(
                user_id, request.category, request.minutes, at
            )
            
            return {"status": "success", "event_uuid": event_uuid, "message": "Distraction logged"}
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error logging distraction: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to log distraction: {str(e)}")
    
    @app.get("/api/distractions/weekly")
    async def get_weekly_distractions(
        ref_time: Optional[str] = Query(None, description="Reference time (ISO datetime)"),
        category: Optional[str] = Query(None, description="Filter by category"),
        user_id: int = Depends(get_current_user)
    ):
        """Get weekly distraction summary."""
        try:
            from datetime import datetime
            from dateutil.parser import parse as parse_datetime
            from utils.time_utils import get_week_range
            
            distractions_repo = DistractionsRepository(app.state.root_dir)
            
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
    
    # Admin API endpoints
    class AdminUser(BaseModel):
        """Admin user information."""
        user_id: str
        first_name: Optional[str] = None
        last_name: Optional[str] = None
        username: Optional[str] = None
        last_seen_utc: Optional[str] = None
        timezone: Optional[str] = None
        language: Optional[str] = None
        promise_count: Optional[int] = None
        activity_count: Optional[int] = None
    
    class AdminUsersResponse(BaseModel):
        """Response model for admin users endpoint."""
        users: List[AdminUser]
        total: int
    
    class CreateBroadcastRequest(BaseModel):
        """Request model for creating a broadcast."""
        message: str
        target_user_ids: List[int]
        scheduled_time_utc: Optional[str] = None  # ISO format datetime string, None for immediate
        bot_token_id: Optional[str] = None  # Optional bot token ID to use for this broadcast
    
    class BroadcastResponse(BaseModel):
        """Response model for broadcast."""
        broadcast_id: str
        admin_id: str
        message: str
        target_user_ids: List[int]
        scheduled_time_utc: str
        status: str
        bot_token_id: Optional[str] = None
        created_at: str
        updated_at: str
    
    class BotTokenResponse(BaseModel):
        """Response model for bot token."""
        bot_token_id: str
        bot_username: Optional[str] = None
        is_active: bool
        description: Optional[str] = None
        created_at_utc: str
        updated_at_utc: str
    
    class ConversationMessage(BaseModel):
        """Response model for a conversation message."""
        id: int
        user_id: str
        chat_id: Optional[str] = None
        message_id: Optional[int] = None
        message_type: str  # 'user' or 'bot'
        content: str
        created_at_utc: str
    
    class ConversationResponse(BaseModel):
        """Response model for conversation history."""
        messages: List[ConversationMessage]
    
    @app.get("/api/admin/users", response_model=AdminUsersResponse)
    async def get_admin_users(
        limit: int = Query(default=1000, ge=1, le=10000),
        admin_id: int = Depends(get_admin_user)
    ):
        """
        Get all users (admin only).
        
        Args:
            limit: Maximum number of users to return
            admin_id: Admin user ID (from dependency)
        
        Returns:
            List of all users
        """
        try:
            from db.postgres_db import get_db_session
            from sqlalchemy import text
            from datetime import datetime, timedelta, timezone

            # Calculate 30 days ago for activity count
            since_utc = (
                datetime.now(timezone.utc) - timedelta(days=30)
            ).isoformat().replace("+00:00", "Z")

            with get_db_session() as session:
                rows = session.execute(
                    text("""
                        SELECT 
                            u.user_id,
                            u.first_name,
                            u.last_name,
                            u.username,
                            u.last_seen_utc,
                            u.timezone,
                            u.language,
                            COALESCE(promise_counts.promise_count, 0) as promise_count,
                            COALESCE(activity.activity_count, 0) as activity_count
                        FROM users u
                        LEFT JOIN (
                            SELECT user_id, COUNT(*) as promise_count
                            FROM promises
                            WHERE is_deleted = 0
                            GROUP BY user_id
                        ) promise_counts ON u.user_id = promise_counts.user_id
                        LEFT JOIN (
                            SELECT user_id, COUNT(*) as activity_count
                            FROM actions 
                            WHERE at_utc >= :since_utc
                            GROUP BY user_id
                        ) activity ON u.user_id = activity.user_id
                        ORDER BY u.last_seen_utc DESC NULLS LAST
                        LIMIT :limit;
                    """),
                    {"since_utc": since_utc, "limit": int(limit)},
                ).mappings().fetchall()

            users: List[AdminUser] = []
            for row in rows:
                users.append(
                    AdminUser(
                        user_id=str(row.get("user_id")),
                        first_name=row.get("first_name"),
                        last_name=row.get("last_name"),
                        username=row.get("username"),
                        last_seen_utc=row.get("last_seen_utc"),
                        timezone=row.get("timezone"),
                        language=row.get("language"),
                        promise_count=row.get("promise_count"),
                        activity_count=row.get("activity_count"),
                    )
                )

            return AdminUsersResponse(users=users, total=len(users))
                
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error getting admin users: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch users: {str(e)}")
    
    @app.get("/api/admin/bot-tokens", response_model=List[BotTokenResponse])
    async def get_bot_tokens(
        is_active: Optional[bool] = Query(None, description="Filter by active status"),
        admin_id: int = Depends(get_admin_user)
    ):
        """
        List available bot tokens (admin only).
        
        Args:
            is_active: Filter by active status (optional)
            admin_id: Admin user ID (from dependency)
        
        Returns:
            List of bot tokens
        """
        try:
            bot_tokens_repo = BotTokensRepository(app.state.root_dir)
            tokens = bot_tokens_repo.list_bot_tokens(is_active=is_active)
            
            return [
                BotTokenResponse(
                    bot_token_id=token["bot_token_id"],
                    bot_username=token["bot_username"],
                    is_active=token["is_active"],
                    description=token["description"],
                    created_at_utc=token["created_at_utc"],
                    updated_at_utc=token["updated_at_utc"],
                )
                for token in tokens
            ]
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error listing bot tokens: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to list bot tokens: {str(e)}")
    
    @app.get("/api/admin/users/{user_id}/conversations", response_model=ConversationResponse)
    async def get_user_conversations(
        user_id: int,
        limit: int = Query(default=100, ge=1, le=1000),
        message_type: Optional[str] = Query(None, description="Filter by 'user' or 'bot'"),
        admin_id: int = Depends(get_admin_user)
    ):
        """
        Get conversation history for a user (admin only).
        
        Args:
            user_id: Target user ID
            limit: Maximum number of messages to return
            message_type: Filter by message type ('user' or 'bot'), or None for all
            admin_id: Admin user ID (from dependency)
        
        Returns:
            List of conversation messages
        """
        try:
            from repositories.conversation_repo import ConversationRepository
            
            # Validate message_type if provided
            if message_type and message_type not in ['user', 'bot']:
                raise HTTPException(status_code=400, detail="message_type must be 'user' or 'bot'")
            
            conversation_repo = ConversationRepository(app.state.root_dir)
            messages = conversation_repo.get_recent_history(
                user_id=user_id,
                limit=limit,
                message_type=message_type
            )
            
            # Convert to response models
            conversation_messages = [
                ConversationMessage(
                    id=msg["id"],
                    user_id=msg["user_id"],
                    chat_id=msg.get("chat_id"),
                    message_id=msg.get("message_id"),
                    message_type=msg["message_type"],
                    content=msg["content"],
                    created_at_utc=msg["created_at_utc"],
                )
                for msg in messages
            ]
            
            return ConversationResponse(messages=conversation_messages)
                
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error getting conversations for user {user_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch conversations: {str(e)}")
    
    @app.post("/api/admin/broadcast", response_model=BroadcastResponse)
    async def create_broadcast(
        request: CreateBroadcastRequest,
        admin_id: int = Depends(get_admin_user)
    ):
        """
        Create or schedule a broadcast (admin only).
        
        Args:
            request: Broadcast creation request
            admin_id: Admin user ID (from dependency)
        
        Returns:
            Created broadcast
        """
        try:
            from zoneinfo import ZoneInfo
            from services.broadcast_service import get_all_users
            from infra.scheduler import schedule_once
            
            # Validate message
            if not request.message or not request.message.strip():
                raise HTTPException(status_code=400, detail="Message cannot be empty")
            
            # Validate target users
            if not request.target_user_ids:
                raise HTTPException(status_code=400, detail="At least one target user must be selected")
            
            # Get all valid users
            all_users = get_all_users(app.state.root_dir)
            valid_user_ids = [uid for uid in request.target_user_ids if uid in all_users]
            
            if not valid_user_ids:
                raise HTTPException(status_code=400, detail="No valid target users found")
            
            # Determine scheduled time
            if request.scheduled_time_utc:
                # Parse scheduled time
                try:
                    scheduled_dt = datetime.fromisoformat(request.scheduled_time_utc.replace('Z', '+00:00'))
                    if scheduled_dt.tzinfo is None:
                        scheduled_dt = scheduled_dt.replace(tzinfo=ZoneInfo("UTC"))
                    scheduled_dt = scheduled_dt.astimezone(ZoneInfo("UTC"))
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=f"Invalid scheduled_time_utc format: {e}")
                
                # Check if time is in the past
                now_utc = datetime.now(ZoneInfo("UTC"))
                if scheduled_dt < now_utc:
                    raise HTTPException(status_code=400, detail="Scheduled time cannot be in the past")
            else:
                # Immediate broadcast - schedule for now
                scheduled_dt = datetime.now(ZoneInfo("UTC"))
            
            # Create broadcast in database
            broadcasts_repo = BroadcastsRepository(app.state.root_dir)
            broadcast_id = broadcasts_repo.create_broadcast(
                admin_id=admin_id,
                message=request.message,
                target_user_ids=valid_user_ids,
                scheduled_time_utc=scheduled_dt,
                bot_token_id=request.bot_token_id,
            )
            
            # Schedule job if not immediate (or schedule immediately if it's now)
            # Note: Job scheduling requires access to the application/job_queue
            # For now, broadcasts created via API will need to be executed by a separate process
            # or we can add a periodic job that checks for pending broadcasts
            # This is a limitation - in production, you'd want to schedule the job here
            # For immediate broadcasts, we could execute them directly, but that's async
            # and would require more complex setup
            
            # Get created broadcast
            broadcast = broadcasts_repo.get_broadcast(broadcast_id)
            if not broadcast:
                raise HTTPException(status_code=500, detail="Failed to retrieve created broadcast")
            
            return BroadcastResponse(
                broadcast_id=broadcast.broadcast_id,
                admin_id=broadcast.admin_id,
                message=broadcast.message,
                target_user_ids=broadcast.target_user_ids,
                scheduled_time_utc=broadcast.scheduled_time_utc.isoformat(),
                status=broadcast.status,
                bot_token_id=broadcast.bot_token_id,
                created_at=broadcast.created_at.isoformat() if broadcast.created_at else "",
                updated_at=broadcast.updated_at.isoformat() if broadcast.updated_at else "",
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error creating broadcast: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create broadcast: {str(e)}")
    
    @app.get("/api/admin/broadcasts", response_model=List[BroadcastResponse])
    async def list_broadcasts(
        status: Optional[str] = Query(None),
        limit: int = Query(default=100, ge=1, le=1000),
        admin_id: int = Depends(get_admin_user)
    ):
        """
        List scheduled broadcasts (admin only).
        
        Args:
            status: Filter by status (pending, completed, cancelled)
            limit: Maximum number of broadcasts to return
            admin_id: Admin user ID (from dependency)
        
        Returns:
            List of broadcasts
        """
        try:
            broadcasts_repo = BroadcastsRepository(app.state.root_dir)
            broadcasts = broadcasts_repo.list_broadcasts(
                admin_id=admin_id,
                status=status,
                limit=limit,
            )
            
            return [
                BroadcastResponse(
                    broadcast_id=b.broadcast_id,
                    admin_id=b.admin_id,
                    message=b.message,
                    target_user_ids=b.target_user_ids,
                    scheduled_time_utc=b.scheduled_time_utc.isoformat(),
                    status=b.status,
                    bot_token_id=b.bot_token_id,
                    created_at=b.created_at.isoformat() if b.created_at else "",
                    updated_at=b.updated_at.isoformat() if b.updated_at else "",
                )
                for b in broadcasts
            ]
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error listing broadcasts: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to list broadcasts: {str(e)}")
    
    @app.get("/api/admin/broadcasts/{broadcast_id}", response_model=BroadcastResponse)
    async def get_broadcast(
        broadcast_id: str,
        admin_id: int = Depends(get_admin_user)
    ):
        """
        Get broadcast details (admin only).
        
        Args:
            broadcast_id: Broadcast ID
            admin_id: Admin user ID (from dependency)
        
        Returns:
            Broadcast details
        """
        try:
            broadcasts_repo = BroadcastsRepository(app.state.root_dir)
            broadcast = broadcasts_repo.get_broadcast(broadcast_id)
            
            if not broadcast:
                raise HTTPException(status_code=404, detail="Broadcast not found")
            
            # Verify admin owns this broadcast
            if broadcast.admin_id != str(admin_id):
                raise HTTPException(status_code=403, detail="Access denied")
            
            return BroadcastResponse(
                broadcast_id=broadcast.broadcast_id,
                admin_id=broadcast.admin_id,
                message=broadcast.message,
                target_user_ids=broadcast.target_user_ids,
                scheduled_time_utc=broadcast.scheduled_time_utc.isoformat(),
                status=broadcast.status,
                bot_token_id=broadcast.bot_token_id,
                created_at=broadcast.created_at.isoformat() if broadcast.created_at else "",
                updated_at=broadcast.updated_at.isoformat() if broadcast.updated_at else "",
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error getting broadcast: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get broadcast: {str(e)}")
    
    class UpdateBroadcastRequest(BaseModel):
        """Request model for updating a broadcast."""
        message: Optional[str] = None
        target_user_ids: Optional[List[int]] = None
        scheduled_time_utc: Optional[str] = None  # ISO format datetime string
    
    @app.patch("/api/admin/broadcasts/{broadcast_id}", response_model=BroadcastResponse)
    async def update_broadcast(
        broadcast_id: str,
        request: UpdateBroadcastRequest,
        admin_id: int = Depends(get_admin_user)
    ):
        """
        Update a scheduled broadcast (admin only).
        
        Args:
            broadcast_id: Broadcast ID
            request: Update request
            admin_id: Admin user ID (from dependency)
        
        Returns:
            Updated broadcast
        """
        try:
            from zoneinfo import ZoneInfo
            
            broadcasts_repo = BroadcastsRepository(app.state.root_dir)
            broadcast = broadcasts_repo.get_broadcast(broadcast_id)
            
            if not broadcast:
                raise HTTPException(status_code=404, detail="Broadcast not found")
            
            # Verify admin owns this broadcast
            if broadcast.admin_id != str(admin_id):
                raise HTTPException(status_code=403, detail="Access denied")
            
            # Can only update pending broadcasts
            if broadcast.status != "pending":
                raise HTTPException(status_code=400, detail="Can only update pending broadcasts")
            
            # Parse scheduled time if provided
            scheduled_dt = None
            if request.scheduled_time_utc:
                try:
                    scheduled_dt = datetime.fromisoformat(request.scheduled_time_utc.replace('Z', '+00:00'))
                    if scheduled_dt.tzinfo is None:
                        scheduled_dt = scheduled_dt.replace(tzinfo=ZoneInfo("UTC"))
                    scheduled_dt = scheduled_dt.astimezone(ZoneInfo("UTC"))
                    
                    # Check if time is in the past
                    now_utc = datetime.now(ZoneInfo("UTC"))
                    if scheduled_dt < now_utc:
                        raise HTTPException(status_code=400, detail="Scheduled time cannot be in the past")
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=f"Invalid scheduled_time_utc format: {e}")
            
            # Update broadcast
            success = broadcasts_repo.update_broadcast(
                broadcast_id=broadcast_id,
                message=request.message,
                target_user_ids=request.target_user_ids,
                scheduled_time_utc=scheduled_dt,
            )
            
            if not success:
                raise HTTPException(status_code=500, detail="Failed to update broadcast")
            
            # Get updated broadcast
            updated_broadcast = broadcasts_repo.get_broadcast(broadcast_id)
            if not updated_broadcast:
                raise HTTPException(status_code=500, detail="Failed to retrieve updated broadcast")
            
            return BroadcastResponse(
                broadcast_id=updated_broadcast.broadcast_id,
                admin_id=updated_broadcast.admin_id,
                message=updated_broadcast.message,
                target_user_ids=updated_broadcast.target_user_ids,
                scheduled_time_utc=updated_broadcast.scheduled_time_utc.isoformat(),
                status=updated_broadcast.status,
                bot_token_id=updated_broadcast.bot_token_id,
                created_at=updated_broadcast.created_at.isoformat() if updated_broadcast.created_at else "",
                updated_at=updated_broadcast.updated_at.isoformat() if updated_broadcast.updated_at else "",
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error updating broadcast: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to update broadcast: {str(e)}")
    
    @app.delete("/api/admin/broadcasts/{broadcast_id}")
    async def cancel_broadcast(
        broadcast_id: str,
        admin_id: int = Depends(get_admin_user)
    ):
        """
        Cancel a scheduled broadcast (admin only).
        
        Args:
            broadcast_id: Broadcast ID
            admin_id: Admin user ID (from dependency)
        
        Returns:
            Success message
        """
        try:
            broadcasts_repo = BroadcastsRepository(app.state.root_dir)
            broadcast = broadcasts_repo.get_broadcast(broadcast_id)
            
            if not broadcast:
                raise HTTPException(status_code=404, detail="Broadcast not found")
            
            # Verify admin owns this broadcast
            if broadcast.admin_id != str(admin_id):
                raise HTTPException(status_code=403, detail="Access denied")
            
            # Can only cancel pending broadcasts
            if broadcast.status != "pending":
                raise HTTPException(status_code=400, detail="Can only cancel pending broadcasts")
            
            # Cancel broadcast
            success = broadcasts_repo.cancel_broadcast(broadcast_id)
            
            if not success:
                raise HTTPException(status_code=500, detail="Failed to cancel broadcast")
            
            return {"status": "success", "message": "Broadcast cancelled successfully"}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error cancelling broadcast: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to cancel broadcast: {str(e)}")
    
    # Add route for /weekly to serve React app (works with or without static_dir)
    @app.get("/weekly")
    async def weekly_route():
        """
        Route for /weekly - serves React app index.html.
        This route works whether static_dir is set or not.
        """
        # If static_dir is set, serve the built React app
        if static_dir and os.path.isdir(static_dir):
            index_path = os.path.join(static_dir, "index.html")
            if os.path.exists(index_path):
                # Prevent caching of index.html to ensure users get latest version
                response = FileResponse(index_path)
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                return response
            logger.warning(f"[WARNING] static_dir set but index.html not found at {index_path}")
        
        # If no static_dir or file not found, return helpful error
        # In development, the React app should be running on Vite dev server
        # In production, static_dir should be set to the built React app directory
        from fastapi.responses import JSONResponse
        logger.warning("[WARNING] /weekly route accessed but React app not available. "
                      "static_dir is not set or index.html not found.")
        return JSONResponse(
            status_code=503,
            content={
                "error": "Frontend not available",
                "message": "React app is not built or static_dir is not configured.",
                "hint": "In development, ensure Vite dev server is running. "
                       "In production, build the React app and set static_dir parameter.",
                "static_dir": str(static_dir) if static_dir else None
            }
        )
    
    # Serve static assets (icons, etc.) from assets directory
    # Path: from tm_bot/webapp/api.py -> go up to zana_planner/ -> assets/
    assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
        logger.info(f"[DEBUG] Serving static assets from: {assets_dir}")
    else:
        logger.warning(f"[WARNING] Assets directory not found at: {assets_dir}")
    
    # Serve static files if directory is provided
    if static_dir and os.path.isdir(static_dir):
        logger.info(f"[VERSION_CHECK] v2.0 - Registering static file serving, static_dir={static_dir}")
        
        # Custom exception handler to serve static files or index.html
        from starlette.exceptions import HTTPException as StarletteHTTPException
        from starlette.requests import Request
        
        @app.exception_handler(StarletteHTTPException)
        async def custom_404_handler(request: Request, exc: StarletteHTTPException):
            """Handle 404s by checking for static files or serving index.html."""
            path = request.url.path
            
            # For API routes, return proper JSON error response
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail if hasattr(exc, 'detail') else "Error"}
                )
            
            # Only handle 404s for non-API routes
            if exc.status_code == 404:
                logger.info(f"[VERSION_CHECK] v2.0 - 404 handler for: {path}")
                
                # Handle paths that went through /assets mount - strip the /assets prefix
                # and check in dist/assets/ directory
                if path.startswith("/assets/"):
                    # This is a file request that went through the /assets mount
                    # Strip /assets/ prefix and check in dist/assets/
                    file_name = path[len("/assets/"):]
                    assets_file_path = os.path.join(static_dir, "assets", file_name)
                    if os.path.isfile(assets_file_path):
                        logger.info(f"[VERSION_CHECK] v2.0 - Serving static file from assets: {assets_file_path}")
                        if path.endswith('.js'):
                            return FileResponse(assets_file_path, media_type='application/javascript')
                        elif path.endswith('.css'):
                            return FileResponse(assets_file_path, media_type='text/css')
                        else:
                            return FileResponse(assets_file_path)
                    # If not found, continue to check root and serve index.html
                
                # Don't handle /assets root path (only /assets/...)
                if path == "/assets":
                    return JSONResponse(
                        status_code=exc.status_code,
                        content={"detail": exc.detail if hasattr(exc, 'detail') else "Not found"}
                    )
                
                # Check if it's a static file request in dist root (remove leading slash)
                file_path = os.path.join(static_dir, path.lstrip("/"))
                if os.path.isfile(file_path):
                    logger.info(f"[VERSION_CHECK] v2.0 - Serving static file: {file_path}")
                    if path.endswith('.js'):
                        return FileResponse(file_path, media_type='application/javascript')
                    elif path.endswith('.css'):
                        return FileResponse(file_path, media_type='text/css')
                    else:
                        return FileResponse(file_path)
                
                # Check in assets subdirectory
                assets_file_path = os.path.join(static_dir, "assets", path.lstrip("/"))
                if os.path.isfile(assets_file_path):
                    logger.info(f"[VERSION_CHECK] v2.0 - Serving static file from assets: {assets_file_path}")
                    if path.endswith('.js'):
                        return FileResponse(assets_file_path, media_type='application/javascript')
                    elif path.endswith('.css'):
                        return FileResponse(assets_file_path, media_type='text/css')
                    else:
                        return FileResponse(assets_file_path)
                
                # Otherwise serve index.html for SPA routing
                index_path = os.path.join(static_dir, "index.html")
                if os.path.exists(index_path):
                    logger.info(f"[VERSION_CHECK] v2.0 - Serving index.html for SPA route: {path}")
                    # Prevent caching of index.html to ensure users get latest version
                    response = FileResponse(index_path)
                    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                    response.headers["Pragma"] = "no-cache"
                    response.headers["Expires"] = "0"
                    return response
            
            # For non-404 errors on non-API routes, return JSON response
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail if hasattr(exc, 'detail') else "Error"}
            )
        
        # Keep the catch-all route as backup (though exception handler should catch it)
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            """Serve the React SPA - serves index.html for non-file routes."""
            logger.info(f"[VERSION_CHECK] v2.0 - Catch-all route hit for: {full_path}")
            # This should rarely be hit if exception handler works
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            index_path = os.path.join(static_dir, "index.html")
            if os.path.exists(index_path):
                # Prevent caching of index.html to ensure users get latest version
                response = FileResponse(index_path)
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                return response
            raise HTTPException(status_code=404, detail="Frontend not found")
    
    return app
