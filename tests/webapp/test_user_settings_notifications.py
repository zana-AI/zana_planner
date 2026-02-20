import asyncio

import httpx
from fastapi import FastAPI

from models.models import UserSettings
from webapp.dependencies import get_current_user
from webapp.routers import users as users_router


class FakeSettingsRepo:
    def __init__(self, settings: UserSettings):
        self.settings = settings
        self.save_calls = 0

    def get_settings(self, user_id: int) -> UserSettings:
        return self.settings

    def save_settings(self, settings: UserSettings) -> None:
        self.settings = settings
        self.save_calls += 1


def _build_app(monkeypatch, fake_repo: FakeSettingsRepo, notifications: list) -> FastAPI:
    app = FastAPI()
    app.include_router(users_router.router)
    app.dependency_overrides[get_current_user] = lambda: 123
    app.state.bot_token = "test-bot-token"

    monkeypatch.setattr(users_router, "get_settings_repo", lambda _request: fake_repo)
    monkeypatch.setattr(users_router, "update_user_activity", lambda _request, _user_id: None)

    def _capture_notification(request, user_id: int, **kwargs):
        notifications.append({"user_id": user_id, **kwargs})

    monkeypatch.setattr(users_router, "_notify_settings_change", _capture_notification)
    return app


class _ASGITestClient:
    """Sync wrapper around httpx.AsyncClient + ASGITransport (works with httpx 0.28+)."""

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

    def post(self, url: str, **kwargs):
        return self._request("POST", url, **kwargs)

    def patch(self, url: str, **kwargs):
        return self._request("PATCH", url, **kwargs)


def TestClient(app, base_url: str = "http://testserver"):
    return _ASGITestClient(app, base_url)


def test_update_user_settings_language_change_triggers_notification(monkeypatch):
    fake_repo = FakeSettingsRepo(
        UserSettings(user_id="123", timezone="UTC", language="en", voice_mode="disabled")
    )
    notifications = []
    app = _build_app(monkeypatch, fake_repo, notifications)
    client = TestClient(app)

    response = client.patch("/api/user/settings", json={"language": "fr"})
    assert response.status_code == 200
    assert response.json()["language"] == "fr"
    assert len(notifications) == 1
    assert notifications[0]["user_id"] == 123
    assert notifications[0]["language"] == "fr"
    assert notifications[0]["user_language"] == "fr"
    assert notifications[0]["timezone"] is None
    assert notifications[0]["voice_mode"] is None


def test_update_user_settings_no_change_does_not_trigger_notification(monkeypatch):
    fake_repo = FakeSettingsRepo(
        UserSettings(user_id="123", timezone="UTC", language="en", voice_mode="disabled")
    )
    notifications = []
    app = _build_app(monkeypatch, fake_repo, notifications)
    client = TestClient(app)

    response = client.patch("/api/user/settings", json={"language": "en"})
    assert response.status_code == 200
    assert response.json()["language"] == "en"
    assert notifications == []


def test_update_user_timezone_force_change_triggers_notification(monkeypatch):
    fake_repo = FakeSettingsRepo(
        UserSettings(user_id="123", timezone="UTC", language="fa", voice_mode="enabled")
    )
    notifications = []
    app = _build_app(monkeypatch, fake_repo, notifications)
    client = TestClient(app)

    response = client.post("/api/user/timezone", json={"tz": "Europe/Paris", "force": True})
    assert response.status_code == 200
    assert response.json()["timezone"] == "Europe/Paris"
    assert fake_repo.settings.timezone == "Europe/Paris"
    assert len(notifications) == 1
    assert notifications[0]["user_id"] == 123
    assert notifications[0]["timezone"] == "Europe/Paris"
    assert notifications[0]["user_language"] == "fa"
    assert notifications[0].get("language") is None
    assert notifications[0].get("voice_mode") is None


def test_update_user_timezone_force_same_value_skips_notification(monkeypatch):
    fake_repo = FakeSettingsRepo(
        UserSettings(user_id="123", timezone="Europe/Paris", language="en", voice_mode=None)
    )
    notifications = []
    app = _build_app(monkeypatch, fake_repo, notifications)
    client = TestClient(app)

    response = client.post("/api/user/timezone", json={"tz": "Europe/Paris", "force": True})
    assert response.status_code == 200
    assert response.json()["timezone"] == "Europe/Paris"
    assert notifications == []
