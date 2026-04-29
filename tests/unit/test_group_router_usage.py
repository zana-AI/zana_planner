import os
import sys
import types

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms import group_router  # noqa: E402
from llms.providers.usage import extract_tokens  # noqa: E402


def test_extract_tokens_supports_raw_openai_usage_object():
    response = types.SimpleNamespace(
        usage=types.SimpleNamespace(prompt_tokens=17, completion_tokens=5)
    )

    assert extract_tokens(response) == (17, 5)


def test_group_router_logs_successful_raw_groq_call(monkeypatch):
    logged = []

    class _Usage:
        prompt_tokens = 11
        completion_tokens = 3

    class _Message:
        content = '{"action":"REACT_EMOJI","emoji":"ok","reason":"ack"}'

    class _Choice:
        message = _Message()

    class _Response:
        choices = [_Choice()]
        usage = _Usage()

    class _Completions:
        def create(self, **kwargs):
            assert kwargs["model"] == group_router._ROUTER_MODEL
            return _Response()

    class _Client:
        def __init__(self, **_kwargs):
            self.chat = types.SimpleNamespace(completions=_Completions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_Client))
    monkeypatch.setattr(group_router, "record_usage_safely", lambda **kwargs: logged.append(kwargs))

    decision = group_router.route_group_message(
        message="I played today",
        sender="Javad",
        vibe="coach",
        is_mentioned=False,
        sender_checked_in=True,
        recent_messages=[],
        groq_api_key="test-key",
    )

    assert decision.action == "REACT_EMOJI"
    assert len(logged) == 1
    assert logged[0]["provider"] == "groq"
    assert logged[0]["model_name"] == group_router._ROUTER_MODEL
    assert logged[0]["role"] == "group_router"
    assert logged[0]["input_tokens"] == 11
    assert logged[0]["output_tokens"] == 3
    assert logged[0]["success"] is True


def test_group_router_logs_failed_attempts_without_breaking_heuristic(monkeypatch):
    logged = []

    class _Completions:
        def create(self, **_kwargs):
            raise RuntimeError("network down")

    class _Client:
        def __init__(self, **_kwargs):
            self.chat = types.SimpleNamespace(completions=_Completions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_Client))
    monkeypatch.setattr(group_router, "record_usage_safely", lambda **kwargs: logged.append(kwargs))

    decision = group_router.route_group_message(
        message="Xaana?",
        sender="Javad",
        vibe="coach",
        is_mentioned=True,
        sender_checked_in=False,
        recent_messages=[],
        groq_api_key="test-key",
    )

    assert decision.action == "FULL_REPLY"
    assert [row["model_name"] for row in logged] == [
        group_router._ROUTER_MODEL,
        group_router._FALLBACK_MODEL,
    ]
    assert all(row["role"] == "group_router" for row in logged)
    assert all(row["success"] is False for row in logged)
    assert all(row["error_type"] == "RuntimeError" for row in logged)


def test_group_router_pre_routes_emoji_only_without_groq(monkeypatch):
    def _fail_openai(*_args, **_kwargs):
        raise AssertionError("Groq should not be called for obvious emoji-only input")

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_fail_openai))

    decision = group_router.route_group_message(
        message="😂😂",
        sender="Homa",
        vibe="playful",
        is_mentioned=False,
        sender_checked_in=False,
        recent_messages=[],
        groq_api_key="test-key",
    )

    assert decision.action == "REACT_EMOJI"
    assert decision.reason == "emoji-only"


def test_group_router_pre_routes_direct_status_question_without_groq(monkeypatch):
    def _fail_openai(*_args, **_kwargs):
        raise AssertionError("Groq should not be called for obvious status question")

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_fail_openai))

    decision = group_router.route_group_message(
        message="who checked in today?",
        sender="Javad",
        vibe="coach",
        is_mentioned=True,
        sender_checked_in=False,
        recent_messages=[],
        groq_api_key="test-key",
    )

    assert decision.action == "FULL_REPLY"
    assert decision.reason == "direct club/status question"


def test_group_router_pre_routes_address_only_mention_as_reaction(monkeypatch):
    def _fail_openai(*_args, **_kwargs):
        raise AssertionError("Groq should not be called for address-only mention")

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_fail_openai))

    decision = group_router.route_group_message(
        message="",
        sender="Mahmoud",
        vibe="playful",
        is_mentioned=True,
        sender_checked_in=False,
        recent_messages=[],
        groq_api_key="test-key",
    )

    assert decision.action == "REACT_EMOJI"
    assert decision.reason == "address-only"
