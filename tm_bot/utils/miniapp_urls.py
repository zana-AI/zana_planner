"""Authenticated Mini App URLs for Telegram inline keyboards.

Telegram Desktop occasionally opens an inline ``web_app`` without providing
``Telegram.WebApp.initData``.  A normal web session is therefore minted for
the known callback recipient and placed in the URL fragment.  Fragments never
reach the server or its access logs; the frontend consumes the token before it
makes its first API request.
"""

from __future__ import annotations

import time
from typing import Mapping
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from repositories.auth_session_repo import AuthSessionRepository


def authenticated_miniapp_url(
    miniapp_url: str,
    user_id: int,
    path: str,
    query: Mapping[str, str] | None = None,
) -> str:
    """Build an authenticated, user-specific Mini App URL.

    The session deliberately lasts one day: a Telegram message can be opened
    later, while the fragment keeps the bearer token out of HTTP requests.
    """
    session = AuthSessionRepository().create_session(
        user_id=user_id,
        telegram_auth_date=int(time.time()),
        expires_in_days=1,
        auth_method="inline_web_app",
    )
    base = miniapp_url.rstrip("/")
    parsed = urlparse(f"{base}/{path.lstrip('/')}")
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params.update({key: value for key, value in (query or {}).items() if value})
    return urlunparse(parsed._replace(
        query=urlencode(params),
        fragment=urlencode({"session_token": session.session_token}),
    ))
