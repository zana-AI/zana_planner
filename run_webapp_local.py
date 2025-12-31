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
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Zana AI - Your Personal Planning Assistant</title>
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
            
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
