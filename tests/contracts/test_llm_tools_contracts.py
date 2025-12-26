import pytest

from llms.tool_wrappers import _current_user_id, _wrap_tool


@pytest.mark.contract
def test_wrap_tool_drops_invalid_parameters_and_still_calls_function():
    calls = {}

    class DummyAdapter:
        def do_stuff(self, user_id, x: int):
            calls["user_id"] = user_id
            calls["x"] = x
            return x + 1

    wrapped = _wrap_tool(DummyAdapter().do_stuff, "do_stuff")

    token = _current_user_id.set("123")
    try:
        # "junk" should be removed; "kwargs" should be removed if present.
        result = wrapped(x=1, junk="ignored", kwargs="also_ignored")
    finally:
        _current_user_id.reset(token)

    assert result == 2
    assert calls == {"user_id": "123", "x": 1}


@pytest.mark.contract
def test_wrap_tool_returns_friendly_message_when_required_args_missing():
    class DummyAdapter:
        def needs_two(self, user_id, a: str, b: str):
            return f"{a}-{b}"

    wrapped = _wrap_tool(DummyAdapter().needs_two, "needs_two")

    token = _current_user_id.set("42")
    try:
        msg = wrapped(a="only-a")  # missing b
    finally:
        _current_user_id.reset(token)

    assert isinstance(msg, str)
    assert "Missing required arguments for needs_two" in msg
    assert "b" in msg
