#!/usr/bin/env python3
"""
FastAPI webapp module for running with uvicorn.

Usage:
    uvicorn run_webapp_local:app --host 0.0.0.0 --port 8080

Environment Variables:
    ROOT_DIR: Root directory for user data (default: ./USERS_DATA_DIR)
    TELEGRAM_BOT_TOKEN: Telegram bot token (required for auth validation)
"""

# import os
# import sys
# from pathlib import Path
#
# # Add tm_bot to path
# sys.path.insert(0, str(Path(__file__).parent / "tm_bot"))
#
# from webapp.api import create_webapp_api
# from utils.logger import get_logger
#
# logger = get_logger(__name__)
#
# # Get configuration from environment
# root_dir = os.getenv("ROOT_DIR", str(Path(__file__).parent / "USERS_DATA_DIR"))
# bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "dummy_token_for_local_testing")
#
# # Convert to absolute path
# root_dir = os.path.abspath(root_dir)
#
# # Create FastAPI app instance (exposed for uvicorn)
# app = create_webapp_api(
#     root_dir=root_dir,
#     bot_token=bot_token,
#     static_dir=None  # Frontend runs on Vite dev server
# )
#
# logger.info("Zana Web App API module loaded")
# logger.info(f"  Root directory: {root_dir}")
# logger.info(f"  API docs: http://localhost:8080/api/docs")
# logger.info(f"  Public users: http://localhost:8080/api/public/users")

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.get("/")
def read_root():
    return HTMLResponse("<h1>Hello World</h1><p>This is FastAPI running</p>")
