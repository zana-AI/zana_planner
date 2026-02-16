"""
FastAPI web application for Telegram Mini App.
Provides API endpoints for the React frontend.
"""

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from repositories.auth_session_repo import AuthSessionRepository
from utils.logger import get_logger

# Import all routers
from .routers import health, auth, users, promises, templates, distractions, admin, community, focus_timer

logger = get_logger(__name__)


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
    delayed_message_service = DelayedMessageService(scheduler)
    app.state.delayed_message_service = delayed_message_service
    
    # Include all routers
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(promises.router)
    app.include_router(templates.router)
    app.include_router(distractions.router)
    app.include_router(admin.router)
    app.include_router(community.router)
    app.include_router(focus_timer.router)
    
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
        
        # Start background task for focus timer completion notifications
        async def focus_timer_sweeper():
            """Periodically check for overdue focus sessions and send Telegram notifications."""
            from repositories.sessions_repo import SessionsRepository
            from webapp.notifications import send_focus_finished_notification
            import os
            
            while True:
                try:
                    await asyncio.sleep(30)  # Check every 30 seconds
                    
                    sessions_repo = SessionsRepository()
                    overdue_sessions = sessions_repo.list_overdue_sessions_needing_notification()
                    
                    if overdue_sessions:
                        logger.info(f"Found {len(overdue_sessions)} overdue focus session(s) needing notification")
                    else:
                        # Log occasionally to confirm sweeper is running (every 5 minutes)
                        import time
                        if int(time.time()) % 300 < 30:  # Log roughly every 5 minutes
                            logger.debug("Focus timer sweeper running - no overdue sessions found")
                    
                    for session in overdue_sessions:
                        try:
                            logger.info(f"Processing overdue session {session.session_id} for user {session.user_id}, "
                                      f"expected_end: {session.expected_end_utc}, "
                                      f"planned_duration: {session.planned_duration_minutes} minutes")
                            
                            # Mark as notified first to avoid duplicate sends
                            sessions_repo.mark_session_notified(session.session_id)
                            
                            # Get promise text
                            from repositories.promises_repo import PromisesRepository
                            promises_repo = PromisesRepository()
                            promise = promises_repo.get_promise(int(session.user_id), session.promise_id)
                            promise_text = promise.text if promise else f"Promise #{session.promise_id}"
                            
                            # Calculate proposed hours
                            proposed_hours = (session.planned_duration_minutes or 25) / 60.0
                            
                            # Send notification
                            miniapp_url = os.getenv("MINIAPP_URL", "https://xaana.club")
                            logger.info(f"Sending focus completion notification to user {session.user_id} for session {session.session_id}")
                            await send_focus_finished_notification(
                                bot_token=bot_token,
                                user_id=int(session.user_id),
                                session_id=session.session_id,
                                promise_text=promise_text,
                                proposed_hours=proposed_hours,
                                miniapp_url=miniapp_url,
                            )
                            
                            logger.info(f"✓ Successfully sent focus completion notification for session {session.session_id} to user {session.user_id}")
                        except Exception as e:
                            logger.error(f"❌ FAILED to send focus notification for session {session.session_id} to user {session.user_id}: {e}", exc_info=True)
                            # Note: Session is already marked as notified, so it won't retry
                            # This is intentional to avoid spam, but means failed notifications won't retry
                            
                except Exception as e:
                    logger.error(f"Error in focus timer sweeper: {e}", exc_info=True)
                    await asyncio.sleep(60)  # Wait longer on error
        
        asyncio.create_task(focus_timer_sweeper())
        logger.info("✓ Started focus timer completion sweeper (checks every 30 seconds)")
    
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
