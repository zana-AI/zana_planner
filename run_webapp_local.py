#!/usr/bin/env python3
"""
FastAPI webapp module for running with uvicorn.

Usage:
    uvicorn run_webapp_local:app --host 0.0.0.0 --port 8080

Environment Variables:
    ROOT_DIR: Root directory for user data (default: ./USERS_DATA_DIR)
    TELEGRAM_BOT_TOKEN: Telegram bot token (required for auth validation)
    MINIAPP_URL: URL for the mini app (default: https://xaana.club)
"""

import os
import sys
import traceback
from pathlib import Path

# Add tm_bot to path
try:
    sys.path.insert(0, str(Path(__file__).parent / "tm_bot"))
    print(f"[DEBUG] Added tm_bot to path: {Path(__file__).parent / 'tm_bot'}")
except Exception as e:
    print(f"[ERROR] Failed to add tm_bot to path: {e}")
    traceback.print_exc()
    sys.exit(1)

# Import webapp API with error handling
try:
    from webapp.api import create_webapp_api
    print("[DEBUG] Successfully imported create_webapp_api")
except ImportError as e:
    print(f"[ERROR] Failed to import create_webapp_api: {e}")
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f"[ERROR] Unexpected error importing create_webapp_api: {e}")
    traceback.print_exc()
    sys.exit(1)

# Import logger with error handling
try:
    from utils.logger import get_logger
    logger = get_logger(__name__)
    print("[DEBUG] Successfully initialized logger")
except Exception as e:
    print(f"[WARNING] Failed to initialize logger: {e}")
    # Fallback to basic logging
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

# Get configuration from environment with error handling
try:
    root_dir = os.getenv("ROOT_DIR", str(Path(__file__).parent / "USERS_DATA_DIR"))
    logger.info(f"[DEBUG] ROOT_DIR from env: {os.getenv('ROOT_DIR', 'NOT SET')}")
    logger.info(f"[DEBUG] Using root_dir: {root_dir}")
    
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.warning("[WARNING] TELEGRAM_BOT_TOKEN/BOT_TOKEN not set, using dummy token for local testing")
        bot_token = "dummy_token_for_local_testing"
    else:
        logger.info("[DEBUG] Bot token found in environment")
    
    # Convert to absolute path
    root_dir = os.path.abspath(root_dir)
    logger.info(f"[DEBUG] Absolute root_dir: {root_dir}")
    
    # Verify root_dir exists or create it
    if not os.path.exists(root_dir):
        logger.warning(f"[WARNING] Root directory does not exist: {root_dir}, creating it...")
        try:
            os.makedirs(root_dir, exist_ok=True)
            logger.info(f"[DEBUG] Created root directory: {root_dir}")
        except Exception as e:
            logger.error(f"[ERROR] Failed to create root directory: {e}")
            traceback.print_exc()
            raise
    
    # Try to find built React app
    static_dir = None
    possible_static_dirs = [
        os.path.join(Path(__file__).parent, "webapp_frontend", "dist"),
        os.path.join(Path(__file__).parent, "tm_bot", "..", "webapp_frontend", "dist"),
    ]
    
    for possible_dir in possible_static_dirs:
        abs_dir = os.path.abspath(possible_dir)
        if os.path.isdir(abs_dir) and os.path.exists(os.path.join(abs_dir, "index.html")):
            static_dir = abs_dir
            logger.info(f"[DEBUG] Found built React app at: {static_dir}")
            break
    
    if not static_dir:
        logger.warning("[WARNING] Built React app not found. Tried:")
        for possible_dir in possible_static_dirs:
            logger.warning(f"  - {os.path.abspath(possible_dir)}")
        logger.warning("[WARNING] Frontend will not be served. Use Vite dev server or build the React app.")
    else:
        logger.info(f"[DEBUG] Using static_dir: {static_dir}")
    
    # Create FastAPI app instance with error handling
    logger.info("[DEBUG] Creating FastAPI app instance...")
    try:
        app = create_webapp_api(
            root_dir=root_dir,
            bot_token=bot_token,
            static_dir=static_dir  # Use built React app if found, otherwise None
        )
        logger.info("[DEBUG] FastAPI app instance created successfully")
    except Exception as e:
        logger.error(f"[ERROR] Failed to create FastAPI app: {e}")
        traceback.print_exc()
        raise
    
    logger.info("=" * 60)
    logger.info("Xaana Web App API module loaded successfully")
    logger.info(f"  Root directory: {root_dir}")
    logger.info(f"  API docs: http://localhost:8080/api/docs")
    logger.info(f"  Public users: http://localhost:8080/api/public/users")
    logger.info(f"  Health check: http://localhost:8080/api/health")
    logger.info("=" * 60)
    
except Exception as e:
    logger.error(f"[FATAL] Failed to initialize webapp: {e}")
    traceback.print_exc()
    # Create a minimal error app so uvicorn doesn't crash
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    
    app = FastAPI()
    
    @app.get("/")
    async def error_root():
        return JSONResponse(
            status_code=500,
            content={
                "error": "Webapp initialization failed",
                "message": str(e),
                "details": traceback.format_exc()
            }
        )
    
    @app.get("/api/health")
    async def error_health():
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Webapp initialization failed"}
        )
    
    logger.error("[FATAL] Running in error mode - check logs for details")
