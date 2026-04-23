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


@pytest.mark.handler
def test_handle_deploy_promote_prod_requires_admin(monkeypatch):
    pytest.importorskip("telegram")

    from handlers.callback_handlers import CallbackHandlers

    class FakeBot:
        async def send_message(self, chat_id, text, **kwargs):
            return None

    class FakeQuery:
        def __init__(self):
            self.from_user = types.SimpleNamespace(id=101, username="not-admin")
            self.message = types.SimpleNamespace(chat_id=101)
            self.answers = []
            self.edited = []

        async def answer(self, text=None, show_alert=False):
            self.answers.append((text, show_alert))
            return None

        async def edit_message_reply_markup(self, reply_markup=None):
            self.edited.append(reply_markup)
            return None

    monkeypatch.setattr("handlers.callback_handlers.is_admin", lambda _uid: False)

    callback_handler = CallbackHandlers(
        plan_keeper=types.SimpleNamespace(settings_service=types.SimpleNamespace(get_user_timezone=lambda _uid: "UTC")),
        application=types.SimpleNamespace(bot=FakeBot(), bot_data={}),
        response_service=types.SimpleNamespace(),
        miniapp_url="https://xaana.club",
    )

    query = FakeQuery()
    asyncio.run(callback_handler._handle_deploy_promote_prod(query, {"rid": "1", "sha": "abc1234"}))

    assert query.answers
    assert query.answers[-1][1] is True
    assert "Only bot admins" in (query.answers[-1][0] or "")
    assert query.edited == []


@pytest.mark.handler
def test_handle_deploy_promote_prod_dispatches_workflow(monkeypatch):
    pytest.importorskip("telegram")

    from handlers.callback_handlers import CallbackHandlers

    sent = []
    dispatched = {}

    class FakeBot:
        async def send_message(self, chat_id, text, **kwargs):
            sent.append({"chat_id": chat_id, "text": text, "kwargs": kwargs})
            return None

    class FakeQuery:
        def __init__(self):
            self.from_user = types.SimpleNamespace(id=202, username="admin-user")
            self.message = types.SimpleNamespace(chat_id=202)
            self.answers = []
            self.edited = []

        async def answer(self, text=None, show_alert=False):
            self.answers.append((text, show_alert))
            return None

        async def edit_message_reply_markup(self, reply_markup=None):
            self.edited.append(reply_markup)
            return None

    monkeypatch.setenv("GITHUB_DEPLOY_REPOSITORY", "acme/zana")
    monkeypatch.setenv("GITHUB_DEPLOY_TOKEN", "token-123")
    monkeypatch.delenv("GITHUB_DEPLOY_WORKFLOW", raising=False)
    monkeypatch.delenv("GITHUB_DEPLOY_REF", raising=False)
    monkeypatch.setattr("handlers.callback_handlers.is_admin", lambda _uid: True)

    callback_handler = CallbackHandlers(
        plan_keeper=types.SimpleNamespace(settings_service=types.SimpleNamespace(get_user_timezone=lambda _uid: "UTC")),
        application=types.SimpleNamespace(bot=FakeBot(), bot_data={}),
        response_service=types.SimpleNamespace(),
        miniapp_url="https://xaana.club",
    )

    def fake_dispatch(repository, workflow_file, ref, token, inputs=None):
        dispatched["repository"] = repository
        dispatched["workflow_file"] = workflow_file
        dispatched["ref"] = ref
        dispatched["token"] = token
        dispatched["inputs"] = inputs

    monkeypatch.setattr(callback_handler, "_dispatch_github_workflow", fake_dispatch)

    query = FakeQuery()
    asyncio.run(callback_handler._handle_deploy_promote_prod(query, {"rid": "12345", "sha": "abc1234"}))

    assert dispatched["repository"] == "acme/zana"
    assert dispatched["workflow_file"] == "deploy-prod.yml"
    assert dispatched["ref"] == "master"
    assert dispatched["token"] == "token-123"
    assert dispatched["inputs"]["requested_via"] == "telegram"
    assert dispatched["inputs"]["requested_by"] == "admin-user"
    assert dispatched["inputs"]["source_run_id"] == "12345"
    assert dispatched["inputs"]["source_sha"] == "abc1234"
    assert query.edited == [None]
    assert query.answers and query.answers[-1] == ("Prod promotion started.", False)
    assert sent and "#deploy_prod_requested" in sent[0]["text"]
