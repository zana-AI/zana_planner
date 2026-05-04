"""
API routers for the webapp.
"""

from importlib import import_module
from types import ModuleType

__all__ = [
    "health",
    "auth",
    "users",
    "promises",
    "templates",
    "distractions",
    "admin",
    "community",
    "focus_timer",
    "youtube_watch",
    "content",
    "plan_sessions",
]


def __getattr__(name: str) -> ModuleType:
    if name in __all__:
        return import_module(f"{__name__}.{name}")
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
