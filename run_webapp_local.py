#!/usr/bin/env python3
"""
Simple script to run the FastAPI webapp locally for testing.

Usage:
    python run_webapp_local.py

Environment Variables:
    ROOT_DIR: Root directory for user data (default: ./USERS_DATA_DIR)
    TELEGRAM_BOT_TOKEN: Telegram bot token (required for auth validation)
    PORT: Server port (default: 8080)
"""

import os
import sys
from pathlib import Path

# Add tm_bot to path
sys.path.insert(0, str(Path(__file__).parent / "tm_bot"))

import uvicorn
from webapp.api import create_webapp_api
from utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Run the webapp API server locally."""
    # Get configuration
    root_dir = os.getenv("ROOT_DIR", str(Path(__file__).parent / "USERS_DATA_DIR"))
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "dummy_token_for_local_testing")
    port = int(os.getenv("PORT", "8080"))
    
    # Convert to absolute path
    root_dir = os.path.abspath(root_dir)
    
    logger.info("Starting Zana Web App API server...")
    logger.info(f"  Root directory: {root_dir}")
    logger.info(f"  Port: {port}")
    logger.info(f"  URL: http://localhost:{port}")
    logger.info(f"  API docs: http://localhost:{port}/api/docs")
    logger.info(f"  Public users: http://localhost:{port}/api/public/users")
    
    # Create FastAPI app (no static files for dev - frontend runs separately)
    app = create_webapp_api(
        root_dir=root_dir,
        bot_token=bot_token,
        static_dir=None  # Frontend runs on Vite dev server
    )
    
    # Run server
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            reload=False,  # Set to True for auto-reload on code changes
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Error starting server: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

