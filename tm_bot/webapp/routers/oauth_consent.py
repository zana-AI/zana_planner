"""Telegram login + consent app for Ory Hydra.

Hydra (the OAuth authorization server) delegates the actual user authentication to
this app via its login/consent flow. We authenticate the user with the **Telegram
Login Widget**, validate its HMAC signature with the bot token, and tell Hydra to
issue tokens whose ``subject`` is the Telegram user_id — so the MCP server's token
subject is already the Zana user_id (no account linking).

Flow (browser, driven by Claude/ChatGPT):
  Hydra /oauth2/auth
    -> GET  /api/oauth/login?login_challenge=...      (this app shows the widget)
    -> GET  /api/oauth/login/callback?...             (Telegram redirects here)
         validate HMAC -> Hydra accept-login(subject=tg_id) -> redirect back
    -> GET  /api/oauth/consent?consent_challenge=...   (auto-grant, first-party)
    -> back to the client with an authorization code.

Endpoints are unauthenticated by themselves (that's expected for an OAuth login
app): trust comes from the Hydra challenge + the Telegram HMAC.
"""

import hashlib
import hmac
import os
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from utils.logger import get_logger

router = APIRouter(prefix="/api", tags=["oauth"])
logger = get_logger(__name__)

_AUTH_DATE_MAX_AGE = 86400  # reject Telegram auth payloads older than 1 day


def _hydra_admin() -> str:
    return os.getenv("HYDRA_ADMIN_URL", "http://hydra:4445").rstrip("/")


def _bot_token(request: Request) -> str:
    return (
        getattr(request.app.state, "bot_token", "")
        or os.getenv("BOT_TOKEN")
        or os.getenv("TELEGRAM_BOT_TOKEN")
        or ""
    )


def _bot_username(request: Request) -> str:
    return getattr(request.app.state, "bot_username", "") or os.getenv("BOT_USERNAME", "")


def _public_base() -> str:
    return os.getenv("MINIAPP_URL", "https://xaana.club").rstrip("/")


def _verify_telegram_auth(params: dict, bot_token: str) -> Optional[str]:
    """Validate a Telegram Login Widget payload. Returns the user id or None."""
    received_hash = params.get("hash")
    if not received_hash or not bot_token:
        return None
    pairs = sorted(f"{k}={v}" for k, v in params.items() if k != "hash")
    data_check_string = "\n".join(pairs)
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None
    try:
        if time.time() - int(params.get("auth_date", "0")) > _AUTH_DATE_MAX_AGE:
            return None
    except (TypeError, ValueError):
        return None
    user_id = params.get("id")
    return str(user_id) if user_id else None


async def _hydra_get(path: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{_hydra_admin()}{path}", params=params)
        resp.raise_for_status()
        return resp.json()


async def _hydra_put(path: str, params: dict, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.put(f"{_hydra_admin()}{path}", params=params, json=body)
        resp.raise_for_status()
        return resp.json()


@router.get("/oauth/login", response_class=HTMLResponse)
async def oauth_login(request: Request, login_challenge: str):
    # If Hydra says the user is already authenticated, accept immediately.
    info = await _hydra_get("/admin/oauth2/auth/requests/login", {"login_challenge": login_challenge})
    if info.get("skip"):
        accepted = await _hydra_put(
            "/admin/oauth2/auth/requests/login/accept",
            {"login_challenge": login_challenge},
            {"subject": str(info.get("subject", "")), "remember": True, "remember_for": 3600},
        )
        return RedirectResponse(accepted["redirect_to"])

    bot_username = _bot_username(request)
    if not bot_username:
        raise HTTPException(status_code=500, detail="BOT_USERNAME not configured for Telegram login.")
    auth_url = f"{_public_base()}/api/oauth/login/callback?login_challenge={login_challenge}"
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connect Xaana</title>
<style>body{{font-family:system-ui,sans-serif;display:flex;flex-direction:column;align-items:center;
justify-content:center;height:100vh;margin:0;background:#f4f1ea;color:#222}}
h1{{font-weight:600}} p{{color:#555}}</style></head>
<body>
  <h1>Connect Xaana to your AI assistant</h1>
  <p>Log in with Telegram to authorize access to your promises.</p>
  <script async src="https://telegram.org/js/telegram-widget.js?22"
    data-telegram-login="{bot_username}"
    data-size="large"
    data-auth-url="{auth_url}"
    data-request-access="write"></script>
</body></html>"""
    return HTMLResponse(html)


@router.get("/oauth/login/callback")
async def oauth_login_callback(request: Request, login_challenge: str):
    params = {k: v for k, v in request.query_params.items() if k != "login_challenge"}
    user_id = _verify_telegram_auth(params, _bot_token(request))
    if not user_id:
        raise HTTPException(status_code=403, detail="Telegram authentication failed.")
    accepted = await _hydra_put(
        "/admin/oauth2/auth/requests/login/accept",
        {"login_challenge": login_challenge},
        {"subject": user_id, "remember": True, "remember_for": 3600},
    )
    return RedirectResponse(accepted["redirect_to"])


@router.get("/oauth/consent")
async def oauth_consent(request: Request, consent_challenge: str):
    # First-party auto-consent: the user explicitly added this connector, so grant
    # the requested scopes without a separate approval screen.
    info = await _hydra_get("/admin/oauth2/auth/requests/consent", {"consent_challenge": consent_challenge})
    accepted = await _hydra_put(
        "/admin/oauth2/auth/requests/consent/accept",
        {"consent_challenge": consent_challenge},
        {
            "grant_scope": info.get("requested_scope", []),
            "grant_access_token_audience": info.get("requested_access_token_audience", []),
            "remember": True,
            "remember_for": 3600,
            "session": {},
        },
    )
    return RedirectResponse(accepted["redirect_to"])


@router.get("/oauth/logout")
async def oauth_logout(request: Request, logout_challenge: str):
    accepted = await _hydra_put(
        "/admin/oauth2/auth/requests/logout/accept",
        {"logout_challenge": logout_challenge},
        {},
    )
    return RedirectResponse(accepted["redirect_to"])
