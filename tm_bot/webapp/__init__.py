"""
Web App module for Telegram Mini App integration.
Provides FastAPI endpoints for the web frontend.
"""

from webapp.api import create_webapp_api

__all__ = ["create_webapp_api"]
