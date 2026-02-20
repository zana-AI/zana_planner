from datetime import datetime, timezone

import pytest

from models.models import Broadcast
from services import broadcast_service


class _FakeBroadcastsRepo:
    def __init__(self, broadcast: Broadcast):
        self._broadcast = broadcast

    def get_broadcast(self, broadcast_id: str):
        if broadcast_id != self._broadcast.broadcast_id:
            return None
        return self._broadcast

    def mark_broadcast_completed(self, broadcast_id: str):
        if broadcast_id == self._broadcast.broadcast_id:
            self._broadcast.status = "completed"
            return True
        return False


@pytest.mark.asyncio
async def test_execute_broadcast_from_db_uses_default_bot_token(monkeypatch):
    now = datetime.now(timezone.utc)
    fake_broadcast = Broadcast(
        broadcast_id="b-1",
        admin_id="123",
        message="hello",
        target_user_ids=[1, 2],
        scheduled_time_utc=now,
        status="pending",
        bot_token_id=None,
        created_at=now,
        updated_at=now,
    )
    fake_repo = _FakeBroadcastsRepo(fake_broadcast)
    monkeypatch.setattr(broadcast_service, "BroadcastsRepository", lambda: fake_repo)

    send_calls = []

    async def _fake_send(response_service, user_ids, message, rate_limit_delay=0.05, bot_token=None):
        send_calls.append(
            {
                "response_service": response_service,
                "user_ids": user_ids,
                "message": message,
                "bot_token": bot_token,
            }
        )
        return {"success": len(user_ids), "failed": 0}

    monkeypatch.setattr(broadcast_service, "send_broadcast", _fake_send)

    result = await broadcast_service.execute_broadcast_from_db(
        response_service=None,
        broadcast_id="b-1",
        default_bot_token="fallback-token",
    )

    assert result == {"success": 2, "failed": 0}
    assert len(send_calls) == 1
    assert send_calls[0]["bot_token"] == "fallback-token"
    assert fake_broadcast.status == "completed"


@pytest.mark.asyncio
async def test_execute_broadcast_from_db_without_delivery_channel_raises(monkeypatch):
    now = datetime.now(timezone.utc)
    fake_broadcast = Broadcast(
        broadcast_id="b-2",
        admin_id="123",
        message="hello",
        target_user_ids=[1],
        scheduled_time_utc=now,
        status="pending",
        bot_token_id=None,
        created_at=now,
        updated_at=now,
    )
    fake_repo = _FakeBroadcastsRepo(fake_broadcast)
    monkeypatch.setattr(broadcast_service, "BroadcastsRepository", lambda: fake_repo)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    with pytest.raises(ValueError):
        await broadcast_service.execute_broadcast_from_db(
            response_service=None,
            broadcast_id="b-2",
            default_bot_token=None,
        )

    # Keep pending so dispatcher can retry after config is fixed.
    assert fake_broadcast.status == "pending"

