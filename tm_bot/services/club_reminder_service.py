"""
Service for sending nightly reminder messages to each club's Telegram group.

Each night the bot sends one message per active club to its connected
Telegram group chat.  The message lists every member's promise that was
explicitly shared to that club via promise_club_shares.

Privacy guarantee
-----------------
A member's promise is only included when there is a row in
promise_club_shares where (promise_uuid, club_id) matches this club.
A member's private promises are never touched.
"""
from __future__ import annotations

from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from repositories.clubs_repo import ClubsRepository
from repositories.settings_repo import SettingsRepository
from utils.logger import get_logger

logger = get_logger(__name__)


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
        # Validate
        ZoneInfo(tz)
        return tz
    except (ZoneInfoNotFoundError, Exception):
        return "UTC"


def _owner_language(owner_user_id: str) -> Optional[str]:
    """Look up the club owner's preferred language; None means English."""
    try:
        settings_repo = SettingsRepository()
        settings = settings_repo.get_settings(int(owner_user_id))
        return getattr(settings, "language", None) or None
    except Exception:
        return None


def build_club_reminder_message(club_name: str, members: list[dict]) -> Optional[str]:
    """
    Compose the nightly reminder text for a club group chat.

    Returns None if no member has shared a promise to this club (so the
    message is skipped entirely for empty clubs).
    """
    # Filter to members who shared a promise
    promised = [m for m in members if m.get("promise_text")]
    no_promise = [m for m in members if not m.get("promise_text")]

    # Skip entirely when no one has a promise
    if not promised:
        return None

    lines: list[str] = [
        f"🌙 Nightly Club Check-in: {club_name}",
        "",
        "📋 Member Commitments:",
    ]

    for i, member in enumerate(promised, 1):
        name = _display_name(member)
        promise = str(member["promise_text"]).replace("_", " ")
        lines.append(f"{i}. {name}: {promise}")

    # Members without a promise get a placeholder at the bottom
    for member in no_promise:
        name = _display_name(member)
        lines.append(f"• {name}: (No promise shared yet)")

    lines.extend(["", "Keep going! 💪"])
    return "\n".join(lines)


class ClubReminderService:
    """Send nightly promise-recap messages to each club's Telegram group."""

    def __init__(self) -> None:
        self.clubs_repo = ClubsRepository()

    async def send_all_club_nightly_reminders(self, bot) -> None:
        """
        Iterate over all active clubs with a connected Telegram group and
        post the nightly reminder to each group chat.

        Args:
            bot: A python-telegram-bot ``Bot`` instance (or any object that
                 exposes ``send_message(chat_id, text, parse_mode)``).
        """
        clubs = self.clubs_repo.get_active_clubs_with_telegram()
        logger.info(
            "[ClubReminder] Starting nightly run — %d club(s) with Telegram groups",
            len(clubs),
        )

        for club in clubs:
            club_id = str(club["club_id"])
            club_name = str(club.get("name") or "Club")
            chat_id = club.get("telegram_chat_id")
            owner_user_id = str(club.get("owner_user_id") or "")

            if not chat_id:
                logger.warning(
                    "[ClubReminder] Club %s ('%s') has no telegram_chat_id — skipping",
                    club_id,
                    club_name,
                )
                continue

            try:
                members = self.clubs_repo.get_club_members_promises(club_id)
            except Exception as exc:
                logger.exception(
                    "[ClubReminder] Failed to fetch members for club %s: %s",
                    club_id,
                    exc,
                )
                continue

            if not members:
                logger.info(
                    "[ClubReminder] Club %s ('%s') has no active members — skipping",
                    club_id,
                    club_name,
                )
                continue

            message = build_club_reminder_message(club_name, members)
            if message is None:
                logger.info(
                    "[ClubReminder] Club %s ('%s') has no shared promises — skipping",
                    club_id,
                    club_name,
                )
                continue

            try:
                await bot.send_message(
                    chat_id=int(chat_id),
                    text=message,
                    parse_mode=None,  # plain text — safe in group chats
                )
                logger.info(
                    "[ClubReminder] ✓ Sent nightly reminder to club %s ('%s') chat %s",
                    club_id,
                    club_name,
                    chat_id,
                )
            except Exception as exc:
                logger.warning(
                    "[ClubReminder] ✗ Failed to send to club %s ('%s') chat %s: %s",
                    club_id,
                    club_name,
                    chat_id,
                    exc,
                )
