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

    mh = MessageHandlers.__new__(MessageHandlers)

    async def run():
        await mh._reply_text_smart(FakeMessage(), "<b>Xaana:</b>\nHello")
        await mh._reply_text_smart(FakeMessage(), "Plain markdown-ish text")

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
    _settings = types.SimpleNamespace(timezone="UTC", first_name="", username=None, last_seen=None)
    mh.plan_keeper = types.SimpleNamespace(
        settings_repo=types.SimpleNamespace(get_settings=lambda _uid: types.SimpleNamespace(voice_mode=None)),
        settings_service=types.SimpleNamespace(
            get_settings=lambda _uid: _settings,
            save_settings=lambda s: None,
        ),
    )
    mh.llm_handler = types.SimpleNamespace(get_response_api=lambda *_a, **_k: {"response_to_user": "ok", "function_call": "no_op"})
    mh.application = types.SimpleNamespace(bot_data={})
    mh.content_service = types.SimpleNamespace(detect_urls=lambda text: ["https://example.com"], process_link=lambda url: {})
    mh.response_service = types.SimpleNamespace(log_user_message=lambda **kw: None)

    routed = {"called": False}

    async def _handle_link_message(update, context, url, user_id, user_lang):
        routed["called"] = True
        assert url == "https://example.com"
        return

    mh._handle_link_message = _handle_link_message

    class FakeMessage:
        def __init__(self):
            self.text = "see https://example.com"
            self.message_id = 1

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


@pytest.mark.handler
def test_handle_message_youtube_builds_new_content_card_with_add_button(tmp_path, monkeypatch):
    pytest.importorskip("telegram")
    pytest.importorskip("langgraph.prebuilt")

    import utils.youtube_utils as yt_utils_mod
    import handlers.message_handlers as mh_mod
    from handlers.message_handlers import MessageHandlers

    monkeypatch.setattr(mh_mod, "get_user_language", lambda _u: None)
    monkeypatch.setattr(
        yt_utils_mod,
        "get_video_info",
        lambda _video_id, url=None: {
            "title": "Deep Work Sprint",
            "duration_seconds": 600,
            "captions_available": True,
            "channel": "Xaana Lab",
        },
    )

    user_id = 123
    root_dir = tmp_path
    os.makedirs(root_dir / str(user_id), exist_ok=True)

    sent = {}

    class FakeResponseService:
        def log_user_message(self, **kwargs):
            return None

        async def send_message(self, context, chat_id, text, user_id=None, reply_markup=None, parse_mode=None):
            sent["chat_id"] = chat_id
            sent["text"] = text
            sent["reply_markup"] = reply_markup
            return None

    mh = MessageHandlers.__new__(MessageHandlers)
    mh.root_dir = str(root_dir)
    mh.plan_keeper = types.SimpleNamespace(
        settings_repo=types.SimpleNamespace(get_settings=lambda _uid: types.SimpleNamespace(voice_mode=None)),
        settings_service=types.SimpleNamespace(
            get_settings=lambda _uid: types.SimpleNamespace(timezone="UTC", first_name="", username=None, last_seen=None),
            save_settings=lambda s: None,
        ),
    )
    mh.llm_handler = types.SimpleNamespace(get_response_api=lambda *_a, **_k: {"response_to_user": "ok", "function_call": "no_op"})
    mh.application = types.SimpleNamespace(bot_data={})
    mh.response_service = FakeResponseService()
    mh.miniapp_url = "https://xaana.club"
    mh.content_service = types.SimpleNamespace(detect_urls=lambda text: [text], process_link=lambda url: {})
    mh.content_resolve_service = types.SimpleNamespace(resolve=lambda _url: {"content_id": "content-123"})

    class FakeMessage:
        def __init__(self):
            self.text = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            self.message_id = 1

        async def reply_text(self, *_args, **_kwargs):
            return None

    update = types.SimpleNamespace(
        message=FakeMessage(),
        effective_message=FakeMessage(),
        effective_user=types.SimpleNamespace(id=user_id),
        effective_chat=types.SimpleNamespace(id=user_id, type="private"),
    )
    context = types.SimpleNamespace(user_data={}, bot=None)

    asyncio.run(mh.handle_message(update, context))

    assert "New content detected" in sent["text"]
    assert sent["reply_markup"] is not None
    first_button = sent["reply_markup"].inline_keyboard[0][0]
    assert first_button.callback_data is not None
    assert "a=add_content" in first_button.callback_data
    assert "cid=content-123" in first_button.callback_data


@pytest.mark.handler
def test_resolve_tts_language_code_uses_settings_language():
    pytest.importorskip("telegram")
    pytest.importorskip("langgraph.prebuilt")

    from handlers.message_handlers import MessageHandlers

    settings = types.SimpleNamespace(language="fa", voice_mode="enabled")
    assert MessageHandlers._resolve_tts_language_code(settings, None) == "fa-IR"


@pytest.mark.handler
def test_send_response_with_voice_mode_sends_voice_when_enabled():
    pytest.importorskip("telegram")
    pytest.importorskip("langgraph.prebuilt")

    from handlers.message_handlers import MessageHandlers

    captured = {"voice_calls": 0, "text_calls": 0, "lang": None}

    class FakeVoiceService:
        def synthesize_speech(self, text, language_code="en-US"):
            captured["lang"] = language_code
            return b"fake-ogg-opus"

    class FakeResponseService:
        async def reply_voice(self, update, voice, user_id=None):
            captured["voice_calls"] += 1
            assert user_id == 321
            payload = voice.read()
            assert payload == b"fake-ogg-opus"
            return None

        async def reply_text(self, *args, **kwargs):
            captured["text_calls"] += 1
            return None

    mh = MessageHandlers.__new__(MessageHandlers)
    mh.voice_service = FakeVoiceService()
    mh.response_service = FakeResponseService()

    update = types.SimpleNamespace(
        effective_user=types.SimpleNamespace(id=321),
        effective_message=types.SimpleNamespace(message_id=999),
        message=types.SimpleNamespace(),
    )
    context = types.SimpleNamespace()
    settings = types.SimpleNamespace(voice_mode="enabled", language="fa")

    asyncio.run(
        mh._send_response_with_voice_mode(
            update,
            context,
            "Hello",
            settings,
            None,
        )
    )

    assert captured["voice_calls"] == 1
    assert captured["text_calls"] == 0
    assert captured["lang"] == "fa-IR"
