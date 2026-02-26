from __future__ import annotations

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest

from models.models import Broadcast
from services import broadcast_service
pytest.importorskip("fastapi")
from webapp.routers import admin as admin_router
from webapp.schemas import CreateBroadcastRequest


class _FakeBroadcastsRepo:
    def __init__(self, broadcast: Broadcast):
        self._broadcast = broadcast
        self.created = []

    def create_broadcast(self, **kwargs):
        self.created.append(kwargs)
        return self._broadcast.broadcast_id

    def get_broadcast(self, broadcast_id: str):
        if broadcast_id != self._broadcast.broadcast_id:
            return None
        return self._broadcast

    def mark_broadcast_completed(self, broadcast_id: str):
        if broadcast_id == self._broadcast.broadcast_id:
            self._broadcast.status = "completed"
            return True
        return False


class _MultiBroadcastRepo:
    def __init__(self):
        self.created = []
        self._broadcasts = {}
        self._counter = 0

    def create_broadcast(self, **kwargs):
        self._counter += 1
        broadcast_id = f"b-{self._counter}"
        now = kwargs.get("scheduled_time_utc")
        self._broadcasts[broadcast_id] = Broadcast(
            broadcast_id=broadcast_id,
            admin_id=str(kwargs.get("admin_id")),
            message=kwargs.get("message"),
            target_user_ids=kwargs.get("target_user_ids") or [],
            scheduled_time_utc=now,
            status="pending",
            bot_token_id=kwargs.get("bot_token_id"),
            created_at=now,
            updated_at=now,
        )
        self.created.append(kwargs)
        return broadcast_id

    def get_broadcast(self, broadcast_id: str):
        return self._broadcasts.get(broadcast_id)

    def mark_broadcast_completed(self, broadcast_id: str):
        broadcast = self._broadcasts.get(broadcast_id)
        if broadcast:
            broadcast.status = "completed"
            return True
        return False

@pytest.mark.asyncio
async def test_create_broadcast_send_now_schedules_immediate_dispatch_task(monkeypatch):
    now = datetime.now(timezone.utc)
    fake_broadcast = Broadcast(
        broadcast_id="b-2",
        admin_id="7",
        message="urgent",
        target_user_ids=[1001, 1002],
        scheduled_time_utc=now,
        status="pending",
        bot_token_id=None,
        created_at=now,
        updated_at=now,
    )
    fake_repo = _FakeBroadcastsRepo(fake_broadcast)
    monkeypatch.setattr(admin_router, "BroadcastsRepository", lambda: fake_repo)

    monkeypatch.setattr(
        broadcast_service,
        "get_all_users_from_db",
        lambda: [1001, 1002, 1003],
    )

    execute_calls = []

    async def _fake_execute(response_service, broadcast_id, default_bot_token=None):
        execute_calls.append(
            {
                "response_service": response_service,
                "broadcast_id": broadcast_id,
                "default_bot_token": default_bot_token,
            }
        )
        return {"success": 2, "failed": 0}

    monkeypatch.setattr(broadcast_service, "execute_broadcast_from_db", _fake_execute)

    scheduled_coroutines = []

    def _fake_create_task(coro):
        scheduled_coroutines.append(coro)
        return SimpleNamespace()

    monkeypatch.setattr(admin_router.asyncio, "create_task", _fake_create_task)

    fake_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(bot_token="app-bot-token")))
    request = CreateBroadcastRequest(
        message="urgent",
        target_user_ids=[1001, 1002],
        scheduled_time_utc=None,
        bot_token_id=None,
    )

    response = await admin_router.create_broadcast(
        request=fake_request,
        broadcast_request=request,
        admin_id=7,
    )

    assert response.broadcast_id == "b-2"
    assert response.status == "pending"
    assert len(scheduled_coroutines) == 1

    await scheduled_coroutines[0]
    assert execute_calls == [
        {
            "response_service": None,
            "broadcast_id": "b-2",
            "default_bot_token": "app-bot-token",
        }
    ]


@pytest.mark.asyncio
async def test_create_broadcast_scheduled_does_not_trigger_immediate_dispatch(monkeypatch):
    now = datetime.now(timezone.utc)
    fake_broadcast = Broadcast(
        broadcast_id="b-3",
        admin_id="7",
        message="later",
        target_user_ids=[1001],
        scheduled_time_utc=now + timedelta(hours=2),
        status="pending",
        bot_token_id=None,
        created_at=now,
        updated_at=now,
    )
    fake_repo = _FakeBroadcastsRepo(fake_broadcast)
    monkeypatch.setattr(admin_router, "BroadcastsRepository", lambda: fake_repo)

    monkeypatch.setattr(
        broadcast_service,
        "get_all_users_from_db",
        lambda: [1001, 1002],
    )

    scheduled_coroutines = []

    def _fake_create_task(coro):
        scheduled_coroutines.append(coro)
        return SimpleNamespace()

    monkeypatch.setattr(admin_router.asyncio, "create_task", _fake_create_task)

    future_dt = (now + timedelta(minutes=30)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    fake_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(bot_token="app-bot-token")))
    request = CreateBroadcastRequest(
        message="later",
        target_user_ids=[1001],
        scheduled_time_utc=future_dt,
        bot_token_id=None,
    )

    response = await admin_router.create_broadcast(
        request=fake_request,
        broadcast_request=request,
        admin_id=7,
    )

    assert response.broadcast_id == "b-3"
    assert response.status == "pending"
    assert scheduled_coroutines == []


@pytest.mark.asyncio
async def test_create_broadcast_translation_groups_by_language(monkeypatch):
    now = datetime.now(timezone.utc)
    repo = _MultiBroadcastRepo()
    monkeypatch.setattr(admin_router, "BroadcastsRepository", lambda: repo)

    monkeypatch.setattr(
        broadcast_service,
        "get_all_users_from_db",
        lambda: [1, 2, 3],
    )
    monkeypatch.setattr(
        admin_router,
        "_get_user_language_map",
        lambda _user_ids: {1: "en", 2: "fr", 3: "fr"},
    )

    translation_calls = []

    def _fake_translate(text: str, target_lang: str, source_lang: str = "en") -> str:
        translation_calls.append((source_lang, target_lang, text))
        return f"[{target_lang}] {text}"

    import handlers.translator as translator_module
    monkeypatch.setattr(translator_module, "translate_text", _fake_translate)

    scheduled_coroutines = []

    def _fake_create_task(coro):
        scheduled_coroutines.append(coro)
        return SimpleNamespace()

    monkeypatch.setattr(admin_router.asyncio, "create_task", _fake_create_task)

    fake_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(bot_token="app-bot-token")))
    request = CreateBroadcastRequest(
        message="hello",
        target_user_ids=[1, 2, 3],
        scheduled_time_utc=None,
        bot_token_id=None,
        translate_to_user_language=True,
        source_language="en",
    )

    response = await admin_router.create_broadcast(
        request=fake_request,
        broadcast_request=request,
        admin_id=7,
    )

    assert response.broadcast_id == "b-1"
    assert response.status == "pending"
    assert len(repo.created) == 2
    assert translation_calls == [("en", "fr", "hello")]
    assert len(scheduled_coroutines) == 2
