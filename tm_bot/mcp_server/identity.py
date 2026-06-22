"""Resolve the Zana user_id for a request and bind it for tools.

Because Hydra authenticates via Telegram and sets the token subject to the
Telegram user_id, the validated subject *is* the Zana user_id — no account-link
table, no linking step. Adapter tools resolve their ``user_id`` from the
``_current_user_id`` context var; ``bind_current_user`` sets it per call:

- Auth enabled: ``user_id = access_token.subject``.
- Auth disabled (local/dev): fall back to ``MCP_DEFAULT_USER_ID``.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Optional

from mcp.server.auth.middleware.auth_context import get_access_token

from llms.tool_wrappers import _current_user_id

from .config import config


def resolve_user_id_or_none() -> Optional[str]:
    token = get_access_token()
    if token is not None and token.subject:
        return token.subject  # Hydra subject == Telegram user_id
    # No auth context -> single-user fallback (do not expose this mode publicly).
    if config.default_user_id:
        return config.default_user_id
    return None


@contextmanager
def bind_current_user():
    user_id = resolve_user_id_or_none()
    if user_id is None:
        raise ValueError("No authenticated user for this request.")
    token = _current_user_id.set(str(user_id))
    try:
        yield user_id
    finally:
        _current_user_id.reset(token)
