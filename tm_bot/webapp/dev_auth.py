"""
Development-only authentication helpers for local webapp testing.
"""

import os
from typing import Final

from dotenv import load_dotenv

load_dotenv()

_ENABLED_VALUES: Final[set[str]] = {"1", "true", "yes", "on"}
_PRODUCTION_ENVIRONMENTS: Final[set[str]] = {"prod", "production"}
_DEFAULT_DEV_ADMIN_USER_ID: Final[int] = 900000001


def is_dev_auth_enabled() -> bool:
    """Return True when local development auth is explicitly enabled."""
    environment = os.getenv("ENVIRONMENT", "").strip().lower()
    if environment in _PRODUCTION_ENVIRONMENTS:
        return False

    enabled = os.getenv("WEBAPP_DEV_AUTH_ENABLED", "").strip().lower()
    return enabled in _ENABLED_VALUES


def get_dev_admin_user_id() -> int:
    """Return the synthetic admin user id used by the dev auth flow."""
    raw_user_id = os.getenv("WEBAPP_DEV_ADMIN_USER_ID", str(_DEFAULT_DEV_ADMIN_USER_ID)).strip()
    try:
        return int(raw_user_id)
    except ValueError:
        return _DEFAULT_DEV_ADMIN_USER_ID


def is_dev_admin_user(user_id: int) -> bool:
    """Return True when the supplied user id is the enabled synthetic admin."""
    return is_dev_auth_enabled() and int(user_id) == get_dev_admin_user_id()
