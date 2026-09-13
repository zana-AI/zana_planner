"""Reserve-pool operations shared by the web process and the running bot.

No second Telegram update consumer is used. Dormant reserves contain chat IDs,
not bearer invite URLs. Allocation creates a join-request link, so possession
of a leaked URL alone cannot grant group access.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from sqlalchemy import text
from telegram import Bot
from telegram.error import TelegramError

from db.postgres_db import get_db_session, utc_now_iso
from utils.admin_utils import get_admin_ids
from utils.logger import get_logger


logger = get_logger(__name__)
RESERVE_LABEL_RE = re.compile(r"C[0-9]{4,6}\Z")
BOT_RIGHTS = (
    "can_change_info", "can_invite_users", "can_promote_members",
    "can_delete_messages", "can_restrict_members",
)


class ReserveValidationError(ValueError):
    """A candidate group is not safe to enter the available pool."""


async def inspect_reserve(bot: Bot, chat_id: int, caretaker_user_id: int) -> dict[str, Any]:
    """Check the small, empty group and bot rights before registration/allocation."""
    chat = await bot.get_chat(chat_id)
    me = await bot.get_me()
    bot_member = await bot.get_chat_member(chat_id, me.id)
    admins = await bot.get_chat_administrators(chat_id)
    member_count = await bot.get_chat_member_count(chat_id)
    if chat.type != "supergroup":
        raise ReserveValidationError("Reserve must be a supergroup")
    if bot_member.status != "administrator" or not all(
        bool(getattr(bot_member, right, False)) for right in BOT_RIGHTS
    ):
        raise ReserveValidationError("Bot lacks required group-admin permissions")
    if member_count != 2:
        raise ReserveValidationError("Reserve must contain exactly the caretaker and Xaana bot")
    if not any(
        entry.user.id == caretaker_user_id and entry.status in {"creator", "owner", "administrator"}
        for entry in admins
    ):
        raise ReserveValidationError("Registered caretaker is no longer a group admin")
    if not chat.title:
        raise ReserveValidationError("Reserve has no title")
    return {"chat_id": chat_id, "title": chat.title, "bot_user_id": me.id, "member_count": member_count}


async def revoke_legacy_primary_link(bot: Bot, chat_id: int) -> None:
    """Retire every primary invite link handed out before registration.

    ``export_chat_invite_link`` mints a fresh primary link and revokes the
    previous one, which is the only way a bot can retire a link it did not
    create itself. The new URL is deliberately discarded: a dormant reserve
    must never hold a bearer link, and allocation mints its own join-request
    link anyway. Named links created by other admins cannot be enumerated over
    the Bot API, so the operator still confirms those by hand.
    """
    try:
        await bot.export_chat_invite_link(chat_id)
    except TelegramError as error:
        raise ReserveValidationError(
            f"Could not revoke the group's existing primary invite link: {error}"
        ) from error


async def register_reserve(bot: Bot, chat_id: int, actor_user_id: int, label: str) -> dict[str, Any]:
    """Register a clean group after a configured Xaana admin attests it."""
    label = label.strip().upper()
    if not RESERVE_LABEL_RE.fullmatch(label):
        raise ReserveValidationError("Use a reserve label such as C0002")
    admins = await bot.get_chat_administrators(chat_id)
    owners = [entry.user.id for entry in admins if entry.status in {"creator", "owner"} and not entry.user.is_bot]
    if len(owners) != 1:
        raise ReserveValidationError("Reserve must have one human group owner")
    caretaker_user_id = owners[0]
    checked = await inspect_reserve(bot, chat_id, caretaker_user_id)
    if checked["title"].strip().upper() != label:
        raise ReserveValidationError("Group title must match its reserve label")
    await revoke_legacy_primary_link(bot, chat_id)
    now = utc_now_iso()
    with get_db_session() as session:
        existing = session.execute(
            text("SELECT chat_id, label, status FROM telegram_group_reserves WHERE chat_id = :chat_id FOR UPDATE"),
            {"chat_id": chat_id},
        ).mappings().fetchone()
        if existing and existing["status"] not in {"available", "needs_review"}:
            raise ReserveValidationError("This group is already assigned or disabled")
        if existing and existing["label"] != label:
            raise ReserveValidationError("This group is already registered under another label")
        other_label = session.execute(
            text("SELECT chat_id FROM telegram_group_reserves WHERE label = :label AND chat_id <> :chat_id LIMIT 1"),
            {"label": label, "chat_id": chat_id},
        ).fetchone()
        if other_label:
            raise ReserveValidationError("This reserve label belongs to another group")
        linked = session.execute(
            text("SELECT club_id FROM clubs WHERE telegram_chat_id = :chat_id AND COALESCE(status, 'active') = 'active' LIMIT 1"),
            {"chat_id": str(chat_id)},
        ).fetchone()
        if linked:
            raise ReserveValidationError("This group is already linked to a club")
        session.execute(
            text("""
                INSERT INTO telegram_group_reserves (
                    chat_id, label, registered_by_user_id, caretaker_user_id, bot_user_id,
                    status, original_title, member_count_at_check, verified_at_utc,
                    cleanliness_attested_at_utc, cleanliness_attested_by_user_id
                ) VALUES (
                    :chat_id, :label, :actor, :caretaker, :bot_id,
                    'available', :title, :member_count, :now, :now, :actor
                )
                ON CONFLICT (chat_id) DO UPDATE SET
                    status = 'available',
                    registered_by_user_id = EXCLUDED.registered_by_user_id,
                    caretaker_user_id = EXCLUDED.caretaker_user_id,
                    bot_user_id = EXCLUDED.bot_user_id,
                    original_title = EXCLUDED.original_title,
                    member_count_at_check = EXCLUDED.member_count_at_check,
                    verified_at_utc = EXCLUDED.verified_at_utc,
                    cleanliness_attested_at_utc = EXCLUDED.cleanliness_attested_at_utc,
                    cleanliness_attested_by_user_id = EXCLUDED.cleanliness_attested_by_user_id,
                    last_error = NULL
            """),
            {
                "chat_id": chat_id, "label": label, "actor": actor_user_id,
                "caretaker": caretaker_user_id,
                "bot_id": checked["bot_user_id"], "title": checked["title"],
                "member_count": checked["member_count"], "now": now,
            },
        )
    return {
        "chat_id": chat_id, "label": label, "title": checked["title"],
        "caretaker_user_id": caretaker_user_id, "status": "available",
        "primary_link_revoked": True,
    }


def _claim_oldest_reserve(club_id: str) -> dict[str, Any] | None:
    """Commit a row-level claim so concurrent club requests cannot share a group."""
    with get_db_session() as session:
        row = session.execute(
            text("""
                SELECT chat_id, label, caretaker_user_id, original_title
                FROM telegram_group_reserves
                WHERE status = 'available'
                ORDER BY verified_at_utc, chat_id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            """),
        ).mappings().fetchone()
        if not row:
            return None
        session.execute(
            text("""
                UPDATE telegram_group_reserves
                SET status = 'assigning', club_id = :club_id, last_error = NULL
                WHERE chat_id = :chat_id AND status = 'available'
            """),
            {"chat_id": row["chat_id"], "club_id": club_id},
        )
        return dict(row)


def _mark_reserve_needs_review(chat_id: int, error_name: str) -> None:
    with get_db_session() as session:
        session.execute(
            text("""
                UPDATE telegram_group_reserves
                SET status = 'needs_review', club_id = NULL, last_error = :error
                WHERE chat_id = :chat_id AND status = 'assigning'
            """),
            {"chat_id": chat_id, "error": error_name[:200]},
        )


async def allocate_reserve_to_club(club_id: str, bot_token: str) -> dict[str, Any] | None:
    """Rename a claimed reserve, mint a guarded link, then mark the club ready."""
    if not bot_token:
        return None
    with get_db_session() as session:
        club = session.execute(
            text("""
                SELECT club_id, owner_user_id, name FROM clubs
                WHERE club_id = :club_id AND COALESCE(status, 'active') = 'active'
                  AND telegram_status = 'pending_admin_setup'
                  AND NULLIF(trim(COALESCE(telegram_chat_id, '')), '') IS NULL
                LIMIT 1
            """),
            {"club_id": club_id},
        ).mappings().fetchone()
    if not club:
        return None
    reserve = _claim_oldest_reserve(club_id)
    if not reserve:
        return None

    chat_id = int(reserve["chat_id"])
    link: str | None = None
    renamed = False
    try:
        async with Bot(token=bot_token) as bot:
            checked = await inspect_reserve(bot, chat_id, int(reserve["caretaker_user_id"]))
            if checked["title"] != reserve["original_title"]:
                raise ReserveValidationError("Reserve title changed since registration")
            await bot.set_chat_title(chat_id, str(club["name"]))
            renamed = True
            if (await bot.get_chat(chat_id)).title != club["name"]:
                raise ReserveValidationError("Telegram did not confirm the requested club title")
            invite = await bot.create_chat_invite_link(
                chat_id=chat_id,
                creates_join_request=True,
                name=f"xaana-club-{club_id[:8]}",
            )
            link = invite.invite_link
            now = utc_now_iso()
            with get_db_session() as session:
                result = session.execute(
                    text("""
                        UPDATE clubs SET
                            telegram_status = 'ready', telegram_chat_id = :chat_id,
                            telegram_invite_link = :link, telegram_ready_at_utc = :now,
                            updated_at_utc = :now
                        WHERE club_id = :club_id AND telegram_status = 'pending_admin_setup'
                          AND NULLIF(trim(COALESCE(telegram_chat_id, '')), '') IS NULL
                    """),
                    {"chat_id": str(chat_id), "link": link, "now": now, "club_id": club_id},
                )
                if result.rowcount != 1:
                    raise RuntimeError("Club changed while reserve was being allocated")
                updated = session.execute(
                    text("""
                        UPDATE telegram_group_reserves SET status = 'allocated', allocated_at_utc = :now
                        WHERE chat_id = :chat_id AND status = 'assigning' AND club_id = :club_id
                    """),
                    {"chat_id": chat_id, "club_id": club_id, "now": now},
                )
                if updated.rowcount != 1:
                    raise RuntimeError("Reserve claim changed during allocation")
            return {
                "chat_id": chat_id, "club_id": club_id, "club_name": str(club["name"]),
                "owner_user_id": int(club["owner_user_id"]), "invite_link": link,
                "label": str(reserve["label"]),
            }
    except Exception as error:
        logger.warning("Reserve %s allocation failed: %s", reserve["label"], type(error).__name__)
        # A failed Telegram or DB step quarantines the group; never hand its URL to users.
        try:
            async with Bot(token=bot_token) as bot:
                if link:
                    await bot.revoke_chat_invite_link(chat_id, link)
                if renamed:
                    await bot.set_chat_title(chat_id, str(reserve["original_title"]))
        except TelegramError:
            logger.warning("Reserve %s could not be fully restored after failure", reserve["label"])
        _mark_reserve_needs_review(chat_id, type(error).__name__)
        return None


async def handle_reserve_join_request(bot: Bot, join_request: Any) -> str:
    """Approve only authenticated club members using the assigned guarded link."""
    chat_id = join_request.chat.id
    user_id = join_request.from_user.id
    supplied_link = getattr(getattr(join_request, "invite_link", None), "invite_link", None)
    with get_db_session() as session:
        row = session.execute(
            text("""
                SELECT c.club_id, c.owner_user_id, r.caretaker_user_id, c.telegram_invite_link,
                       c.telegram_status, cm.status AS member_status
                FROM telegram_group_reserves r
                JOIN clubs c ON c.club_id = r.club_id
                LEFT JOIN club_members cm ON cm.club_id = c.club_id AND cm.user_id = :user_id
                WHERE r.chat_id = :chat_id AND r.status = 'allocated'
                  AND c.telegram_chat_id = :chat_id_text
                  AND COALESCE(c.status, 'active') = 'active'
                LIMIT 1
            """),
            {"chat_id": chat_id, "chat_id_text": str(chat_id), "user_id": str(user_id)},
        ).mappings().fetchone()
    if not row:
        with get_db_session() as session:
            known = session.execute(
                text("SELECT 1 FROM telegram_group_reserves WHERE chat_id = :chat_id LIMIT 1"),
                {"chat_id": chat_id},
            ).fetchone()
        if not known:
            return "unmanaged"
        await bot.decline_chat_join_request(chat_id, user_id)
        return "declined"
    allowed = bool(
        row and supplied_link and supplied_link == row["telegram_invite_link"]
        and row["telegram_status"] in {"ready", "connected"}
        and row["member_status"] == "active"
        and user_id != row["caretaker_user_id"]
    )
    if not allowed:
        await bot.decline_chat_join_request(chat_id, user_id)
        return "declined"
    await bot.approve_chat_join_request(chat_id, user_id)
    if str(row["owner_user_id"]) != str(user_id):
        return "member_approved"

    for attempt in range(3):
        try:
            await bot.promote_chat_member(
                chat_id=chat_id, user_id=user_id,
                can_manage_chat=True, can_change_info=True,
                can_delete_messages=True, can_invite_users=True,
                can_restrict_members=True, can_pin_messages=True,
                can_promote_members=False,
            )
            promoted = await bot.get_chat_member(chat_id, user_id)
            if promoted.status == "administrator":
                if row["telegram_status"] == "ready":
                    with get_db_session() as session:
                        caretaker = session.execute(
                            text("SELECT caretaker_user_id FROM telegram_group_reserves WHERE chat_id = :chat_id"),
                            {"chat_id": chat_id},
                        ).scalar_one()
                    try:
                        await bot.send_message(
                            caretaker,
                            f"The creator joined reserve group {chat_id} and is now an admin. "
                            "Please leave the group now to finish the private handoff.",
                        )
                    except TelegramError:
                        logger.warning("Could not ask caretaker to leave allocated group %s", chat_id)
                return "owner_promoted"
        except TelegramError:
            if attempt == 2:
                raise
        await asyncio.sleep(0.5 * (attempt + 1))
    raise RuntimeError("Owner joined but Telegram did not confirm admin promotion")


def reserve_join_policy(chat_id: int, user_id: int) -> bool | None:
    """Return None for ordinary clubs, or whether a reserve-group join is allowed."""
    with get_db_session() as session:
        row = session.execute(
            text("""
                SELECT r.status, r.caretaker_user_id, c.owner_user_id,
                       c.status AS club_status, c.telegram_status,
                       cm.status AS member_status
                FROM telegram_group_reserves r
                LEFT JOIN clubs c ON c.club_id = r.club_id
                LEFT JOIN club_members cm ON cm.club_id = c.club_id AND cm.user_id = :user_id
                WHERE r.chat_id = :chat_id
                LIMIT 1
            """),
            {"chat_id": chat_id, "user_id": str(user_id)},
        ).mappings().fetchone()
        if not row:
            return None
        if user_id == row["caretaker_user_id"]:
            return row["status"] in {"available", "assigning", "needs_review"} or (
                row["status"] == "allocated" and row["telegram_status"] == "ready"
            )
        allowed = bool(
            row["status"] == "allocated"
            and row["club_status"] == "active"
            and row["member_status"] == "active"
        )
        if not allowed and row["status"] == "available":
            session.execute(
                text("""
                    UPDATE telegram_group_reserves
                    SET status = 'needs_review', last_error = 'Unexpected member joined'
                    WHERE chat_id = :chat_id AND status = 'available'
                """),
                {"chat_id": chat_id},
            )
        return allowed


def reserve_handoff_pending(chat_id: int) -> bool:
    """Hold Xaana group content while the registered caretaker is still inside."""
    with get_db_session() as session:
        return bool(session.execute(
            text("""
                SELECT 1
                FROM telegram_group_reserves r
                JOIN clubs c ON c.club_id = r.club_id
                WHERE r.chat_id = :chat_id AND r.status = 'allocated'
                  AND c.telegram_status = 'ready'
                LIMIT 1
            """),
            {"chat_id": chat_id},
        ).fetchone())


async def note_reserve_member_left(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Complete handoff only after the caretaker leaves and owner is an admin."""
    with get_db_session() as session:
        row = session.execute(
            text("""
                SELECT r.caretaker_user_id, c.club_id, c.owner_user_id
                FROM telegram_group_reserves r
                JOIN clubs c ON c.club_id = r.club_id
                WHERE r.chat_id = :chat_id AND r.status = 'allocated'
                  AND c.telegram_status = 'ready'
                LIMIT 1
            """),
            {"chat_id": chat_id},
        ).mappings().fetchone()
    if not row or int(row["caretaker_user_id"]) != user_id:
        return False
    owner = await bot.get_chat_member(chat_id, int(row["owner_user_id"]))
    if owner.status != "administrator":
        logger.warning("Caretaker left reserve %s before club owner became admin", chat_id)
        return False
    with get_db_session() as session:
        updated = session.execute(
            text("""
                UPDATE clubs SET telegram_status = 'connected', updated_at_utc = :now
                WHERE club_id = :club_id AND telegram_status = 'ready'
            """),
            {"club_id": row["club_id"], "now": utc_now_iso()},
        )
    if updated.rowcount == 1:
        try:
            await bot.send_message(int(row["owner_user_id"]), "Your club handoff is complete: the caretaker has left the Telegram group.")
        except TelegramError:
            logger.warning("Could not notify owner of completed reserve handoff for %s", chat_id)
    return updated.rowcount == 1


async def revoke_allocated_club_link(bot_token: str, chat_id: str | None, invite_link: str | None) -> None:
    """Best-effort cleanup when an allocated club is archived."""
    if not bot_token or not chat_id or not invite_link:
        return
    try:
        async with Bot(token=bot_token) as bot:
            await bot.revoke_chat_invite_link(int(chat_id), invite_link)
    except (TelegramError, ValueError):
        logger.warning("Could not revoke archived club invite for chat %s", chat_id)


async def notify_low_reserve_stock(bot_token: str, consumed_label: str) -> None:
    """Tell operators when the pool needs replenishing, without sharing links."""
    if not bot_token:
        return
    with get_db_session() as session:
        remaining = session.execute(
            text("SELECT COUNT(*) FROM telegram_group_reserves WHERE status = 'available'"),
        ).scalar_one()
    if remaining > 1:
        return
    try:
        async with Bot(token=bot_token) as bot:
            for admin_id in get_admin_ids():
                try:
                    await bot.send_message(
                        admin_id,
                        f"Reserve {consumed_label} was allocated. Only {remaining} ready reserve(s) remain. "
                        "Please prepare and register more clean groups.",
                    )
                except TelegramError:
                    logger.warning("Could not send low-reserve alert to admin %s", admin_id)
    except TelegramError:
        logger.warning("Could not initialize low-reserve alert")
