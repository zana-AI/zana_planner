"""Print the group member context that Xaana gives to the group LLM.

Usage inside the bot container:
    python scripts/debug_group_member_context.py --chat-id -100123 --query "کسی به اسم قلی داریم"
    python scripts/debug_group_member_context.py --club-id <uuid> --query "کسی به اسم قلی داریم"

This is read-only. It helps debug cases where the admin panel has name aliases
but the Telegram group bot still answers as if it cannot see them.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TM_BOT = ROOT / "tm_bot"
for path in (str(ROOT), str(TM_BOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from sqlalchemy import text

from db.postgres_db import get_db_session
from repositories.actions_repo import ActionsRepository
from repositories.clubs_repo import ClubsRepository
from services.club_reminder_service import _display_name


def _resolve_club_id(chat_id: str | None, club_id: str | None) -> str:
    if club_id:
        return club_id
    if not chat_id:
        raise SystemExit("Provide --club-id or --chat-id.")
    with get_db_session() as session:
        row = session.execute(
            text(
                """
                SELECT club_id, name
                FROM clubs
                WHERE telegram_chat_id = :chat_id
                LIMIT 1;
                """
            ),
            {"chat_id": str(chat_id)},
        ).mappings().fetchone()
    if not row:
        raise SystemExit(f"No club found for telegram_chat_id={chat_id!r}.")
    print(f"Resolved chat {chat_id} to club {row['club_id']} ({row.get('name')})")
    return str(row["club_id"])


def _query_terms(query: str) -> list[str]:
    return [term for term in re.split(r"[\s,،:؛؟?!()\\[\\]{}\"'«»]+", query or "") if len(term) >= 2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--club-id")
    parser.add_argument("--chat-id")
    parser.add_argument("--query", default="")
    args = parser.parse_args()

    club_id = _resolve_club_id(args.chat_id, args.club_id)
    raw_members = ClubsRepository().get_club_members_promises(club_id)
    promise_uuid = next((m.get("promise_uuid") for m in raw_members if m.get("promise_uuid")), None)
    checked_in = ActionsRepository().get_today_checkins(promise_uuid) if promise_uuid else set()

    print(f"\nActive members returned by get_club_members_promises: {len(raw_members)}")
    print(f"Shared promise UUID used for today's check-ins: {promise_uuid or '(none)'}")
    print("\nRows visible to the bot:")
    member_status = []
    for member in raw_members:
        display = _display_name(member)
        status = "done" if str(member["user_id"]) in checked_in else "pending"
        member_status.append({"name": display, "status": status})
        print(
            " - "
            f"user_id={member.get('user_id')} "
            f"first_name={member.get('first_name')!r} "
            f"username={member.get('username')!r} "
            f"non_latin_name={member.get('non_latin_name')!r} "
            f"latin_name={member.get('latin_name')!r} "
            f"display={display!r} "
            f"status={status}"
        )

    done = [m["name"] for m in member_status if m.get("status") == "done"]
    pending = [m["name"] for m in member_status if m.get("status") != "done"]
    context_line = (
        f"Today's check-ins ({len(done)}/{len(member_status)}): "
        f"checked in: {', '.join(done) if done else 'nobody yet'} | "
        f"not yet: {', '.join(pending) if pending else 'everyone'}"
    )

    print("\nExact member-status line sent to the group LLM:")
    print(context_line)

    if args.query:
        haystack = "\n".join(
            " ".join(
                str(member.get(field) or "")
                for field in ("first_name", "username", "non_latin_name", "latin_name")
            )
            for member in raw_members
        )
        print("\nQuery term visibility:")
        for term in _query_terms(args.query):
            print(f" - {term!r}: {'FOUND' if term in haystack else 'not found'}")


if __name__ == "__main__":
    main()

