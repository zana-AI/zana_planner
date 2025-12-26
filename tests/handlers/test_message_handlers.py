import asyncio
import os
import types

import pytest


@pytest.mark.handler
def test_reply_text_smart_selects_html_vs_markdown():
    pytest.importorskip("telegram")

    # MessageHandlers imports llm_handler which depends on LangGraph prebuilt tools;
    # skip if the local environment doesn't have that variant installed.
    pytest.importorskip("langgraph.prebuilt")

    from handlers.message_handlers import MessageHandlers

    calls = []

    class FakeMessage:
        async def reply_text(self, text, parse_mode=None):
            calls.append({"text": text, "parse_mode": parse_mode})

    async def run():
        await MessageHandlers._reply_text_smart(FakeMessage(), "<b>Zana:</b>\nHello")
        await MessageHandlers._reply_text_smart(FakeMessage(), "Plain markdown-ish text")

    asyncio.run(run())

    assert calls[0]["parse_mode"] == "HTML"
    assert calls[1]["parse_mode"] == "Markdown"


@pytest.mark.handler
def test_format_response_html_escapes_llm_and_log_text():
    pytest.importorskip("telegram")
    pytest.importorskip("langgraph.prebuilt")

    from handlers.message_handlers import MessageHandlers

    mh = MessageHandlers.__new__(MessageHandlers)  # avoid __init__ side-effects
    out = mh._format_response('hello <script>alert(1)</script>', {"k": "<b>v</b>"})
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "&lt;b&gt;v&lt;/b&gt;" in out
    assert "<blockquote" in out  # log is wrapped


@pytest.mark.handler
def test_handle_message_routes_urls_to_handle_link_message(tmp_path, monkeypatch):
    pytest.importorskip("telegram")
    pytest.importorskip("langgraph.prebuilt")

    import handlers.message_handlers as mh_mod
    from handlers.message_handlers import MessageHandlers

    # Patch language getter to avoid depending on i18n store internals.
    monkeypatch.setattr(mh_mod, "get_user_language", lambda _u: None)

    user_id = 123
    root_dir = tmp_path
    os.makedirs(root_dir / str(user_id), exist_ok=True)  # so start() is not called

    mh = MessageHandlers.__new__(MessageHandlers)
    mh.root_dir = str(root_dir)
    mh.plan_keeper = types.SimpleNamespace(settings_repo=types.SimpleNamespace(get_settings=lambda _uid: types.SimpleNamespace(voice_mode=None)))
    mh.llm_handler = types.SimpleNamespace(get_response_api=lambda *_a, **_k: {"response_to_user": "ok", "function_call": "no_op"})
    mh.application = types.SimpleNamespace(bot_data={})
    mh.content_service = types.SimpleNamespace(detect_urls=lambda text: ["https://example.com"], process_link=lambda url: {})

    routed = {"called": False}

    async def _handle_link_message(update, context, url, user_id, user_lang):
        routed["called"] = True
        assert url == "https://example.com"
        return

    mh._handle_link_message = _handle_link_message

    class FakeMessage:
        def __init__(self):
            self.text = "see https://example.com"

        async def reply_text(self, *_a, **_k):
            return None

    update = types.SimpleNamespace(
        message=FakeMessage(),
        effective_message=FakeMessage(),
        effective_user=types.SimpleNamespace(id=user_id),
        effective_chat=types.SimpleNamespace(id=user_id, type="private"),
    )
    context = types.SimpleNamespace(user_data={})

    asyncio.run(mh.handle_message(update, context))

    assert routed["called"] is True
