"""
FastAPI platform adapter for Telegram Mini App.

This module provides a FastAPI-based platform adapter that enables
the bot to work through HTTP/WebSocket APIs for Telegram Mini Apps.
"""

from .adapter import FastAPIPlatformAdapter
from .response_service import FastAPIResponseService
from .api_extensions import create_bot_api, add_bot_routes

__all__ = [
    'FastAPIPlatformAdapter',
    'FastAPIResponseService',
    'create_bot_api',
    'add_bot_routes',
]


