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

from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from repositories.clubs_repo import ClubsRepository
from repositories.settings_repo import SettingsRepository
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
            "✅ Done!",
            callback_data=f"{CLUB_CHECKIN_PREFIX}{club_id}:done",
        ),
        InlineKeyboardButton(
            "❌ Not Today",
            callback_data=f"{CLUB_CHECKIN_PREFIX}{club_id}:skip",
        ),
    ]])


def build_club_reminder_message(club_name: str, members: list[dict]) -> Optional[str]:
    """
    Compose the nightly reminder text for a club group chat.

    Each member dict is expected to have:
        user_id      int
        name         str   (pre-computed display name)
        promise_text str | None
        status       None | 'done' | 'skip'

    Returns None if no member has shared a promise to this club (so the
    message is skipped entirely for empty clubs).
    """
    promised = [m for m in members if m.get("promise_text")]
    no_promise = [m for m in members if not m.get("promise_text")]

    # Skip entirely when nobody has a promise
    if not promised:
        return None

    total = len(members)
    responded = sum(1 for m in members if m.get("status"))

    lines: list[str] = [
        f"🌙 Nightly Club Check-in: {club_name}",
        "",
        "📋 Member Check-in:",
    ]

    # Members with a promise (numbered list)
    for i, member in enumerate(promised, 1):
        status = member.get("status")
        if status == "done":
            marker = "✅"
        elif status == "skip":
            marker = "❌"
        else:
            marker = f"{i}."
        name = member["name"]
        promise = str(member["promise_text"]).replace("_", " ")
        lines.append(f"{marker} {name}: {promise}")

    # Members without a shared promise (bullet list)
    for member in no_promise:
        status = member.get("status")
        if status == "done":
            marker = "✅"
        elif status == "skip":
            marker = "❌"
        else:
            marker = "•"
        name = member["name"]
        lines.append(f"{marker} {name}: (No promise shared yet)")

    lines.append("")
    if responded > 0:
        lines.append(f"Checked in: {responded}/{total} 💪")
    else:
        lines.append("Tap a button below to check in!")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ClubReminderService:
    """Send nightly promise-recap messages to each club's Telegram group."""

    def __init__(self) -> None:
        self.clubs_repo = ClubsRepository()

    async def send_all_club_nightly_reminders(self, bot, bot_data: dict) -> None:
        """
        Iterate over all active clubs with a connected Telegram group and
        post the nightly check-in reminder to each group chat.

        State for each sent message is stored in bot_data['club_checkins']
        under the key (chat_id, message_id), so the callback handler can
        find and edit it when members tap their buttons.

        Args:
            bot:      python-telegram-bot ``Bot`` instance.
            bot_data: The application's bot_data dict for state storage.
        """
        clubs = self.clubs_repo.get_active_clubs_with_telegram()
        logger.info(
            "[ClubReminder] Starting nightly run — %d club(s) with Telegram groups",
            len(clubs),
        )

        if "club_checkins" not in bot_data:
            bot_data["club_checkins"] = {}

        for club in clubs:
            club_id = str(club["club_id"])
            club_name = str(club.get("name") or "Club")
            chat_id = club.get("telegram_chat_id")
            owner_user_id = str(club.get("owner_user_id") or "")

            if not chat_id:
                logger.warning(
                    "[ClubReminder] Club %s ('%s') has no telegram_chat_id — skipping",
                    club_id, club_name,
                )
                continue

            try:
                raw_members = self.clubs_repo.get_club_members_promises(club_id)
            except Exception as exc:
                logger.exception(
                    "[ClubReminder] Failed to fetch members for club %s: %s",
                    club_id, exc,
                )
                continue

            if not raw_members:
                logger.info(
                    "[ClubReminder] Club %s ('%s') has no active members — skipping",
                    club_id, club_name,
                )
                continue

            # Build initial member state list (all statuses start as None)
            members = [
                {
                    "user_id": int(m["user_id"]),
                    "name": _display_name(m),
                    "promise_text": m.get("promise_text"),
                    "status": None,
                }
                for m in raw_members
            ]

            message = build_club_reminder_message(club_name, members)
            if message is None:
                logger.info(
                    "[ClubReminder] Club %s ('%s') has no shared promises — skipping",
                    club_id, club_name,
                )
                continue

            keyboard = create_club_checkin_keyboard(club_id)

            try:
                sent = await bot.send_message(
                    chat_id=int(chat_id),
                    text=message,
                    parse_mode=None,  # plain text — safe in group chats
                    reply_markup=keyboard,
                )
                # Register state so the callback handler can edit this message
                state_key = (sent.chat_id, sent.message_id)
                bot_data["club_checkins"][state_key] = {
                    "club_id": club_id,
                    "club_name": club_name,
                    "members": members,
                }
                logger.info(
                    "[ClubReminder] ✓ Sent check-in to club %s ('%s') chat %s msg %s",
                    club_id, club_name, sent.chat_id, sent.message_id,
                )
            except Exception as exc:
                logger.warning(
                    "[ClubReminder] ✗ Failed to send to club %s ('%s') chat %s: %s",
                    club_id, club_name, chat_id, exc,
                )
