"""Group replies that ask for a second, action message.

The group responder has no tools, so before this existed it would answer a
"remind the others" request with a warm promise and then never act. It can now
request one bounded follow-up, which PlannerBot sends as its own message.
"""
import os
import sys

import pytest

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from langchain_core.messages import AIMessage  # noqa: E402

from llms.llm_handler import (  # noqa: E402
    GROUP_FOLLOWUP_REMIND_PENDING,
    LLMHandler,
    extract_group_followup,
)

MARKER = f"[[ACTION:{GROUP_FOLLOWUP_REMIND_PENDING}]]"


class _CapturingModel:
    """Returns a canned reply and records the prompt it was given."""

    def __init__(self, reply):
        self.reply = reply
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return AIMessage(content=self.reply)


class _Handler:
    """Minimal stand-in exposing only what get_response_group_safe touches."""

    _fallback_chain_model_specs = []
    _fallback_responder_model = None
    _fallback_label = None

    def __init__(self, reply):
        self.responder_model = _CapturingModel(reply)
        self.chat_model = self.responder_model

    def _strip_internal_reasoning(self, text):
        return text


SOME_PENDING = [
    {"user_id": "1", "name": "Javad", "status": "done"},
    {"user_id": "2", "name": "Homa", "status": "pending"},
    {"user_id": "3", "name": "Sepideh", "status": "pending"},
]
ALL_DONE = [{"user_id": "1", "name": "Javad", "status": "done"}]


def _context(members=SOME_PENDING, response_mode="FULL_REPLY"):
    return {
        "club_name": "Cheenva Club",
        "promise_text": "Play Cheenva",
        "member_status": members,
        "recent_messages": [],
        "sender_name": "Javad",
        "conversation_state": "active",
        "response_mode": response_mode,
    }


def _run(reply, **kwargs):
    handler = _Handler(reply)
    out = LLMHandler.get_response_group_safe(handler, "remind the others", _context(**kwargs), "en")
    return out, handler.responder_model.messages[0].content


def test_action_is_offered_when_someone_still_has_to_check_in():
    _, system_prompt = _run("ok")
    assert "WHAT YOU CAN AND CANNOT DO HERE" in system_prompt
    assert MARKER in system_prompt
    assert "Homa, Sepideh" in system_prompt


def test_reply_and_action_both_survive_the_round_trip():
    out, _ = _run(f"On it.{chr(10)}{MARKER}")
    assert extract_group_followup(out) == ("On it.", GROUP_FOLLOWUP_REMIND_PENDING)


def test_action_only_reply_keeps_the_action_instead_of_erroring():
    """The model sometimes answers with the marker alone. That is a real intent:
    the caller should send just the follow-up, not an error string."""
    out, _ = _run(MARKER)
    text, action = extract_group_followup(out)
    assert text == ""
    assert action == GROUP_FOLLOWUP_REMIND_PENDING


def test_genuinely_empty_reply_still_errors():
    out, _ = _run("")
    text, action = extract_group_followup(out)
    assert action is None
    assert text and "trouble" in text.lower()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"members": ALL_DONE},                    # nothing to remind anyone about
        {"response_mode": "SHORT_REPLY"},         # one-liner turn
        {"response_mode": "PROACTIVE"},           # nobody asked the bot anything
    ],
)
def test_action_is_not_offered_when_it_would_be_pointless_or_unsolicited(kwargs):
    _, system_prompt = _run("ok", **kwargs)
    assert MARKER not in system_prompt


@pytest.mark.parametrize(
    "kwargs",
    [{"members": ALL_DONE}, {"response_mode": "SHORT_REPLY"}, {"response_mode": "PROACTIVE"}],
)
def test_unoffered_action_is_ignored_even_if_the_model_emits_it(kwargs):
    """A model that emits the marker unprompted must not trigger a reminder."""
    out, _ = _run(f"Sure, I'll remind them.{chr(10)}{MARKER}", **kwargs)
    text, action = extract_group_followup(out)
    assert action is None
    assert MARKER not in text and "[[" not in text


def test_marker_never_reaches_the_chat_text():
    for reply in (f"hi {MARKER}", f"{MARKER} hi", f"hi{chr(10)}{MARKER}", "[[ACTION:BOGUS]]"):
        text, _ = extract_group_followup(_run(reply)[0])
        assert "[[" not in text and "ACTION:" not in text
