"""Map an authenticated request to a Zana user_id, and bind it for tools.

This is the bridge between OAuth identity (a WorkOS subject) and Zana's existing
Telegram-based identity. Adapter tools resolve their ``user_id`` from the
``_current_user_id`` context var; ``bind_current_user`` sets it for the duration
of a tool call:

- Auth enabled: read the validated access token's subject, look up the linked
  Zana user_id (account-link table). No link yet -> raise AccountNotLinkedError
  with instructions to link.
- Auth disabled (local/dev): fall back to ``MCP_DEFAULT_USER_ID``.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Optional

from mcp.server.auth.middleware.auth_context import get_access_token

from llms.tool_wrappers import _current_user_id
from repositories.mcp_links_repo import McpLinksRepository

from .config import config

_links = McpLinksRepository()


class AccountNotLinkedError(Exception):
    """Authenticated, but the OAuth identity isn't linked to a Zana account yet."""


def current_subject() -> Optional[str]:
    token = get_access_token()
    return token.subject if token is not None else None


def resolve_user_id_or_none() -> Optional[str]:
    token = get_access_token()
    if token is not None and token.subject:
        return _links.get_user_id_for_subject(config.workos_issuer or "", token.subject)
    # No auth context -> Phase 1 fallback (do not expose this mode publicly).
    if config.default_user_id:
        return config.default_user_id
    return None


@contextmanager
def bind_current_user():
    user_id = resolve_user_id_or_none()
    if user_id is None:
        if current_subject() is not None:
            raise AccountNotLinkedError(
                "Your AI account isn't linked to a Xaana account yet. Open Xaana in "
                "Telegram, get a link code, then call `link_account` with that code."
            )
        raise ValueError("No authenticated user for this request.")
    token = _current_user_id.set(str(user_id))
    try:
        yield user_id
    finally:
        _current_user_id.reset(token)
