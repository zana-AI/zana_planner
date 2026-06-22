"""Per-request identity for the MCP server.

This is the seam between transport auth and the adapter's per-user scoping. Every
adapter tool resolves its ``user_id`` from the ``_current_user_id`` context var
(the same one the LLM path uses, via ``llms.tool_wrappers``). This middleware is
responsible for setting that context var for the duration of each HTTP request.

Phase 1 (current): single-user stub — it sets the context var to
``MCP_DEFAULT_USER_ID`` so the server is fully testable with the MCP Inspector
before any OAuth exists.

Phase 2: replace ``_resolve_user_id`` with WorkOS token validation — read the
``Authorization: Bearer`` header, validate the access token against WorkOS, map
the OAuth subject to a Zana ``user_id`` via the account-linking table, and return
that. The rest of the server does not change.
"""

from __future__ import annotations

import os
from typing import Optional

from llms.tool_wrappers import _current_user_id
from utils.logger import get_logger

logger = get_logger(__name__)


def _resolve_user_id(scope) -> Optional[str]:
    """Return the Zana user_id for this request, or None if unauthenticated.

    PHASE 1 STUB: returns the configured default user. Replace the body in Phase 2
    with bearer-token validation + OAuth-subject -> user_id lookup.
    """
    default_user = os.getenv("MCP_DEFAULT_USER_ID")
    if default_user:
        return str(default_user).strip()
    return None


class CurrentUserMiddleware:
    """ASGI middleware that binds the resolved user_id to the request context.

    Sets ``_current_user_id`` before delegating to the MCP app and resets it
    afterward. Because tools run within the same request task (sync tools are run
    via ``anyio.to_thread``, which copies the context), they observe the value.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        user_id = _resolve_user_id(scope)
        if user_id is None:
            token = None
        else:
            token = _current_user_id.set(user_id)
        try:
            await self.app(scope, receive, send)
        finally:
            if token is not None:
                _current_user_id.reset(token)
