import os
import sys
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from planner_bot import PlannerBot  # noqa: E402


def test_bot_self_reference_detection_uses_general_aliases():
    zana_fa = "\u0632\u0627\u0646\u0627"
    aliases = ["xaana_bot", "xaana", "zana", zana_fa]

    assert PlannerBot._text_has_bot_self_reference(f"{zana_fa}\u060c \u06cc\u0647 \u0633\u0648\u0627\u0644 \u062f\u0627\u0631\u0645", aliases)
    assert PlannerBot._text_has_bot_self_reference("@xaana_bot what happened?", aliases)
    assert not PlannerBot._text_has_bot_self_reference("\u0686\u06cc\u0646\u0648\u0627 \u0627\u0645\u0631\u0648\u0632 \u0633\u062e\u062a \u0628\u0648\u062f", aliases)


def test_strip_bot_self_references_removes_alias_without_phrase_rule():
    zana_fa = "\u0632\u0627\u0646\u0627"
    aliases = ["xaana_bot", "xaana", "zana", zana_fa]

    assert PlannerBot._strip_bot_self_references(
        f"{zana_fa}\u060c \u06cc\u0647 \u0633\u0648\u0627\u0644 \u062f\u0627\u0631\u0645",
        aliases,
    ) == "\u06cc\u0647 \u0633\u0648\u0627\u0644 \u062f\u0627\u0631\u0645"
    assert PlannerBot._strip_bot_self_references("@xaana_bot what happened?", aliases) == "what happened?"


def test_group_conversation_state_ignores_current_message_and_uses_previous_recency():
    bot = object.__new__(PlannerBot)
    bot._group_chat_history = defaultdict(lambda: deque(maxlen=40))
    now = datetime.now(timezone.utc)
    chat_id = -100
    bot._group_chat_history[chat_id].append({
        "message_id": 10,
        "text": "previous",
        "created_at_utc": (now - timedelta(minutes=2)).isoformat(),
        "is_bot": False,
    })
    bot._group_chat_history[chat_id].append({
        "message_id": 11,
        "text": "current",
        "created_at_utc": now.isoformat(),
        "is_bot": False,
    })

    ctx = SimpleNamespace(chat_id=chat_id, message_id=11)

    assert bot._get_group_conversation_state(ctx) == "active"
