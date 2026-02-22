import asyncio
import importlib.util
from dataclasses import dataclass
from datetime import datetime

import httpx
import pytest

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
if FASTAPI_AVAILABLE:
    from fastapi import FastAPI
    from webapp.dependencies import get_current_user
    from webapp.routers import community as community_router
else:
    FastAPI = object  # type: ignore[assignment]
    get_current_user = None  # type: ignore[assignment]
    community_router = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi is not installed")


class _ASGITestClient:
    def __init__(self, app, base_url: str = "http://testserver"):
        self._app = app
        self._base_url = base_url

    def _request(self, method: str, url: str, **kwargs):
        async def _run():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self._app),
                base_url=self._base_url,
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(_run())

    def get(self, url: str, **kwargs):
        return self._request("GET", url, **kwargs)


def TestClient(app, base_url: str = "http://testserver"):
    return _ASGITestClient(app, base_url)


@dataclass
class _FakePromise:
    id: str
    text: str
    hours_per_week: float
    visibility: str


class _FakePromisesRepo:
    def __init__(self, promises):
        self.promises = promises

    def list_promises(self, user_id: int):
        return self.promises


class _FakeActionsRepo:
    pass


class _FakeReportsService:
    def __init__(self, promises_repo, actions_repo):
        self.promises_repo = promises_repo
        self.actions_repo = actions_repo

    def get_promise_summary(self, user_id: int, promise_id: str, ref_time: datetime):
        return {
            "weekly_hours": 2.0,
            "total_hours": 6.0,
            "streak": 3,
        }


def _build_app(current_user_id: int) -> FastAPI:
    app = FastAPI()
    app.include_router(community_router.router)
    app.dependency_overrides[get_current_user] = lambda: current_user_id
    return app


def test_public_promises_route_filters_private_promises(monkeypatch):
    fake_promises = [
        _FakePromise(id="P10", text="Public_Goal", hours_per_week=5.0, visibility="public"),
        _FakePromise(id="P11", text="Private_Goal", hours_per_week=4.0, visibility="private"),
    ]

    monkeypatch.setattr(community_router, "PromisesRepository", lambda: _FakePromisesRepo(fake_promises))
    monkeypatch.setattr(community_router, "ActionsRepository", lambda: _FakeActionsRepo())
    monkeypatch.setattr(community_router, "ReportsService", _FakeReportsService)

    app = _build_app(123)
    client = TestClient(app)
    response = client.get("/api/users/456/public-promises")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["promise_id"] == "P10"
    assert payload[0]["text"] == "Public Goal"
    payload_text = str(payload)
    assert "Private_Goal" not in payload_text
    assert "Private Goal" not in payload_text
