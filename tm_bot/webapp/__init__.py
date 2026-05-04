"""
Web App module for Telegram Mini App integration.
Provides FastAPI endpoints for the web frontend.
"""

from typing import Any

__all__ = ["create_webapp_api"]


def create_webapp_api(*args: Any, **kwargs: Any):
    """
    Lazy import to avoid pulling full webapp dependencies at package import time.
    """
    from webapp.api import create_webapp_api as _create_webapp_api

    return _create_webapp_api(*args, **kwargs)
