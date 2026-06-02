"""
Sends nightly check-in reminders to each club's Slack channel.

Mirrors the logic in club_reminder_service.py but uses Slack Block Kit
for rich interactive messages instead of Telegram inline keyboards.

The service is called every 15 minutes from a background task started in
webapp/api.py at startup.  State (sent-today flag, per-message payload for
editing) lives in a simple in-memory dict that is passed in from the caller.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from repositories.clubs_repo import ClubsRepository
from repositories.settings_repo import SettingsRepository
from repositories.actions_repo import ActionsRepository
from services.club_reminder_service import (
    _owner_timezone,
    _display_name,
    _localized_weekday,
    build_club_reminder_message,
)
from utils.logger import get_logger

logger = get_logger(__name__)

CLUB_CHECKIN_PREFIX = "club_checkin:"


# ---------------------------------------------------------------------------
# Block Kit helpers
# ---------------------------------------------------------------------------

def _build_checkin_blocks(message_text: str, club_id: str) -> list:
    """Return Slack Block Kit blocks for a club check-in reminder."""
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": message_text},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Check in", "emoji": True},
                    "style": "primary",
                    "action_id": f"{CLUB_CHECKIN_PREFIX}{club_id}:done",
                    "value": f"{club_id}:done",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Skip today", "emoji": True},
                    "action_id": f"{CLUB_CHECKIN_PREFIX}{club_id}:skip",
                    "value": f"{club_id}:skip",
                },
            ],
        },
    ]
    return blocks


def _rebuild_message_blocks(
    club_name: str,
    members: list[dict],
    promise_text: str | None,
    language: str,
    now_utc: datetime,
    owner_tz: str,
    club_id: str,
) -> list:
    """Rebuild Block Kit blocks after a member checks in (to update the message)."""
    text = build_club_reminder_message(
        club_name,
        members,
        promise_text=promise_text,
        language=language,
        now_utc=now_utc,
        timezone=owner_tz,
    )
    if text is None:
        return []
    return _build_checkin_blocks(text, club_id)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SlackClubReminderService:
    """Sends scheduled Slack check-in messages to clubs that have a Slack channel."""

    def __init__(self) -> None:
        self.clubs_repo = ClubsRepository()
        self.actions_repo = ActionsRepository()

    def _is_reminder_due(self, reminder_time: str, owner_tz: str, now_utc: datetime) -> bool:
        try:
            hh, mm = map(int, reminder_time.split(":"))
        except (ValueError, AttributeError):
            hh, mm = 21, 0
        now_local = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(owner_tz))
        target = hh * 60 + mm
        current = now_local.hour * 60 + now_local.minute
        return target <= current < target + 15

    async def send_due_club_reminders(
        self,
        slack_state: dict,
        now_utc: datetime | None = None,
    ) -> None:
        """
        Called every 15 minutes.  Posts a check-in block to each Slack-connected
        club whose reminder window falls within the current 15-minute slot and
        hasn't sent today yet.

        slack_state is a mutable dict stored in app.state.slack_state:
          {
            "checkins": { (channel_id, ts): { club payload ... } },
            "reminder_sent": { club_id: "YYYY-MM-DD" },
          }
        """
        now = now_utc or datetime.utcnow()
        today_str = now.strftime("%Y-%m-%d")

        slack_state.setdefault("checkins", {})
        slack_state.setdefault("reminder_sent", {})

        clubs = self.clubs_repo.get_active_clubs_with_slack()
        logger.info("[SlackReminder] Tick — %d club(s) with Slack channels", len(clubs))

        for club in clubs:
            club_id = str(club["club_id"])
            club_name = str(club.get("name") or "Club")
            channel_id = club.get("slack_channel_id")
            bot_token = club.get("slack_bot_token")
            owner_user_id = str(club.get("owner_user_id") or "")
            reminder_time = str(club.get("reminder_time") or "21:00")
            language = str(club.get("language") or "en")

            if slack_state["reminder_sent"].get(club_id) == today_str:
                continue

            if not channel_id or not bot_token:
                logger.debug("[SlackReminder] Club %s missing channel/token — skipping", club_id)
                continue

            owner_tz = _owner_timezone(owner_user_id)
            if not self._is_reminder_due(reminder_time, owner_tz, now):
                continue

            try:
                raw_members = self.clubs_repo.get_club_members_promises(club_id)
            except Exception as exc:
                logger.exception("[SlackReminder] Failed to fetch members for club %s: %s", club_id, exc)
                continue

            if not raw_members:
                continue

            promise_text = next(
                (m.get("promise_text") for m in raw_members if m.get("promise_text")), None
            )
            promise_uuid = next(
                (m.get("promise_uuid") for m in raw_members if m.get("promise_uuid")), None
            )
            checked_in_today = self.actions_repo.get_today_checkins(promise_uuid) if promise_uuid else set()

            members = []
            for m in raw_members:
                uid = int(m["user_id"])
                streak = 0
                if promise_uuid:
                    try:
                        streak = self.actions_repo.get_checkin_streak(uid, promise_uuid)
                    except Exception:
                        pass
                members.append({
                    "user_id": uid,
                    "name": _display_name(m, language),
                    "promise_text": m.get("promise_text"),
                    "status": "done" if str(uid) in checked_in_today else None,
                    "streak": streak,
                })

            message = build_club_reminder_message(
                club_name,
                members,
                promise_text=promise_text,
                language=language,
                now_utc=now,
                timezone=owner_tz,
            )
            if message is None:
                continue

            blocks = _build_checkin_blocks(message, club_id)

            try:
                client = WebClient(token=bot_token)
                resp = client.chat_postMessage(
                    channel=channel_id,
                    text=message,
                    blocks=blocks,
                )
                ts = resp["ts"]
                state_key = (channel_id, ts)
                slack_state["checkins"][state_key] = {
                    "club_id": club_id,
                    "club_name": club_name,
                    "promise_text": promise_text,
                    "promise_uuid": promise_uuid,
                    "language": language,
                    "timezone": owner_tz,
                    "members": members,
                    "bot_token": bot_token,
                }
                slack_state["reminder_sent"][club_id] = today_str
                logger.info(
                    "[SlackReminder] ✓ Sent to club %s ('%s') channel %s ts %s",
                    club_id, club_name, channel_id, ts,
                )
            except SlackApiError as exc:
                logger.warning(
                    "[SlackReminder] ✗ Failed to post to club %s channel %s: %s",
                    club_id, channel_id, exc,
                )

    async def handle_checkin_action(
        self,
        slack_state: dict,
        action_id: str,
        channel_id: str,
        message_ts: str,
        slack_user_id: str,
    ) -> None:
        """
        Called when a user taps ✅ or ❌ in Slack.
        Updates in-memory state and edits the original message in place.
        """
        # Parse club_id and action from action_id: "club_checkin:{club_id}:{done|skip}"
        parts = action_id.split(":")
        if len(parts) < 3 or parts[0] != "club_checkin":
            return

        club_id = parts[1]
        action = parts[2]  # done | skip

        state_key = (channel_id, message_ts)
        state = slack_state.get("checkins", {}).get(state_key)
        if not state:
            logger.debug("[SlackReminder] No state for key %s", state_key)
            return

        bot_token = state.get("bot_token")
        members: list[dict] = state.get("members", [])

        # Map slack_user_id to xaana user — we store it in the action itself for now
        # and update all members whose slack_user_id matches (or update by position if unknown)
        matched = False
        for member in members:
            if str(member.get("slack_user_id", "")) == slack_user_id:
                member["status"] = action
                matched = True
                break

        if not matched:
            logger.debug(
                "[SlackReminder] slack_user_id %s not mapped to a member in club %s",
                slack_user_id, club_id,
            )

        # Rebuild and update the message
        now = datetime.utcnow()
        blocks = _rebuild_message_blocks(
            club_name=state["club_name"],
            members=members,
            promise_text=state.get("promise_text"),
            language=state.get("language", "en"),
            now_utc=now,
            owner_tz=state.get("timezone", "UTC"),
            club_id=club_id,
        )
        if not blocks or not bot_token:
            return

        message_text = build_club_reminder_message(
            state["club_name"],
            members,
            promise_text=state.get("promise_text"),
            language=state.get("language", "en"),
            now_utc=now,
            timezone=state.get("timezone", "UTC"),
        ) or ""

        try:
            client = WebClient(token=bot_token)
            client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text=message_text,
                blocks=blocks,
            )
            logger.info(
                "[SlackReminder] Updated check-in for club %s action=%s slack_user=%s",
                club_id, action, slack_user_id,
            )
        except SlackApiError as exc:
            logger.warning("[SlackReminder] Failed to update message: %s", exc)


# ---------------------------------------------------------------------------
# Background task helper
# ---------------------------------------------------------------------------

async def run_slack_reminder_loop(get_state_fn, interval_seconds: int = 900) -> None:
    """
    Runs forever, calling SlackClubReminderService.send_due_club_reminders()
    every `interval_seconds` (default 15 min).

    get_state_fn() returns the mutable slack_state dict from app.state.
    """
    service = SlackClubReminderService()
    while True:
        try:
            await service.send_due_club_reminders(get_state_fn())
        except Exception as exc:
            logger.exception("[SlackReminder] Unexpected error in reminder loop: %s", exc)
        await asyncio.sleep(interval_seconds)
