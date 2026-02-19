import asyncio
import types

import pytest


@pytest.mark.handler
def test_handle_add_content_adds_to_library_and_removes_add_button(monkeypatch):
    pytest.importorskip("telegram")

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    import repositories.content_repo as content_repo_mod
    from handlers.callback_handlers import CallbackHandlers

    calls = {}

    class FakeContentRepository:
        def get_user_content(self, user_id, content_id):
            calls["lookup"] = (user_id, content_id)
            return None

        def add_user_content(self, user_id, content_id):
            calls["added"] = (user_id, content_id)
            return "uc-1"

    monkeypatch.setattr(content_repo_mod, "ContentRepository", FakeContentRepository)

    class FakeResponseService:
        async def edit_message_reply_markup(self, query, reply_markup=None, log_conversation=False):
            calls["edited_markup"] = reply_markup
            return None

    class FakeMessage:
        def __init__(self):
            self.reply_markup = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("➕ Add to My Contents", callback_data="a=add_content&cid=content-1")],
                    [InlineKeyboardButton("▶️ Watch in Mini App", url="https://xaana.club")],
                ]
            )
            self.replies = []

        async def reply_text(self, text, **_kwargs):
            self.replies.append(text)
            return None

    class FakeQuery:
        def __init__(self):
            self.from_user = types.SimpleNamespace(id=42)
            self.message = FakeMessage()
            self.answers = []

        async def answer(self, text=None, show_alert=False):
            self.answers.append((text, show_alert))
            return None

    callback_handler = CallbackHandlers(
        plan_keeper=types.SimpleNamespace(settings_service=types.SimpleNamespace(get_user_timezone=lambda _uid: "UTC")),
        application=types.SimpleNamespace(bot_data={}),
        response_service=FakeResponseService(),
        miniapp_url="https://xaana.club",
    )

    query = FakeQuery()
    asyncio.run(callback_handler._handle_add_content(query, user_id=42, content_id="content-1", url_id=None, user_lang=None))

    assert calls["added"] == ("42", "content-1")
    assert query.message.replies and "Added to your contents" in query.message.replies[0]
    assert calls["edited_markup"] is not None
    flat_buttons = [btn for row in calls["edited_markup"].inline_keyboard for btn in row]
    assert all("a=add_content" not in (btn.callback_data or "") for btn in flat_buttons)
