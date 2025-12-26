import pytest

from llms.tool_wrappers import _current_user_id, _sanitize_user_id, _wrap_tool


def test_sanitize_user_id_allows_digits_only():
    assert _sanitize_user_id("123") == "123"
    assert _sanitize_user_id(456) == "456"
    with pytest.raises(ValueError):
        _sanitize_user_id("abc")
    with pytest.raises(ValueError):
        _sanitize_user_id("1../2")


def test_wrap_tool_injects_context_user_id_and_strips_model_user_id():
    calls = {}

    class DummyAdapter:
        def do_stuff(self, user_id, x):
            calls["user_id"] = user_id
            return x + 1

    dummy = DummyAdapter()
    wrapped = _wrap_tool(dummy.do_stuff, "do_stuff")

    token = _current_user_id.set("42")
    try:
        result = wrapped(x=1, user_id="999")  # user_id from model should be ignored
    finally:
        _current_user_id.reset(token)

    assert result == 2
    assert calls["user_id"] == "42"


def test_wrap_tool_raises_when_context_missing_user_id():
    class DummyAdapter:
        def do_stuff(self, user_id, x):
            return x

    wrapped = _wrap_tool(DummyAdapter().do_stuff, "do_stuff")
    with pytest.raises(ValueError):
        wrapped(x=1)
