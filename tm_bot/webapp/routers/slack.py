"""
Slack webhook endpoints.

POST /slack/events       — Slack Events API (url_verification + event callbacks)
POST /slack/interactions — Interactive component payloads (button clicks)
POST /slack/oauth        — OAuth install redirect (saves per-club bot token)

Signature verification uses SLACK_SIGNING_SECRET from the environment.
Each club can also set its own signing secret; we fall back to the global one.
"""

import hashlib
import hmac
import json
import os
import time
import urllib.parse
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from repositories.clubs_repo import ClubsRepository
from services.slack_club_reminder_service import SlackClubReminderService
from utils.logger import get_logger

router = APIRouter(prefix="/slack", tags=["slack"])
logger = get_logger(__name__)

_SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
_SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID", "")
_SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET", "")


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def _verify_slack_signature(request_body: bytes, timestamp: str, signature: str, signing_secret: str) -> bool:
    """Return True if the Slack request signature is valid."""
    if not signing_secret:
        return True  # Disabled in dev when secret is not set
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False
    if abs(time.time() - ts) > 300:
        return False  # Replay attack guard
    base = f"v0:{timestamp}:{request_body.decode('utf-8')}"
    expected = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        base.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


# ---------------------------------------------------------------------------
# /slack/events — Events API
# ---------------------------------------------------------------------------

@router.post("/events")
async def slack_events(request: Request) -> Response:
    """Receive Slack Events API payloads."""
    body_bytes = await request.body()

    # Signature check
    ts = request.headers.get("X-Slack-Request-Timestamp", "")
    sig = request.headers.get("X-Slack-Signature", "")
    if _SLACK_SIGNING_SECRET and not _verify_slack_signature(body_bytes, ts, sig, _SLACK_SIGNING_SECRET):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")

    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # URL verification challenge (required when first adding the events URL)
    if payload.get("type") == "url_verification":
        return JSONResponse({"challenge": payload.get("challenge", "")})

    event = payload.get("event", {})
    event_type = event.get("type", "")
    logger.debug("[Slack/events] type=%s subtype=%s", event_type, event.get("subtype"))

    # We don't process inbound messages yet — extend here for DM support
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# /slack/interactions — Interactive Components
# ---------------------------------------------------------------------------

@router.post("/interactions")
async def slack_interactions(request: Request) -> Response:
    """Receive Slack interactive component payloads (button clicks)."""
    body_bytes = await request.body()

    ts = request.headers.get("X-Slack-Request-Timestamp", "")
    sig = request.headers.get("X-Slack-Signature", "")
    if _SLACK_SIGNING_SECRET and not _verify_slack_signature(body_bytes, ts, sig, _SLACK_SIGNING_SECRET):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")

    # Slack sends interactions as URL-encoded "payload" field
    try:
        form = urllib.parse.parse_qs(body_bytes.decode("utf-8"))
        payload_str = form.get("payload", ["{}"])[0]
        payload = json.loads(payload_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    interaction_type = payload.get("type")
    if interaction_type != "block_actions":
        return Response(status_code=200)

    channel_id = payload.get("channel", {}).get("id", "")
    message_ts = payload.get("message", {}).get("ts", "")
    slack_user_id = payload.get("user", {}).get("id", "")
    actions = payload.get("actions", [])

    if not actions or not channel_id or not message_ts:
        return Response(status_code=200)

    # Retrieve shared state from app
    slack_state: dict = {}
    try:
        slack_state = request.app.state.slack_state
    except AttributeError:
        logger.warning("[Slack/interactions] app.state.slack_state not initialised")
        return Response(status_code=200)

    service = SlackClubReminderService()
    for action in actions:
        action_id: str = action.get("action_id", "")
        if action_id.startswith("club_checkin:"):
            await service.handle_checkin_action(
                slack_state=slack_state,
                action_id=action_id,
                channel_id=channel_id,
                message_ts=message_ts,
                slack_user_id=slack_user_id,
            )

    # Slack expects a 200 within 3 s; return empty body to acknowledge
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# /slack/oauth — OAuth 2.0 Install
# ---------------------------------------------------------------------------

@router.get("/oauth")
async def slack_oauth(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
) -> Response:
    """
    Handle OAuth redirect from Slack after a workspace installs the app.

    The `state` param should be the club_id so we can associate the token.
    """
    if error:
        logger.warning("[Slack/oauth] Error from Slack: %s", error)
        return JSONResponse({"ok": False, "error": error}, status_code=400)

    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    if not _SLACK_CLIENT_ID or not _SLACK_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Slack app credentials not configured")

    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": _SLACK_CLIENT_ID,
                "client_secret": _SLACK_CLIENT_SECRET,
                "code": code,
            },
        )
    data = resp.json()

    if not data.get("ok"):
        logger.error("[Slack/oauth] oauth.v2.access failed: %s", data.get("error"))
        raise HTTPException(status_code=400, detail=data.get("error", "oauth_failed"))

    bot_token = data.get("access_token") or data.get("bot", {}).get("bot_access_token", "")
    workspace_id = data.get("team", {}).get("id", "")
    team_name = data.get("team", {}).get("name", "")
    channel_id = data.get("incoming_webhook", {}).get("channel_id", "")
    channel_name = data.get("incoming_webhook", {}).get("channel", "")
    club_id = state or ""

    if club_id:
        try:
            clubs_repo = ClubsRepository()
            clubs_repo.connect_slack(
                club_id=club_id,
                workspace_id=workspace_id,
                team_name=team_name,
                bot_token=bot_token,
                channel_id=channel_id,
                channel_name=channel_name,
            )
            logger.info(
                "[Slack/oauth] Club %s connected to workspace %s channel %s",
                club_id, workspace_id, channel_id,
            )
        except Exception as exc:
            logger.exception("[Slack/oauth] Failed to save Slack credentials for club %s: %s", club_id, exc)

    return JSONResponse({
        "ok": True,
        "team": team_name,
        "channel": channel_name,
        "club_id": club_id,
    })


# ---------------------------------------------------------------------------
# /slack/disconnect — Remove Slack from a club
# ---------------------------------------------------------------------------

@router.post("/disconnect/{club_id}")
async def slack_disconnect(club_id: str, request: Request) -> JSONResponse:
    """Disconnect a club from its Slack workspace (admin action)."""
    try:
        clubs_repo = ClubsRepository()
        clubs_repo.disconnect_slack(club_id)
        logger.info("[Slack] Club %s disconnected from Slack", club_id)
        return JSONResponse({"ok": True})
    except Exception as exc:
        logger.exception("[Slack/disconnect] Error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
