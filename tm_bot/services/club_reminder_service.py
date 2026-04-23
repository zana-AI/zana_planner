"""
Service for sending nightly reminder messages to each club's Telegram group.

Each night the bot sends one message per active club to its connected
Telegram group chat.  The message lists every member's promise that was
explicitly shared to that club via promise_club_shares, together with an
inline keyboard so members can check in (Done / Not Today).

When a member taps a button the planner_bot callback handler updates the
member's status in bot_data and edits the original group message in place.

Privacy guarantee
-----------------
A member's promise is only included when there is a row in
promise_club_shares where (promise_uuid, club_id) matches this club.
A member's private promises are never touched.
"""
from __future__ import annotations

import random
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from repositories.clubs_repo import ClubsRepository
from repositories.settings_repo import SettingsRepository
from repositories.actions_repo import ActionsRepository
from utils.logger import get_logger

logger = get_logger(__name__)

# Prefix used for all club check-in callback data.
# Full format: "club_checkin:{club_id}:{action}"  (action = done | skip)
CLUB_CHECKIN_PREFIX = "club_checkin:"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _display_name(member: dict) -> str:
    """Return the best available display name for a club member."""
    first = (member.get("first_name") or "").strip()
    username = (member.get("username") or "").strip()
    return first or (f"@{username}" if username else "Member")


def _owner_timezone(owner_user_id: str) -> str:
    """Look up the club owner's timezone; fall back to UTC."""
    try:
        settings_repo = SettingsRepository()
        settings = settings_repo.get_settings(int(owner_user_id))
        tz = getattr(settings, "timezone", None) or "UTC"
        if tz == "DEFAULT":
            return "UTC"
        ZoneInfo(tz)
        return tz
    except (ZoneInfoNotFoundError, Exception):
        return "UTC"


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------

def create_club_checkin_keyboard(club_id: str) -> InlineKeyboardMarkup:
    """Build the two-button inline keyboard attached to the nightly reminder."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "✅ Check in",
            callback_data=f"{CLUB_CHECKIN_PREFIX}{club_id}:done",
        ),
        InlineKeyboardButton(
            "❌ Skip today",
            callback_data=f"{CLUB_CHECKIN_PREFIX}{club_id}:skip",
        ),
    ]])


def build_club_reminder_message(
    club_name: str,
    members: list[dict],
    promise_text: str | None = None,
) -> Optional[str]:
    """
    Compose the check-in reminder text for a club group chat.

    Member dict fields:
        user_id      int
        name         str
        promise_text str | None  (fallback if promise_text arg not given)
        status       None | 'done' | 'skip'
        streak       int   (consecutive done-days before today, 0 if none)

    Returns None if there is no promise and no members.
    """
    shared_promise = promise_text or next(
        (m.get("promise_text") for m in members if m.get("promise_text")), None
    )

    if not members:
        return None

    total = len(members)
    done_count = sum(1 for m in members if m.get("status") == "done")

    lines: list[str] = [f"🎯 {club_name} · check-in", ""]

    if shared_promise:
        lines.append(shared_promise.replace("_", " "))
        lines.append("")

    for member in members:
        status = member.get("status")
        name = member["name"]
        streak = int(member.get("streak", 0))
        if status == "done":
            new_streak = streak + 1
            streak_label = f" 🔥{new_streak}" if new_streak > 1 else ""
            lines.append(f"✅ {name}{streak_label}")
        elif status == "skip":
            lines.append(f"❌ {name}")
        else:
            lines.append(f"⬜ {name}")

    lines.append("")
    if done_count > 0:
        lines.append(f"{done_count}/{total} checked in 💪")
    else:
        lines.append("Tap a button to check in!")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ClubReminderService:
    """Send scheduled check-in messages to each club's Telegram group."""

    def __init__(self) -> None:
        self.clubs_repo = ClubsRepository()
        self.actions_repo = ActionsRepository()

    def _is_reminder_due(self, reminder_time: str, owner_tz: str, now_utc: datetime) -> bool:
        """Return True if the club's reminder falls within the current 15-min window."""
        try:
            hh, mm = map(int, reminder_time.split(":"))
        except (ValueError, AttributeError):
            hh, mm = 21, 0

        now_local = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(owner_tz))
        target_minutes = hh * 60 + mm
        current_minutes = now_local.hour * 60 + now_local.minute
        return target_minutes <= current_minutes < target_minutes + 15

    async def send_due_club_reminders(self, bot, bot_data: dict, now_utc: datetime | None = None) -> None:
        """
        Called every 15 minutes. Sends a check-in reminder to each club whose
        configured reminder_time falls within the current 15-minute window and
        has not yet been sent today.

        State for each sent message is stored in bot_data['club_checkins']
        under (chat_id, message_id) so the callback handler can edit it on tap.
        """
        now = now_utc or datetime.utcnow()
        today_str = now.strftime("%Y-%m-%d")

        clubs = self.clubs_repo.get_active_clubs_with_telegram()
        logger.info("[ClubReminder] Tick — %d club(s) with Telegram groups", len(clubs))

        if "club_checkins" not in bot_data:
            bot_data["club_checkins"] = {}
        if "club_reminder_sent" not in bot_data:
            bot_data["club_reminder_sent"] = {}

        for club in clubs:
            club_id = str(club["club_id"])
            club_name = str(club.get("name") or "Club")
            chat_id = club.get("telegram_chat_id")
            owner_user_id = str(club.get("owner_user_id") or "")
            reminder_time = str(club.get("reminder_time") or "21:00")

            # Already sent today?
            if bot_data["club_reminder_sent"].get(club_id) == today_str:
                continue

            owner_tz = _owner_timezone(owner_user_id)
            if not self._is_reminder_due(reminder_time, owner_tz, now):
                continue

            if not chat_id:
                logger.warning("[ClubReminder] Club %s has no telegram_chat_id — skipping", club_id)
                continue

            try:
                raw_members = self.clubs_repo.get_club_members_promises(club_id)
            except Exception as exc:
                logger.exception("[ClubReminder] Failed to fetch members for club %s: %s", club_id, exc)
                continue

            if not raw_members:
                logger.info("[ClubReminder] Club %s has no active members — skipping", club_id)
                continue

            # Shared club promise text (same for all members)
            promise_text = next(
                (m.get("promise_text") for m in raw_members if m.get("promise_text")), None
            )
            # Pick the promise_uuid to record actions against
            promise_uuid = next(
                (m.get("promise_uuid") for m in raw_members if m.get("promise_uuid")), None
            )

            # Build member state with streak pre-loaded from DB
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
                    "name": _display_name(m),
                    "promise_text": m.get("promise_text"),
                    "status": None,
                    "streak": streak,
                })

            message = build_club_reminder_message(club_name, members, promise_text=promise_text)
            if message is None:
                logger.info("[ClubReminder] Club %s has no promise — skipping", club_id)
                continue

            keyboard = create_club_checkin_keyboard(club_id)

            try:
                sent = await bot.send_message(
                    chat_id=int(chat_id),
                    text=message,
                    parse_mode=None,
                    reply_markup=keyboard,
                )
                state_key = (sent.chat_id, sent.message_id)
                bot_data["club_checkins"][state_key] = {
                    "club_id": club_id,
                    "club_name": club_name,
                    "promise_text": promise_text,
                    "promise_uuid": promise_uuid,
                    "members": members,
                }
                bot_data["club_reminder_sent"][club_id] = today_str
                logger.info(
                    "[ClubReminder] ✓ Sent to club %s ('%s') chat %s msg %s",
                    club_id, club_name, sent.chat_id, sent.message_id,
                )
            except Exception as exc:
                logger.warning(
                    "[ClubReminder] ✗ Failed to send to club %s chat %s: %s",
                    club_id, chat_id, exc,
                )

    # Keep old name as alias so any external callers don't break
    async def send_all_club_nightly_reminders(self, bot, bot_data: dict) -> None:
        await self.send_due_club_reminders(bot, bot_data)
