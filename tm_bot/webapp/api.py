"""
FastAPI web application for Telegram Mini App.
Provides API endpoints for the React frontend.
"""

import os
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from webapp.auth import validate_telegram_init_data, extract_user_id
from services.reports import ReportsService
from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from repositories.settings_repo import SettingsRepository
from db.sqlite_db import connection_for_root
from utils.time_utils import get_week_range
from utils.logger import get_logger


logger = get_logger(__name__)


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
    last_seen_utc: Optional[str] = None


class PublicUsersResponse(BaseModel):
    """Response model for public users endpoint."""
    users: List[PublicUser]
    total: int


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
        title="Zana AI Web App",
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
            "https://zana-ai.com",
            "https://www.zana-ai.com",
            "http://zana-ai.com",  # Allow HTTP during initial setup
            "http://www.zana-ai.com",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Store config in app state
    app.state.root_dir = root_dir
    app.state.bot_token = bot_token
    
    # Dependency to validate Telegram auth and get user_id
    async def get_current_user(
        x_telegram_init_data: Optional[str] = Header(None, alias="X-Telegram-Init-Data"),
        authorization: Optional[str] = Header(None),
    ) -> int:
        """
        Validate Telegram initData and return user_id.
        Accepts initData in either X-Telegram-Init-Data header or Authorization header.
        """
        init_data = x_telegram_init_data
        
        # Also check Authorization header (Bearer <initData>)
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
        return ReportsService(promises_repo, actions_repo)
    
    def get_settings_repo() -> SettingsRepository:
        """Get SettingsRepository instance."""
        return SettingsRepository(app.state.root_dir)
    
    @app.get("/")
    async def root():
        """Static landing page or serve React app if static_dir is set."""
        # If static_dir is set, serve the React app
        if static_dir and os.path.isdir(static_dir):
            index_path = os.path.join(static_dir, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
        
        # Otherwise, serve static landing page
        from fastapi.responses import HTMLResponse
        
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Zana AI - Your Personal Planning Assistant</title>
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
                <h1>✨ Zana AI</h1>
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
            # Get user timezone
            settings_repo = get_settings_repo()
            settings = settings_repo.get_settings(user_id)
            user_tz = settings.timezone if settings else "UTC"
            
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
                week_start=week_start.isoformat(),
                week_end=week_end.isoformat(),
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
                language=settings.language if settings else "en"
            )
        except Exception as e:
            logger.exception(f"Error getting user info for user {user_id}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/public/users", response_model=PublicUsersResponse)
    async def get_public_users(limit: int = Query(default=20, ge=1, le=100)):
        """
        Get public list of most active users (no authentication required).
        
        Args:
            limit: Maximum number of users to return (1-100, default: 20)
        
        Returns:
            List of public user information ranked by activity
        """
        try:
            logger.info(f"Getting public users, limit={limit}")
            root_dir = app.state.root_dir
            logger.info(f"Root dir: {root_dir}")
            if not root_dir:
                raise HTTPException(status_code=500, detail="Server configuration error: root_dir not set")
            
            logger.info("Opening database connection...")
            with connection_for_root(root_dir) as conn:
                logger.info("Executing query...")
                # Query users with activity count from last 30 days
                rows = conn.execute(
                    """
                    SELECT 
                        u.user_id,
                        u.first_name,
                        u.last_name,
                        u.display_name,
                        u.username,
                        u.avatar_path,
                        u.avatar_file_unique_id,
                        u.last_seen_utc,
                        COALESCE(activity.activity_count, 0) as activity_count
                    FROM users u
                    LEFT JOIN (
                        SELECT user_id, COUNT(*) as activity_count
                        FROM (
                            SELECT user_id, at_utc FROM actions 
                            WHERE at_utc >= datetime('now', '-30 days')
                            UNION ALL
                            SELECT user_id, started_at_utc as at_utc FROM sessions 
                            WHERE started_at_utc >= datetime('now', '-30 days')
                        ) recent_activity
                        GROUP BY user_id
                    ) activity ON u.user_id = activity.user_id
                    WHERE (u.avatar_visibility = 'public' OR u.avatar_visibility IS NULL)
                    ORDER BY activity_count DESC, u.last_seen_utc DESC NULLS LAST
                    LIMIT ?;
                    """,
                    (limit,),
                ).fetchall()
                
                users = []
                for row in rows:
                    users.append(
                        PublicUser(
                            user_id=str(row["user_id"]),
                            first_name=row["first_name"],
                            last_name=row["last_name"],
                            display_name=row["display_name"],
                            username=row["username"],
                            avatar_path=row["avatar_path"],
                            avatar_file_unique_id=row["avatar_file_unique_id"],
                            activity_count=int(row["activity_count"] or 0),
                            last_seen_utc=row["last_seen_utc"],
                        )
                    )
                
                logger.info(f"Found {len(users)} users")
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
                return FileResponse(index_path)
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
        # Note: Vite builds JS/CSS files in dist root (e.g., index-*.js, index-*.css)
        # and other assets in dist/assets/ subdirectory
        # The catch-all route below will serve files from dist root
        
        # Catch-all route for SPA - must be last, serves files or index.html
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            """Serve the React SPA - serves static files if they exist, otherwise index.html."""
            logger.info(f"[VERSION_CHECK] v2.0 - Catch-all route hit for: {full_path}")
            # Don't serve for API routes (handled by other routes)
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            
            # Don't serve for /assets (handled by assets mount above)
            if full_path == "assets" or full_path.startswith("assets/"):
                raise HTTPException(status_code=404, detail="Not found")
            
            # Check if the requested path is a file that exists in dist root
            file_path = os.path.join(static_dir, full_path)
            logger.info(f"[VERSION_CHECK] v2.0 - SPA route requested: {full_path}, checking file: {file_path}")
            
            # If not found in root, check in assets subdirectory (Vite builds files there)
            if not os.path.isfile(file_path):
                assets_file_path = os.path.join(static_dir, "assets", full_path)
                logger.info(f"[VERSION_CHECK] v2.0 - File not in root, checking assets subdirectory: {assets_file_path}")
                if os.path.isfile(assets_file_path):
                    file_path = assets_file_path
                    logger.info(f"[VERSION_CHECK] v2.0 - Found file in assets subdirectory: {file_path}")
                else:
                    logger.warning(f"[VERSION_CHECK] v2.0 - File not found in root or assets: {file_path}")
            
            if os.path.isfile(file_path):
                # Serve the actual file (JS, CSS, etc. from dist root)
                logger.debug(f"[DEBUG] Serving static file: {file_path}")
                # Determine MIME type based on extension
                if full_path.endswith('.js'):
                    return FileResponse(file_path, media_type='application/javascript')
                elif full_path.endswith('.css'):
                    return FileResponse(file_path, media_type='text/css')
                elif full_path.endswith('.map'):
                    return FileResponse(file_path, media_type='application/json')
                else:
                    return FileResponse(file_path)
            
            # Otherwise, serve index.html for SPA routing
            index_path = os.path.join(static_dir, "index.html")
            logger.debug(f"[DEBUG] File not found, serving index.html for SPA routing")
            if os.path.exists(index_path):
                return FileResponse(index_path)
            raise HTTPException(status_code=404, detail="Frontend not found")
    
    return app
