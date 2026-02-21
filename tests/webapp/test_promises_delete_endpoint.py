import asyncio
import importlib.util
from types import SimpleNamespace

import httpx
import pytest

FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None
if FASTAPI_AVAILABLE:
    from fastapi import FastAPI
    from webapp.dependencies import get_current_user
    from webapp.routers import promises as promises_router
else:
    FastAPI = object  # type: ignore[assignment]
    get_current_user = None  # type: ignore[assignment]
    promises_router = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi is not installed")


class _ASGITestClient:
    """Sync wrapper around httpx.AsyncClient + ASGITransport."""

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

    def delete(self, url: str, **kwargs):
        return self._request("DELETE", url, **kwargs)


def TestClient(app, base_url: str = "http://testserver"):
    return _ASGITestClient(app, base_url)


class _FakePromisesRepo:
    def __init__(self, by_user_promises: dict[int, set[str]]):
        self.by_user_promises = by_user_promises
        self.delete_calls: list[tuple[int, str]] = []

    def get_promise(self, user_id: int, promise_id: str):
        pid = (promise_id or "").strip().upper()
        if pid in self.by_user_promises.get(user_id, set()):
            return SimpleNamespace(id=pid)
        return None

    def delete_promise(self, user_id: int, promise_id: str) -> bool:
        pid = (promise_id or "").strip().upper()
        self.delete_calls.append((user_id, pid))
        user_promises = self.by_user_promises.get(user_id, set())
        if pid not in user_promises:
            return False
        user_promises.remove(pid)
        return True


def _build_app(current_user_id: int) -> FastAPI:
    app = FastAPI()
    app.include_router(promises_router.router)
    app.dependency_overrides[get_current_user] = lambda: current_user_id
    return app


def test_delete_promise_success(monkeypatch):
    fake_repo = _FakePromisesRepo({123: {"P10"}})
    monkeypatch.setattr(promises_router, "PromisesRepository", lambda: fake_repo)
    app = _build_app(123)
    client = TestClient(app)

    response = client.delete("/api/promises/P10")

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "message": "Promise #P10 deleted successfully",
    }
    assert fake_repo.by_user_promises[123] == set()
    assert fake_repo.delete_calls == [(123, "P10")]


def test_delete_promise_not_found(monkeypatch):
    fake_repo = _FakePromisesRepo({123: set()})
    monkeypatch.setattr(promises_router, "PromisesRepository", lambda: fake_repo)
    app = _build_app(123)
    client = TestClient(app)

    response = client.delete("/api/promises/P99")

    assert response.status_code == 404
    assert response.json()["detail"] == "Promise not found"
    assert fake_repo.delete_calls == []


def test_delete_promise_user_scope_enforced(monkeypatch):
    fake_repo = _FakePromisesRepo({123: {"P10"}, 456: {"P20"}})
    monkeypatch.setattr(promises_router, "PromisesRepository", lambda: fake_repo)
    app = _build_app(123)
    client = TestClient(app)

    response = client.delete("/api/promises/P20")

    assert response.status_code == 404
    assert response.json()["detail"] == "Promise not found"
    assert fake_repo.by_user_promises[456] == {"P20"}
    assert fake_repo.delete_calls == []
