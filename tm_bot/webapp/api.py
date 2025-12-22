"""
FastAPI web application for Telegram Mini App.
Provides API endpoints for the React frontend.
"""

import os
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from webapp.auth import validate_telegram_init_data, extract_user_id
from services.reports import ReportsService
from repositories.promises_repo import PromisesRepository
from repositories.actions_repo import ActionsRepository
from repositories.settings_repo import SettingsRepository
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
    
    # CORS middleware for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:3000",
            "https://web.telegram.org",
            "https://*.telegram.org",
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
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid ref_time format")
            else:
                import pytz
                tz = pytz.timezone(user_tz)
                reference_time = datetime.now(tz)
            
            # Get weekly summary
            reports_service = get_reports_service(user_id)
            summary = reports_service.get_weekly_summary_with_sessions(user_id, reference_time)
            
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
    
    # Serve static files if directory is provided
    if static_dir and os.path.isdir(static_dir):
        # Mount static files
        app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")
        
        # Catch-all route for SPA - must be last
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            """Serve the React SPA for all non-API routes."""
            # Don't serve index.html for API routes
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            
            index_path = os.path.join(static_dir, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
            raise HTTPException(status_code=404, detail="Frontend not found")
    
    return app
