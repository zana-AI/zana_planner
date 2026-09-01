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


def test_group_router_pre_routes_persian_short_ack_without_groq(monkeypatch):
    def _fail_openai(*_args, **_kwargs):
        raise AssertionError("Groq should not be called for obvious short acknowledgements")

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_fail_openai))

    decision = group_router.route_group_message(
        message="\u0646\u0647",
        sender="Mahmoud",
        vibe="playful",
        is_mentioned=False,
        sender_checked_in=False,
        recent_messages=[],
        groq_api_key="test-key",
    )

    assert decision.action == "REACT_EMOJI"
    assert decision.reason == "short acknowledgement"


def test_group_router_pre_routes_one_character_noise_without_groq(monkeypatch):
    def _fail_openai(*_args, **_kwargs):
        raise AssertionError("Groq should not be called for one-character noise")

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_fail_openai))

    decision = group_router.route_group_message(
        message="\u0628",
        sender="Mahmoud",
        vibe="playful",
        is_mentioned=False,
        sender_checked_in=False,
        recent_messages=[],
        groq_api_key="test-key",
    )

    assert decision.action == "IGNORE"
    assert decision.reason == "one-character noise"


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


def _fresh_bot_data():
    return {}


def test_commanded_turns_are_never_throttled():
    bot_data = _fresh_bot_data()
    for _ in range(500):
        assert group_router.apply_budget(
            bot_data, -100, "coach", "FULL_REPLY", is_commanded=True
        ) == "FULL_REPLY"
    # Commanded turns spend nothing, so the spontaneous budget is untouched.
    assert bot_data.get("group_budget", {}).get("-100") is None


def test_spontaneous_text_flows_freely_below_the_taper(monkeypatch):
    monkeypatch.setattr(group_router.random, "random", lambda: 0.99)
    bot_data = _fresh_bot_data()
    limit = group_router.text_budget_for("coach")
    below_taper = int(limit * group_router._TAPER_START)
    for _ in range(below_taper):
        assert group_router.apply_budget(
            bot_data, -100, "coach", "FULL_REPLY", is_commanded=False
        ) == "FULL_REPLY"
    assert bot_data["group_budget"]["-100"]["count"] == below_taper


def test_taper_downgrades_text_to_a_reaction_instead_of_silence(monkeypatch):
    # random() always loses the taper roll, so every post-taper turn degrades.
    monkeypatch.setattr(group_router.random, "random", lambda: 0.999)
    bot_data = _fresh_bot_data()
    limit = group_router.text_budget_for("coach")
    entry = group_router._budget_entry(bot_data, -100)
    spent = int(limit * (group_router._TAPER_START + 0.1))
    entry["count"] = spent

    action = group_router.apply_budget(bot_data, -100, "coach", "FULL_REPLY", is_commanded=False)
    assert action == "REACT_EMOJI"
    assert entry["count"] == spent  # no text spent
    assert entry["reactions"] == 1


def test_taper_shortens_long_replies_near_the_cap(monkeypatch):
    monkeypatch.setattr(group_router.random, "random", lambda: 0.0)  # always wins the roll
    bot_data = _fresh_bot_data()
    limit = group_router.text_budget_for("coach")
    entry = group_router._budget_entry(bot_data, -100)
    entry["count"] = int(limit * group_router._SHORTEN_ABOVE)

    assert group_router.apply_budget(
        bot_data, -100, "coach", "FULL_REPLY", is_commanded=False
    ) == "SHORT_REPLY"


def test_exhausted_text_budget_still_leaves_room_for_reactions():
    bot_data = _fresh_bot_data()
    limit = group_router.text_budget_for("coach")
    entry = group_router._budget_entry(bot_data, -100)
    entry["count"] = limit

    assert group_router.apply_budget(
        bot_data, -100, "coach", "FULL_REPLY", is_commanded=False
    ) == "REACT_EMOJI"

    entry["reactions"] = limit * group_router._REACTION_BUDGET_FACTOR
    assert group_router.apply_budget(
        bot_data, -100, "coach", "REACT_EMOJI", is_commanded=False
    ) == "IGNORE"


def test_budget_resets_on_a_new_day():
    bot_data = {"group_budget": {"-100": {"date": "1999-01-01", "count": 999, "reactions": 999}}}
    assert group_router.apply_budget(
        bot_data, -100, "coach", "SHORT_REPLY", is_commanded=False
    ) == "SHORT_REPLY"
    assert bot_data["group_budget"]["-100"]["count"] == 1


def test_delay_matches_the_action_actually_taken():
    assert group_router.delay_for("REACT_EMOJI", is_commanded=False) < group_router.delay_for(
        "FULL_REPLY", is_commanded=False
    )
    assert group_router.delay_for("FULL_REPLY", is_commanded=True) == 2
