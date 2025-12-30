#!/usr/bin/env python3
"""
Run FastAPI bot server.

This script creates and runs a FastAPI server with bot interaction endpoints
for Telegram Mini App integration.

Usage:
    python -m tm_bot.platforms.fastapi.run_server
    
Environment Variables:
    ROOT_DIR: Root directory for user data (default: /tmp/zana_data)
    TELEGRAM_BOT_TOKEN: Telegram bot token (required)
    STATIC_DIR: Optional path to static files directory
    HOST: Server host (default: 0.0.0.0)
    PORT: Server port (default: 8000)
"""

import os
import sys
import uvicorn
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from platforms.fastapi import create_bot_api
from utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Main entry point."""
    # Get configuration from environment
    root_dir = os.getenv("ROOT_DIR", "/tmp/zana_data")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    static_dir = os.getenv("STATIC_DIR", None)
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    
    # Validate required config
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is required")
        sys.exit(1)
    
    # Create data directory if it doesn't exist
    os.makedirs(root_dir, exist_ok=True)
    
    logger.info(f"Starting FastAPI bot server...")
    logger.info(f"  Root directory: {root_dir}")
    logger.info(f"  Static directory: {static_dir or 'None'}")
    logger.info(f"  Host: {host}")
    logger.info(f"  Port: {port}")
    
    try:
        # Create FastAPI app
        app = create_bot_api(
            root_dir=root_dir,
            bot_token=bot_token,
            static_dir=static_dir,
        )
        
        # Run server
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Error starting server: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


