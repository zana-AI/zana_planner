"""Add a chosen Xaana session to the user's primary Google Calendar.

Authorization is requested in context for a single event. OAuth access tokens
are used for that request and discarded; Xaana does not retain a refresh token
or read the user's existing calendar.
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from db.postgres_db import get_db_session
from repositories.plan_sessions_repo import PlanSessionsRepository
from utils.calendar_utils import calendar_event_description, resolve_calendar_event_title
from utils.logger import get_logger
from ..dependencies import get_current_user


router = APIRouter(prefix="/api/google-calendar", tags=["google_calendar"])
logger = get_logger(__name__)
SCOPE = "https://www.googleapis.com/auth/calendar.events.owned"
REDIRECT_URI = "https://xaana.club/api/google-calendar/callback"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def _client_credentials() -> tuple[str, str]:
    client_id = os.getenv("GOOGLE_CALENDAR_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Google Calendar is not configured")
    return client_id, client_secret


def _result(status: str) -> RedirectResponse:
    response = RedirectResponse(f"/calendar-result?status={status}", status_code=303)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _event_payload(plan_session: dict, user_id: int) -> dict:
    raw_start = plan_session.get("planned_start")
    if not raw_start:
        raise ValueError("Session has no start time")
    start = datetime.fromisoformat(str(raw_start).replace("Z", "+00:00"))
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    duration = int(plan_session.get("planned_duration_min") or 30)
    if duration <= 0:
        duration = 30
    end = start + timedelta(minutes=duration)

    promise_text = ""
    promise_uuid = plan_session.get("promise_uuid")
    if promise_uuid:
        with get_db_session() as db:
            promise_text = db.execute(
                text("SELECT text FROM promises WHERE promise_uuid = :uuid AND user_id = :user_id"),
                {"uuid": promise_uuid, "user_id": str(user_id)},
            ).scalar() or ""
    title = resolve_calendar_event_title(plan_session.get("title"), promise_text)
    description = calendar_event_description(title, promise_text, plan_session.get("notes"))
    reminder_offset = plan_session.get("reminder_offset_min")
    reminder_minutes = max(0, min(40320, int(10 if reminder_offset is None else reminder_offset)))
    reminders = {
        "useDefault": False,
        "overrides": [{"method": "popup", "minutes": reminder_minutes}]
        if plan_session.get("reminder_enabled", True) else [],
    }
    return {
        "id": uuid5(NAMESPACE_URL, f"xaana-calendar:{user_id}:{plan_session['id']}").hex,
        "summary": title,
        "description": description,
        "start": {"dateTime": start.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": end.isoformat().replace("+00:00", "Z")},
        "reminders": reminders,
    }


@router.get("/availability")
async def availability() -> dict:
    return {"enabled": bool(os.getenv("GOOGLE_CALENDAR_CLIENT_ID") and os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET"))}


@router.post("/sessions/{session_id}/authorization-url")
async def authorization_url(session_id: int, user_id: int = Depends(get_current_user)) -> dict:
    client_id, _ = _client_credentials()
    plan_session = PlanSessionsRepository().get(session_id, user_id)
    if not plan_session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not plan_session.get("planned_start"):
        raise HTTPException(status_code=400, detail="Schedule the session before adding it to Calendar")

    state = secrets.token_urlsafe(32)
    digest = hashlib.sha256(state.encode("ascii")).hexdigest()
    with get_db_session() as db:
        db.execute(text("DELETE FROM google_calendar_action_state WHERE expires_at < now()"))
        db.execute(
            text("""INSERT INTO google_calendar_action_state
                    (state_digest, user_id, plan_session_id, expires_at)
                    VALUES (:digest, :user_id, :session_id, :expires_at)"""),
            {
                "digest": digest,
                "user_id": str(user_id),
                "session_id": session_id,
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            },
        )
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "online",
        "state": state,
    }
    return {"url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}"}


@router.get("/callback", include_in_schema=False)
async def google_callback(state: str = "", code: str = "", error: str = "") -> RedirectResponse:
    if not state:
        return _result("expired")
    digest = hashlib.sha256(state.encode("utf-8")).hexdigest()
    with get_db_session() as db:
        action = db.execute(
            text("""DELETE FROM google_calendar_action_state
                    WHERE state_digest = :digest AND expires_at >= now()
                    RETURNING user_id, plan_session_id"""),
            {"digest": digest},
        ).mappings().fetchone()
    if not action:
        return _result("expired")
    if error or not code:
        return _result("denied")

    user_id = int(action["user_id"])
    plan_session = PlanSessionsRepository().get(int(action["plan_session_id"]), user_id)
    if not plan_session or not plan_session.get("planned_start"):
        return _result("missing")
    try:
        client_id, client_secret = _client_credentials()
        payload = _event_payload(plan_session, user_id)
        async with httpx.AsyncClient(timeout=12) as client:
            token_response = await client.post(GOOGLE_TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            })
            token_response.raise_for_status()
            token_data = token_response.json()
            access_token = token_data.get("access_token")
            granted_scopes = token_data.get("scope", "").split()
            if not access_token or (granted_scopes and SCOPE not in granted_scopes):
                return _result("denied")
            headers = {"Authorization": f"Bearer {access_token}"}
            event_response = await client.post(GOOGLE_EVENTS_URL, headers=headers, json=payload)
            if event_response.status_code == 409:
                # The user chose Add again after editing this Xaana session.
                event_response = await client.patch(
                    f"{GOOGLE_EVENTS_URL}/{payload['id']}", headers=headers, json=payload
                )
            event_response.raise_for_status()
        return _result("added")
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        # Never log OAuth codes, tokens, Google response bodies, or session notes.
        logger.warning("Google Calendar event addition failed: %s", type(exc).__name__)
        return _result("failed")
