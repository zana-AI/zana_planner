"""Offline safety checks for the pre-created Telegram group pool."""

import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from telegram.error import TelegramError  # noqa: E402

from services import telegram_group_reserves as reserves  # noqa: E402


def _candidate_bot(*, member_count=1, can_promote=True):
    bot = SimpleNamespace(
        get_chat=AsyncMock(return_value=SimpleNamespace(type="supergroup", title="C0002")),
        get_me=AsyncMock(return_value=SimpleNamespace(id=999)),
        get_chat_member=AsyncMock(return_value=SimpleNamespace(
            status="administrator", can_change_info=True, can_invite_users=True,
            can_promote_members=can_promote, can_delete_messages=True,
            can_restrict_members=True,
        )),
        get_chat_member_count=AsyncMock(return_value=member_count),
        export_chat_invite_link=AsyncMock(return_value="https://t.me/+rotated"),
    )
    return bot


def test_inspect_reserve_accepts_a_bot_only_group():
    result = asyncio.run(reserves.inspect_reserve(_candidate_bot(), -100200))
    assert result["title"] == "C0002"
    assert result["bot_user_id"] == 999
    assert result["member_count"] == 1


@pytest.mark.parametrize("kwargs", [
    {"member_count": 2},  # a human is still inside, so the group is not free
    {"member_count": 3},
    {"can_promote": False},  # cannot promote the club creator later
])
def test_inspect_reserve_rejects_unclean_or_unmanageable_group(kwargs):
    with pytest.raises(reserves.ReserveValidationError):
        asyncio.run(reserves.inspect_reserve(_candidate_bot(**kwargs), -100200))


def test_admin_can_register_a_bot_only_group(monkeypatch):
    inserted = []

    class Session:
        def execute(self, statement, params=None):
            if "INSERT INTO telegram_group_reserves" in str(statement):
                inserted.append(params)
            return _QueryResult(None)

    class Context:
        def __enter__(self):
            return Session()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(reserves, "get_db_session", lambda: Context())
    result = asyncio.run(reserves.register_reserve(_candidate_bot(), -100200, 1086, "c0002"))
    assert result["label"] == "C0002"
    assert inserted[0]["actor"] == 1086
    assert "caretaker" not in inserted[0]


def test_registration_revokes_any_previously_issued_primary_link(monkeypatch):
    """Links handed out before registration must not survive into the pool."""
    inserted = []

    class Session:
        def execute(self, statement, params=None):
            if "INSERT INTO telegram_group_reserves" in str(statement):
                inserted.append(params)
            return _QueryResult(None)

    class Context:
        def __enter__(self):
            return Session()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(reserves, "get_db_session", lambda: Context())
    bot = _candidate_bot()
    result = asyncio.run(reserves.register_reserve(bot, -100200, 1086, "C0002"))
    bot.export_chat_invite_link.assert_awaited_once_with(-100200)
    assert result["primary_link_revoked"] is True
    # The rotated URL is discarded, never persisted onto the dormant reserve.
    assert not any("t.me" in str(value) for value in inserted[0].values())


def test_registration_is_refused_when_primary_link_cannot_be_revoked(monkeypatch):
    """A group whose old links may still admit strangers stays out of the pool."""
    inserted = []

    class Session:
        def execute(self, statement, params=None):
            if "INSERT INTO telegram_group_reserves" in str(statement):
                inserted.append(params)
            return _QueryResult(None)

    class Context:
        def __enter__(self):
            return Session()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(reserves, "get_db_session", lambda: Context())
    bot = _candidate_bot()
    bot.export_chat_invite_link = AsyncMock(side_effect=TelegramError("not enough rights"))
    with pytest.raises(reserves.ReserveValidationError):
        asyncio.run(reserves.register_reserve(bot, -100200, 1086, "C0002"))
    assert inserted == []


class _QueryResult:
    def __init__(self, row, rowcount=1):
        self.row = row
        self.rowcount = rowcount

    def mappings(self):
        return self

    def fetchone(self):
        return self.row

    def scalar_one(self):
        return self.row


class _FakeSession:
    def __init__(self, row):
        self.row = row

    def execute(self, statement, params=None):
        return _QueryResult(self.row)


class _FakeSessionContext:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return _FakeSession(self.row)

    def __exit__(self, *_args):
        return False


def _join_request(link="https://t.me/+guarded", user_id=501):
    return SimpleNamespace(
        chat=SimpleNamespace(id=-100200),
        from_user=SimpleNamespace(id=user_id),
        invite_link=SimpleNamespace(invite_link=link),
    )


def test_guarded_join_rejects_leaked_link_for_nonmember(monkeypatch):
    row = {
        "club_id": "club-1", "owner_user_id": "501", "telegram_invite_link": "https://t.me/+guarded",
        "telegram_status": "ready", "member_status": None,
    }
    monkeypatch.setattr(reserves, "get_db_session", lambda: _FakeSessionContext(row))
    bot = SimpleNamespace(
        decline_chat_join_request=AsyncMock(), approve_chat_join_request=AsyncMock(),
    )
    outcome = asyncio.run(reserves.handle_reserve_join_request(bot, _join_request()))
    assert outcome == "declined"
    bot.decline_chat_join_request.assert_awaited_once_with(-100200, 501)
    bot.approve_chat_join_request.assert_not_awaited()


def test_guarded_join_rejects_different_invite_even_for_member(monkeypatch):
    row = {
        "club_id": "club-1", "owner_user_id": "501", "telegram_invite_link": "https://t.me/+guarded",
        "telegram_status": "ready", "member_status": "active",
    }
    monkeypatch.setattr(reserves, "get_db_session", lambda: _FakeSessionContext(row))
    bot = SimpleNamespace(
        decline_chat_join_request=AsyncMock(), approve_chat_join_request=AsyncMock(),
    )
    outcome = asyncio.run(reserves.handle_reserve_join_request(bot, _join_request(link="https://t.me/+stale")))
    assert outcome == "declined"
    bot.approve_chat_join_request.assert_not_awaited()


def test_guarded_join_approves_active_member_without_promoting(monkeypatch):
    row = {
        "club_id": "club-1", "owner_user_id": "501", "telegram_invite_link": "https://t.me/+guarded",
        "telegram_status": "connected", "member_status": "active",
    }
    monkeypatch.setattr(reserves, "get_db_session", lambda: _FakeSessionContext(row))
    bot = SimpleNamespace(
        decline_chat_join_request=AsyncMock(), approve_chat_join_request=AsyncMock(),
        promote_chat_member=AsyncMock(),
    )
    outcome = asyncio.run(reserves.handle_reserve_join_request(bot, _join_request(user_id=777)))
    assert outcome == "member_approved"
    bot.approve_chat_join_request.assert_awaited_once_with(-100200, 777)
    bot.promote_chat_member.assert_not_awaited()


def test_join_policy_rejects_a_stranger_in_an_allocated_group(monkeypatch):
    row = {
        "status": "allocated", "telegram_status": "connected", "club_status": "active",
        "member_status": None, "owner_user_id": "501",
    }
    monkeypatch.setattr(reserves, "get_db_session", lambda: _FakeSessionContext(row))
    assert reserves.reserve_join_policy(-100200, 777) is False


def test_join_policy_admits_an_active_club_member(monkeypatch):
    row = {
        "status": "allocated", "telegram_status": "connected", "club_status": "active",
        "member_status": "active", "owner_user_id": "501",
    }
    monkeypatch.setattr(reserves, "get_db_session", lambda: _FakeSessionContext(row))
    assert reserves.reserve_join_policy(-100200, 501) is True


def test_creator_promotion_completes_setup_with_no_handoff_wait(monkeypatch):
    row = {
        "club_id": "club-1", "owner_user_id": "501", "telegram_invite_link": "https://t.me/+guarded",
        "telegram_status": "ready", "member_status": "active",
    }
    connected = []

    class Session(_FakeSession):
        def execute(self, statement, params=None):
            if "UPDATE clubs" in str(statement):
                connected.append(params)
                return _QueryResult(None, rowcount=1)
            return _QueryResult(row)

    class Context(_FakeSessionContext):
        def __enter__(self):
            return Session(row)

    monkeypatch.setattr(reserves, "get_db_session", lambda: Context(row))
    bot = SimpleNamespace(
        approve_chat_join_request=AsyncMock(), decline_chat_join_request=AsyncMock(),
        promote_chat_member=AsyncMock(),
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator")),
        send_message=AsyncMock(),
    )
    outcome = asyncio.run(reserves.handle_reserve_join_request(bot, _join_request()))
    assert outcome == "owner_promoted"
    bot.promote_chat_member.assert_awaited_once()
    # Nobody has to leave first, so the club is connected in the same step.
    assert len(connected) == 1
    assert connected[0]["club_id"] == "club-1"
    assert bot.send_message.await_args.args[0] == 501


def test_setup_is_not_completed_when_promotion_is_not_confirmed(monkeypatch):
    """A creator Telegram never confirms as admin must not read as connected."""
    row = {
        "club_id": "club-1", "owner_user_id": "501", "telegram_invite_link": "https://t.me/+guarded",
        "telegram_status": "ready", "member_status": "active",
    }
    connected = []

    class Session(_FakeSession):
        def execute(self, statement, params=None):
            if "UPDATE clubs" in str(statement):
                connected.append(params)
                return _QueryResult(None, rowcount=1)
            return _QueryResult(row)

    class Context(_FakeSessionContext):
        def __enter__(self):
            return Session(row)

    monkeypatch.setattr(reserves, "get_db_session", lambda: Context(row))
    bot = SimpleNamespace(
        approve_chat_join_request=AsyncMock(), decline_chat_join_request=AsyncMock(),
        promote_chat_member=AsyncMock(),
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member")),
        send_message=AsyncMock(),
    )
    with pytest.raises(RuntimeError):
        asyncio.run(reserves.handle_reserve_join_request(bot, _join_request()))
    assert connected == []


def test_allocation_renames_then_creates_guarded_link_and_commits(monkeypatch):
    club = {"club_id": "club-123", "owner_user_id": "501", "name": "Practice Persian"}
    reserve = {
        "chat_id": -100200, "label": "C0002",
        "original_title": "C0002",
    }
    updates = []

    class Session(_FakeSession):
        def execute(self, statement, params=None):
            sql = str(statement)
            if "SELECT club_id, owner_user_id, name" in sql:
                return _QueryResult(club)
            if "UPDATE clubs SET" in sql or "UPDATE telegram_group_reserves SET" in sql:
                updates.append((sql, params))
                return _QueryResult(None, rowcount=1)
            raise AssertionError(sql)

    class Context(_FakeSessionContext):
        def __enter__(self):
            return Session(club)

    class FakeBot:
        def __init__(self, token):
            self.title = "C0002"
            self.link_args = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get_chat(self, chat_id):
            return SimpleNamespace(type="supergroup", title=self.title)

        async def get_me(self):
            return SimpleNamespace(id=999)

        async def get_chat_member(self, chat_id, user_id):
            return SimpleNamespace(
                status="administrator", can_change_info=True,
                can_invite_users=True, can_promote_members=True,
                can_delete_messages=True, can_restrict_members=True,
            )

        async def get_chat_member_count(self, chat_id):
            return 1

        async def set_chat_title(self, chat_id, title):
            self.title = title

        async def create_chat_invite_link(self, **kwargs):
            self.link_args = kwargs
            return SimpleNamespace(invite_link="https://t.me/+guarded")

    bot = FakeBot("not-a-real-token")
    monkeypatch.setattr(reserves, "Bot", lambda token: bot)
    monkeypatch.setattr(reserves, "get_db_session", lambda: Context(club))
    monkeypatch.setattr(reserves, "_claim_oldest_reserve", lambda club_id: reserve)
    result = asyncio.run(reserves.allocate_reserve_to_club("club-123", "not-a-real-token"))
    assert result["chat_id"] == -100200
    assert bot.title == "Practice Persian"
    assert bot.link_args["creates_join_request"] is True
    assert len(updates) == 2
    assert updates[0][1]["link"] == "https://t.me/+guarded"


def test_failed_allocation_restores_title_and_quarantines_reserve(monkeypatch):
    club = {"club_id": "club-123", "owner_user_id": "501", "name": "Practice Persian"}
    reserve = {
        "chat_id": -100200, "label": "C0002",
        "original_title": "C0002",
    }
    quarantined = []

    class FakeBot:
        title = "C0002"

        def __init__(self, token):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def set_chat_title(self, chat_id, title):
            self.title = title

        async def get_chat(self, chat_id):
            return SimpleNamespace(title=self.title)

        async def create_chat_invite_link(self, **kwargs):
            raise RuntimeError("Telegram rejected link creation")

    bot = FakeBot("not-a-real-token")
    monkeypatch.setattr(reserves, "Bot", lambda token: bot)
    monkeypatch.setattr(reserves, "get_db_session", lambda: _FakeSessionContext(club))
    monkeypatch.setattr(reserves, "_claim_oldest_reserve", lambda club_id: reserve)
    monkeypatch.setattr(reserves, "inspect_reserve", AsyncMock(return_value={"title": "C0002"}))
    monkeypatch.setattr(reserves, "_mark_reserve_needs_review", lambda chat_id, error: quarantined.append((chat_id, error)))
    result = asyncio.run(reserves.allocate_reserve_to_club("club-123", "not-a-real-token"))
    assert result is None
    assert bot.title == "C0002"
    assert quarantined == [(-100200, "RuntimeError")]
