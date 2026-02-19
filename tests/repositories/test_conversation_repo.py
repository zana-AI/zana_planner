import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from db.postgres_db import get_db_session
from repositories.conversation_repo import ConversationRepository
try:
    from tests.test_config import ensure_users_exist, unique_user_id
except ModuleNotFoundError:
    from test_config import ensure_users_exist, unique_user_id

pytestmark = [pytest.mark.repo, pytest.mark.requires_postgres]


SESSION_ID_RE = re.compile(r"^s-\d{8}T\d{6}Z-[0-9a-f]{8}$")


def test_save_message_assigns_same_session_id_for_close_messages():
    repo = ConversationRepository()
    user_id = unique_user_id()
    ensure_users_exist(user_id)

    repo.save_message(user_id=user_id, message_type="user", content="hello")
    repo.save_message(user_id=user_id, message_type="bot", content="hi there")

    messages = repo.get_recent_history(user_id=user_id, limit=2)
    assert len(messages) == 2

    session_ids = {m.get("conversation_session_id") for m in messages}
    assert len(session_ids) == 1
    session_id = next(iter(session_ids))
    assert session_id is not None
    assert SESSION_ID_RE.match(session_id)
    assert messages[0].get("conversation_session_time_tag_utc")


def test_save_message_starts_new_session_after_gap():
    repo = ConversationRepository()
    user_id = unique_user_id()
    ensure_users_exist(user_id)

    repo.save_message(user_id=user_id, message_type="user", content="first")
    first = repo.get_recent_history(user_id=user_id, limit=1)[0]
    first_session_id = first.get("conversation_session_id")
    assert first_session_id

    old_iso = (
        datetime.now(timezone.utc) - timedelta(hours=2)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with get_db_session() as session:
        session.execute(
            text(
                """
                UPDATE conversations
                SET created_at_utc = :old_iso
                WHERE id = :id
                """
            ),
            {"old_iso": old_iso, "id": first["id"]},
        )

    repo.save_message(user_id=user_id, message_type="user", content="second")
    messages = repo.get_recent_history(user_id=user_id, limit=2)
    latest_session_id = messages[0].get("conversation_session_id")

    assert latest_session_id
    assert latest_session_id != first_session_id
    assert SESSION_ID_RE.match(latest_session_id)


def test_recent_conversation_summary_is_chronological_and_session_aware():
    repo = ConversationRepository()
    user_id = unique_user_id()
    ensure_users_exist(user_id)

    rows = [
        ("user", "old user", "2026-01-10T09:00:00Z", "s-20260110T090000Z-11111111"),
        ("bot", "old bot", "2026-01-10T09:01:00Z", "s-20260110T090000Z-11111111"),
        ("user", "new user one", "2026-01-10T12:00:00Z", "s-20260110T120000Z-22222222"),
        ("bot", "new bot one", "2026-01-10T12:01:00Z", "s-20260110T120000Z-22222222"),
        ("user", "new user two", "2026-01-10T12:02:00Z", "s-20260110T120000Z-22222222"),
        ("bot", "new bot two", "2026-01-10T12:03:00Z", "s-20260110T120000Z-22222222"),
    ]
    with get_db_session() as session:
        for message_type, content, created_at_utc, session_id in rows:
            session.execute(
                text(
                    """
                    INSERT INTO conversations (
                        user_id, chat_id, message_id, message_type, content, created_at_utc, conversation_session_id
                    ) VALUES (
                        :user_id, :chat_id, :message_id, :message_type, :content, :created_at_utc, :session_id
                    )
                    """
                ),
                {
                    "user_id": str(user_id),
                    "chat_id": str(user_id),
                    "message_id": None,
                    "message_type": message_type,
                    "content": content,
                    "created_at_utc": created_at_utc,
                    "session_id": session_id,
                },
            )

    summary = repo.get_recent_conversation_summary(user_id=user_id, limit=2)
    assert "[Session 2026-01-10 12:00 UTC]" in summary
    assert "old user" not in summary

    assert summary.find("User: new user one") < summary.find("Bot: new bot one")
    assert summary.find("Bot: new bot one") < summary.find("User: new user two")
    assert summary.find("User: new user two") < summary.find("Bot: new bot two")
