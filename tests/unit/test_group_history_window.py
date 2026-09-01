"""The group history window, and where it comes from.

Inbound group messages have always been persisted to `conversations`, but the
bot answered from a `deque` in process memory that every restart and deploy
cleared — so it would lose a thread it was already part of. These cover the
merge between the live deque and the stored history.
"""
import os
import sys
import types
from collections import defaultdict, deque

import pytest

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from planner_bot import PlannerBot  # noqa: E402


def _msg(mid, text, is_bot=False, name="Someone", from_db=False):
    return {
        "message_id": mid,
        "sender_user_id": 1,
        "sender_name": name,
        "text": text,
        "created_at_utc": "2026-09-01T13:00:00Z",
        "is_bot": is_bot,
        "from_db": from_db,
    }


class _Bot:
    """A PlannerBot with only the history machinery wired up."""

    GROUP_HISTORY_WINDOW = PlannerBot.GROUP_HISTORY_WINDOW
    _GROUP_HISTORY_REFETCH_SECONDS = PlannerBot._GROUP_HISTORY_REFETCH_SECONDS
    _get_recent_group_messages = PlannerBot._get_recent_group_messages
    _load_group_history = PlannerBot._load_group_history

    def __init__(self, live=(), stored=()):
        self._group_chat_history = defaultdict(lambda: deque(maxlen=40))
        self._group_chat_history[-100].extend(live)
        self._group_history_cache = {}
        self._stored = list(stored)
        self.db_calls = 0


@pytest.fixture
def patched_repo(monkeypatch):
    """Route ConversationRepository through the fake stored history."""
    holder = {}

    class _Repo:
        def get_recent_group_history(self, chat_id, limit=28):
            holder["bot"].db_calls += 1
            return list(holder["bot"]._stored)[-limit:]

    module = types.SimpleNamespace(ConversationRepository=_Repo)
    monkeypatch.setitem(sys.modules, "repositories.conversation_repo", module)
    return holder


def _ctx(chat_id=-100):
    return types.SimpleNamespace(chat_id=chat_id)


def test_full_live_history_never_touches_the_database(patched_repo):
    bot = _Bot(live=[_msg(i, f"m{i}") for i in range(40)])
    patched_repo["bot"] = bot

    out = bot._get_recent_group_messages(_ctx())

    assert len(out) == _Bot.GROUP_HISTORY_WINDOW
    assert bot.db_calls == 0


def test_cold_process_memory_is_filled_from_stored_history(patched_repo):
    """The restart case: nothing in RAM, the conversation still in Postgres."""
    bot = _Bot(live=[], stored=[_msg(i, f"old{i}", from_db=True) for i in range(10)])
    patched_repo["bot"] = bot

    out = bot._get_recent_group_messages(_ctx())

    assert [m["text"] for m in out] == [f"old{i}" for i in range(10)]
    assert bot.db_calls == 1


def test_stored_and_live_are_merged_with_live_last(patched_repo):
    bot = _Bot(
        live=[_msg(9, "live9"), _msg(10, "live10")],
        stored=[_msg(i, f"old{i}", from_db=True) for i in range(9)],
    )
    patched_repo["bot"] = bot

    out = bot._get_recent_group_messages(_ctx())

    assert [m["text"] for m in out][-2:] == ["live9", "live10"]
    assert len(out) == 11


def test_messages_present_in_both_sources_are_not_duplicated(patched_repo):
    bot = _Bot(live=[_msg(3, "three"), _msg(4, "four")],
               stored=[_msg(3, "three", from_db=True), _msg(4, "four", from_db=True)])
    patched_repo["bot"] = bot

    out = bot._get_recent_group_messages(_ctx())

    assert [m["message_id"] for m in out] == [3, 4]


def test_window_is_capped_after_merging(patched_repo):
    bot = _Bot(live=[_msg(100 + i, f"live{i}") for i in range(5)],
               stored=[_msg(i, f"old{i}", from_db=True) for i in range(50)])
    patched_repo["bot"] = bot

    out = bot._get_recent_group_messages(_ctx())

    assert len(out) == _Bot.GROUP_HISTORY_WINDOW
    assert out[-1]["text"] == "live4"


def test_quiet_club_does_not_requery_on_every_message(patched_repo):
    """A club that never fills the window would otherwise hit the DB every turn."""
    bot = _Bot(live=[_msg(1, "hi")], stored=[_msg(0, "older", from_db=True)])
    patched_repo["bot"] = bot

    for _ in range(5):
        bot._get_recent_group_messages(_ctx())

    assert bot.db_calls == 1


def test_database_failure_degrades_to_live_history(monkeypatch):
    class _Boom:
        def get_recent_group_history(self, *a, **k):
            raise RuntimeError("db down")

    monkeypatch.setitem(
        sys.modules,
        "repositories.conversation_repo",
        types.SimpleNamespace(ConversationRepository=_Boom),
    )
    bot = _Bot(live=[_msg(1, "still here")])

    out = bot._get_recent_group_messages(_ctx())

    assert [m["text"] for m in out] == ["still here"]


def test_missing_chat_id_returns_nothing():
    assert _Bot()._get_recent_group_messages(_ctx(chat_id=None)) == []
