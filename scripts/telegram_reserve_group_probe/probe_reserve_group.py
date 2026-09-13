"""Verify one pre-reserved Telegram group can serve a Xaana club instantly.

The probe waits for a group command, discovers the group's numeric chat ID,
checks this bot's administrator permissions, creates a one-use temporary invite
link, and sends it privately to the command sender. It is intentionally
standalone: it never opens the Xaana database and never logs credentials. The
explicit --handoff mode prints its fresh invite for a human-in-the-loop test.
"""

from __future__ import annotations

import asyncio
import argparse
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot
from telegram.error import Forbidden, TelegramError


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_COMMAND = "/reserve_test"
DEFAULT_TIMEOUT_SECONDS = 300
INVITE_TTL_MINUTES = 15
DEFAULT_PROBE_TITLE = "Xaana reserve group probe"
HANDOFF_CLAIM_COMMAND = "/reserve_claim"


def _load_probe_env() -> None:
    env_file = os.getenv("RESERVE_ENV_FILE")
    load_dotenv(Path(env_file) if env_file else SCRIPT_DIR / ".env")


def _command_matches(text: str | None, command: str, bot_username: str) -> bool:
    """Accept /reserve_test and /reserve_test@Javad_bot_test_bot."""
    if not text:
        return False
    first_word = text.strip().split(maxsplit=1)[0]
    return first_word in {command, f"{command}@{bot_username}"}


def _get_timeout_seconds() -> int:
    raw = os.getenv("RESERVE_TEST_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return max(30, min(value, 900))


async def _skip_existing_updates(bot: Bot, allowed_updates: list[str] | None = None) -> int | None:
    """Ignore stale updates so this run waits only for a fresh command."""
    updates = await bot.get_updates(timeout=0, allowed_updates=allowed_updates)
    if not updates:
        return None
    return updates[-1].update_id + 1


async def _check_title_and_permissions(chat_id: int, probe_title: str) -> int:
    """Rename a known test group, verify the result, then restore its title."""
    _load_probe_env()
    token = (os.getenv("RESERVE_BOT_TOKEN") or "").strip()
    if not token:
        print("Missing RESERVE_BOT_TOKEN. Set it in this directory's .env.")
        return 2
    if not probe_title or len(probe_title) > 128:
        print("Probe title must contain 1–128 characters.")
        return 2

    async with Bot(token=token) as bot:
        try:
            me = await bot.get_me()
            chat = await bot.get_chat(chat_id)
            member = await bot.get_chat_member(chat_id, me.id)
        except TelegramError as error:
            print(f"Could not inspect test group: {error}")
            return 1

        original_title = chat.title or ""
        if chat.type not in {"group", "supergroup"} or not original_title:
            print("FAIL: target must be a named group or supergroup.")
            return 1
        if original_title == probe_title:
            print("FAIL: probe title matches the current title; choose a different temporary title.")
            return 1

        rights = (
            "can_change_info",
            "can_invite_users",
            "can_promote_members",
            "can_restrict_members",
            "can_delete_messages",
            "can_pin_messages",
        )
        print(f"Group: {original_title} ({chat.id})")
        print(f"Bot: @{me.username}, status: {member.status}")
        for right in rights:
            print(f"  {right}: {bool(getattr(member, right, False))}")

        if member.status != "administrator" or not bool(getattr(member, "can_change_info", False)):
            print("FAIL: the bot needs administrator 'Change Group Info' permission.")
            return 1

        renamed = False
        restored = False
        try:
            await bot.set_chat_title(chat_id=chat_id, title=probe_title)
            renamed = True
            observed_title = (await bot.get_chat(chat_id)).title
            if observed_title != probe_title:
                print(f"FAIL: Telegram did not return the requested temporary title: {observed_title!r}")
                return 1
            print("PASS: bot changed the group title to the requested temporary title.")
        except TelegramError as error:
            print(f"FAIL: title change failed: {error}")
            return 1
        finally:
            if renamed:
                try:
                    await bot.set_chat_title(chat_id=chat_id, title=original_title)
                    restored_title = (await bot.get_chat(chat_id)).title
                    if restored_title == original_title:
                        restored = True
                        print(f"PASS: original title restored: {original_title}")
                    else:
                        print(f"WARNING: restore was requested, but Telegram returned {restored_title!r}.")
                except TelegramError as error:
                    print(f"WARNING: could not restore original title {original_title!r}: {error}")

    return 0 if restored else 1


async def _run_probe() -> int:
    _load_probe_env()
    token = (os.getenv("RESERVE_BOT_TOKEN") or "").strip()
    if not token:
        print("Missing RESERVE_BOT_TOKEN. Copy .env.example to .env and set the test-bot token.")
        return 2

    command = (os.getenv("RESERVE_TEST_COMMAND") or DEFAULT_COMMAND).strip()
    if not command.startswith("/") or any(char.isspace() for char in command):
        print("RESERVE_TEST_COMMAND must be one Telegram command, for example /reserve_test.")
        return 2

    timeout_seconds = _get_timeout_seconds()
    async with Bot(token=token) as bot:
        try:
            me = await bot.get_me()
            offset = await _skip_existing_updates(bot)
        except TelegramError as error:
            print(f"Could not contact Telegram: {error}")
            print("If this bot has a webhook, remove or disable that webhook before using getUpdates.")
            return 1

        deadline = asyncio.get_running_loop().time() + timeout_seconds
        print(f"Connected as @{me.username}. Waiting up to {timeout_seconds} seconds.")
        print(f"In the reserved group, send {command}. The command sender must have started this bot privately.")

        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            try:
                updates = await bot.get_updates(
                    offset=offset,
                    timeout=min(25, max(1, int(remaining))),
                    allowed_updates=["message"],
                )
            except TelegramError as error:
                print(f"Telegram polling failed: {error}")
                return 1

            for update in updates:
                offset = update.update_id + 1
                message = update.effective_message
                chat = update.effective_chat
                sender = update.effective_user
                if not message or not chat or not sender:
                    continue
                if chat.type not in {"group", "supergroup"}:
                    continue
                if not _command_matches(message.text, command, me.username):
                    continue

                try:
                    full_chat = await bot.get_chat(chat.id)
                    bot_member = await bot.get_chat_member(chat.id, me.id)
                    can_invite = bool(getattr(bot_member, "can_invite_users", False))
                    is_admin = getattr(bot_member, "status", "") in {"administrator", "creator", "owner"}

                    print("Reserve group detected:")
                    print(f"  chat_id: {full_chat.id}")
                    print(f"  title: {full_chat.title or '(no title)'}")
                    print(f"  type: {full_chat.type}")
                    if full_chat.username:
                        print(f"  public_username: @{full_chat.username}")
                    else:
                        print("  public_username: none (private group)")
                    print(f"  bot_status: {getattr(bot_member, 'status', 'unknown')}")
                    print(f"  can_invite_users: {can_invite}")

                    if not is_admin or not can_invite:
                        print("FAIL: the bot is not an admin with 'Invite Users via Link' permission.")
                        return 1

                    invite = await bot.create_chat_invite_link(
                        chat_id=chat.id,
                        expire_date=datetime.now(timezone.utc) + timedelta(minutes=INVITE_TTL_MINUTES),
                        member_limit=1,
                        name="reserve-group-probe",
                    )
                    await bot.send_message(
                        chat_id=sender.id,
                        text=(
                            "✅ Reserve-group probe succeeded. Here is a one-person invite link "
                            f"that expires in {INVITE_TTL_MINUTES} minutes:\n\n{invite.invite_link}"
                        ),
                        disable_web_page_preview=True,
                    )
                except Forbidden:
                    print("FAIL: Telegram would not let the bot DM the command sender. Start the bot in private first, then retry.")
                    return 1
                except TelegramError as error:
                    print(f"FAIL: reserve-group capability check failed: {error}")
                    return 1

                print("PASS: a reserved group can mint and deliver a single-use invite immediately.")
                return 0

    print("Timed out without a matching group command. No changes were made.")
    return 1


def _joined_group(old_status: str, new_status: str) -> bool:
    return old_status in {"left", "kicked"} and new_status in {"member", "restricted"}


async def _run_handoff(chat_id: int) -> int:
    """Bind a private claimant to a one-use invite, then verify admin promotion."""
    _load_probe_env()
    token = (os.getenv("RESERVE_BOT_TOKEN") or "").strip()
    if not token:
        print("Missing RESERVE_BOT_TOKEN in this directory's .env.")
        return 2

    async with Bot(token=token) as bot:
        try:
            me = await bot.get_me()
            chat = await bot.get_chat(chat_id)
            bot_member = await bot.get_chat_member(chat_id, me.id)
            admins = await bot.get_chat_administrators(chat_id)
            owners = {entry.user.id for entry in admins if entry.status in {"creator", "owner"}}
            if chat.type != "supergroup":
                print("FAIL: the handoff test requires a supergroup.")
                return 1
            if bot_member.status != "administrator" or not all(
                getattr(bot_member, right, False)
                for right in ("can_invite_users", "can_promote_members")
            ):
                print("FAIL: the bot needs Invite Users and Add New Admins permissions.")
                return 1
            offset = await _skip_existing_updates(bot, ["message", "chat_member"])
            invite = await bot.create_chat_invite_link(
                chat_id=chat_id,
                expire_date=datetime.now(timezone.utc) + timedelta(minutes=INVITE_TTL_MINUTES),
                member_limit=1,
                name="reserve-handoff-probe",
            )
        except TelegramError as error:
            print(f"FAIL: could not prepare the handoff: {error.__class__.__name__}")
            return 1

        claim_code = secrets.token_urlsafe(12)
        claimant_id: int | None = None
        joined_ids: set[int] = set()
        promoted = False
        print(f"Ready: @{me.username} is an admin in {chat.title} ({chat_id}).")
        print(f"Fresh, one-person invite (expires in {INVITE_TTL_MINUTES} minutes): {invite.invite_link}")
        print(f"From the SECOND account, privately message @{me.username}: {HANDOFF_CLAIM_COMMAND} {claim_code}")
        print("The bot will promote only that claimant after observing it join through this exact link.")

        try:
            deadline = asyncio.get_running_loop().time() + INVITE_TTL_MINUTES * 60
            while asyncio.get_running_loop().time() < deadline:
                remaining = deadline - asyncio.get_running_loop().time()
                updates = await bot.get_updates(
                    offset=offset,
                    timeout=min(20, max(1, int(remaining))),
                    allowed_updates=["message", "chat_member"],
                    read_timeout=30,
                )
                for update in updates:
                    offset = update.update_id + 1
                    change = update.chat_member
                    if change and change.chat.id == chat_id:
                        new_member = change.new_chat_member
                        old_member = change.old_chat_member
                        if (
                            _joined_group(old_member.status, new_member.status)
                            and change.invite_link
                            and change.invite_link.invite_link == invite.invite_link
                        ):
                            joined_ids.add(new_member.user.id)
                            print(f"Observed account {new_member.user.id} join via the fresh invite.")

                    message = update.message
                    if message and message.chat.type == "private" and message.from_user:
                        parts = (message.text or "").strip().split()
                        if not parts or parts[0] not in {HANDOFF_CLAIM_COMMAND, f"{HANDOFF_CLAIM_COMMAND}@{me.username}"}:
                            continue
                        sender_id = message.from_user.id
                        if len(parts) != 2 or not secrets.compare_digest(parts[1], claim_code):
                            await bot.send_message(sender_id, "That handoff claim is invalid or expired.")
                        elif sender_id in owners or sender_id == me.id:
                            await bot.send_message(sender_id, "Use your second account for this handoff test.")
                        elif claimant_id is not None and sender_id != claimant_id:
                            await bot.send_message(sender_id, "This handoff is already claimed by another account.")
                        else:
                            claimant_id = sender_id
                            print(f"Claim accepted from account {claimant_id}.")
                            await bot.send_message(
                                sender_id,
                                "Claim accepted. Open the one-person invite link and join the group. I'll verify your role.",
                            )

                if claimant_id is None or claimant_id not in joined_ids:
                    continue

                member = await bot.get_chat_member(chat_id, claimant_id)
                if member.status not in {"member", "restricted"}:
                    print(f"FAIL: claimant is not a regular group member (status: {member.status}).")
                    return 1
                await bot.promote_chat_member(
                    chat_id=chat_id,
                    user_id=claimant_id,
                    can_manage_chat=True,
                    can_change_info=True,
                    can_delete_messages=True,
                    can_invite_users=True,
                    can_restrict_members=True,
                    can_pin_messages=True,
                    can_promote_members=False,
                )
                verified = await bot.get_chat_member(chat_id, claimant_id)
                if verified.status != "administrator":
                    print(f"FAIL: Telegram did not confirm admin promotion (status: {verified.status}).")
                    return 1
                promoted = True
                print(f"PASS: account {claimant_id} joined through the fresh link and is now an administrator.")
                print("The original owner can now leave; run a fresh audit afterward to verify final roles.")
                try:
                    await bot.send_message(claimant_id, "You're now an admin of the test group. The original owner may leave.")
                except TelegramError:
                    print("Note: private success notification failed, but Telegram confirmed the admin role.")
                return 0
            print("Timed out waiting for a matching private claim and join; nobody was promoted.")
            return 1
        except TelegramError as error:
            print(f"FAIL: handoff interrupted by {error.__class__.__name__}; check actual roles before leaving.")
            return 1
        finally:
            try:
                await bot.revoke_chat_invite_link(chat_id, invite.invite_link)
                print("Temporary invite revoked.")
            except TelegramError as error:
                print(f"WARNING: could not revoke the invite ({error.__class__.__name__}).")
            if not promoted:
                print("Do not leave yet; a verified successor admin has not been confirmed.")


async def _audit_handoff(chat_id: int) -> int:
    """Read-only check of the group's current bot, owner, and admin roles."""
    _load_probe_env()
    token = (os.getenv("RESERVE_BOT_TOKEN") or "").strip()
    if not token:
        print("Missing RESERVE_BOT_TOKEN in this directory's .env.")
        return 2
    async with Bot(token=token) as bot:
        try:
            chat = await bot.get_chat(chat_id)
            admins = await bot.get_chat_administrators(chat_id)
        except TelegramError as error:
            print(f"FAIL: audit could not read group roles ({error.__class__.__name__}).")
            return 1
        print(f"Group: {chat.title} ({chat.id})")
        for entry in admins:
            print(f"  user_id={entry.user.id} username=@{entry.user.username or '(none)'} status={entry.status} bot={entry.user.is_bot}")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chat-id", type=int, help="Known test group ID; enables title/permission probe")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--handoff", action="store_true", help="Mint a fresh invite and promote a privately verified joiner")
    modes.add_argument("--audit", action="store_true", help="Read-only admin-role audit after the owner leaves")
    parser.add_argument(
        "--probe-title",
        default=DEFAULT_PROBE_TITLE,
        help="Temporary title to set before restoring the original title",
    )
    args = parser.parse_args()
    if (args.handoff or args.audit) and args.chat_id is None:
        parser.error("--handoff and --audit require --chat-id")
    if args.handoff:
        raise SystemExit(asyncio.run(_run_handoff(args.chat_id)))
    if args.audit:
        raise SystemExit(asyncio.run(_audit_handoff(args.chat_id)))
    if args.chat_id is not None:
        raise SystemExit(asyncio.run(_check_title_and_permissions(args.chat_id, args.probe_title)))
    raise SystemExit(asyncio.run(_run_probe()))
