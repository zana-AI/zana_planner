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

_NON_LATIN_LANGUAGE_CODES = {"fa", "ar", "ur", "ps"}
_WEEKDAYS_BY_LANGUAGE = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "fr": ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"),
    "fa": (
        "\u062f\u0648\u0634\u0646\u0628\u0647",
        "\u0633\u0647\u200c\u0634\u0646\u0628\u0647",
        "\u0686\u0647\u0627\u0631\u0634\u0646\u0628\u0647",
        "\u067e\u0646\u062c\u0634\u0646\u0628\u0647",
        "\u062c\u0645\u0639\u0647",
        "\u0634\u0646\u0628\u0647",
        "\u06cc\u06a9\u0634\u0646\u0628\u0647",
    ),
    "ar": (
        "\u0627\u0644\u0627\u062b\u0646\u064a\u0646",
        "\u0627\u0644\u062b\u0644\u0627\u062b\u0627\u0621",
        "\u0627\u0644\u0623\u0631\u0628\u0639\u0627\u0621",
        "\u0627\u0644\u062e\u0645\u064a\u0633",
        "\u0627\u0644\u062c\u0645\u0639\u0629",
        "\u0627\u0644\u0633\u0628\u062a",
        "\u0627\u0644\u0623\u062d\u062f",
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _language_code(language: str | None) -> str:
    return (language or "en").strip().lower().split("-", 1)[0] or "en"


def _prefers_non_latin(language: str | None) -> bool:
    return _language_code(language) in _NON_LATIN_LANGUAGE_CODES


def _localized_weekday(
    now_utc: datetime | None = None,
    timezone: str | None = None,
    language: str | None = None,
) -> str:
    """Return the weekday name in the club's display language and timezone."""
    tz_name = (timezone or "UTC").strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name if tz_name != "DEFAULT" else "UTC")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")

    now = now_utc or datetime.utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("UTC"))
    local_now = now.astimezone(tz)
    weekdays = _WEEKDAYS_BY_LANGUAGE.get(_language_code(language), _WEEKDAYS_BY_LANGUAGE["en"])
    return weekdays[local_now.weekday()]


def _display_name(member: dict, language: str | None = None) -> str:
    """Return the best display name for a club member, using one script per group."""
    non_latin = (member.get("non_latin_name") or "").strip()
    latin = (member.get("latin_name") or "").strip()
    if _prefers_non_latin(language):
        primary = non_latin or latin
    else:
        primary = latin or non_latin
    primary = primary or (member.get("first_name") or member.get("name") or "").strip()
    username = (member.get("username") or "").strip()
    return primary or (f"@{username}" if username else "Member")


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
    language: str | None = None,
    now_utc: datetime | None = None,
    timezone: str | None = None,
) -> Optional[str]:
    """
    Compose the check-in reminder text for a club group chat.

    Member dict fields:
        user_id      int
        name         str
        promise_text str | None  (fallback if promise_text arg not given)
        status       None | 'done' | 'skip'
        streak       int   final freeze-aware streak count for display

    Returns None if there is no promise and no members.
    """
    shared_promise = promise_text or next(
        (m.get("promise_text") for m in members if m.get("promise_text")), None
    )

    if not members:
        return None

    total = len(members)
    done_count = sum(1 for m in members if m.get("status") == "done")

    weekday = _localized_weekday(now_utc=now_utc, timezone=timezone, language=language)
    lines: list[str] = [f"🎯 {club_name} · {weekday} · check-in", ""]

    if shared_promise:
        lines.append(shared_promise.replace("_", " "))
        lines.append("")

    for member in members:
        status = member.get("status")
        name = member["name"]
        streak = int(member.get("streak", 0))
        if status == "done":
            streak_label = f" 🔥{streak}" if streak > 1 else ""
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
            language = str(club.get("language") or "en")

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
            checked_in_today = self.actions_repo.get_today_checkins(promise_uuid) if promise_uuid else set()

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
                    "language": language,
                    "timezone": owner_tz,
                    "members": members,
                }
                bot_data["club_reminder_sent"][club_id] = today_str
                logger.info(
                    "[ClubReminder] ✓ Sent to club %s ('%s') chat %s msg %s",
                    club_id, club_name, sent.chat_id, sent.message_id,
                )
                try:
                    await bot.pin_chat_message(
                        chat_id=int(chat_id),
                        message_id=sent.message_id,
                        disable_notification=True,
                    )
                except Exception as pin_exc:
                    logger.debug("[ClubReminder] Could not pin reminder for club %s: %s", club_id, pin_exc)
            except Exception as exc:
                logger.warning(
                    "[ClubReminder] ✗ Failed to send to club %s chat %s: %s",
                    club_id, chat_id, exc,
                )

    # Keep old name as alias so any external callers don't break
    async def send_all_club_nightly_reminders(self, bot, bot_data: dict) -> None:
        await self.send_due_club_reminders(bot, bot_data)
