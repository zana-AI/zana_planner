import asyncio
import types

import pytest


def test_report_stats_logs_time_to_assigned_promise(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("telegram")

    from webapp.routers import youtube_watch as router_mod

    calls = {"add_action": None}

    class FakePlanner:
        def __init__(self, root_dir):
            assert root_dir == str(tmp_path)

        def get_promise(self, user_id, promise_id):
            return types.SimpleNamespace(id=promise_id) if user_id == 42 and promise_id == "T01" else None

        def add_action(self, user_id, promise_id, time_spent, notes=None, action_datetime=None):
            calls["add_action"] = (user_id, promise_id, time_spent, notes)
            return "ok"

    class FakeBot:
        def __init__(self, token):
            self.token = token

        async def send_message(self, chat_id, text):
            return None

    class FakeRequest:
        def __init__(self):
            self.app = types.SimpleNamespace(state=types.SimpleNamespace(bot_token="token", root_dir=str(tmp_path)))

        async def json(self):
            return {
                "init_data": "ok",
                "stats": {
                    "video_id": "dQw4w9WgXcQ",
                    "promise_id": "T01",
                    "time_spent_seconds": 180,
                    "segments": [[0, 180]],
                    "closed_via": "done",
                },
            }

        async def body(self):
            return b"{}"

    monkeypatch.setattr(router_mod, "validate_init_data", lambda _init_data, _bot_token: (True, 42))
    monkeypatch.setattr(router_mod, "append_stats", lambda **kwargs: None)
    monkeypatch.setattr(router_mod, "format_summary_message", lambda *_args, **_kwargs: "summary")
    monkeypatch.setattr(router_mod, "PlannerAPIAdapter", FakePlanner)
    monkeypatch.setattr("telegram.Bot", FakeBot)

    response = asyncio.run(router_mod.report_stats(FakeRequest()))

    assert response.status_code == 200
    assert calls["add_action"] is not None
    user_id, promise_id, time_spent, notes = calls["add_action"]
    assert user_id == 42
    assert promise_id == "T01"
    assert time_spent == pytest.approx(180 / 3600.0, rel=1e-6)
    assert "dQw4w9WgXcQ" in (notes or "")


def test_report_stats_skips_logging_for_tiny_watch_time(monkeypatch, tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("telegram")

    from webapp.routers import youtube_watch as router_mod

    calls = {"add_action": 0}

    class FakePlanner:
        def __init__(self, root_dir):
            assert root_dir == str(tmp_path)

        def get_promise(self, user_id, promise_id):
            return types.SimpleNamespace(id=promise_id)

        def add_action(self, user_id, promise_id, time_spent, notes=None, action_datetime=None):
            calls["add_action"] += 1
            return "ok"

    class FakeBot:
        def __init__(self, token):
            self.token = token

        async def send_message(self, chat_id, text):
            return None

    class FakeRequest:
        def __init__(self):
            self.app = types.SimpleNamespace(state=types.SimpleNamespace(bot_token="token", root_dir=str(tmp_path)))

        async def json(self):
            return {
                "init_data": "ok",
                "stats": {
                    "video_id": "dQw4w9WgXcQ",
                    "promise_id": "T01",
                    "time_spent_seconds": 1.5,
                    "segments": [[0, 1.5]],
                    "closed_via": "done",
                },
            }

        async def body(self):
            return b"{}"

    monkeypatch.setattr(router_mod, "validate_init_data", lambda _init_data, _bot_token: (True, 42))
    monkeypatch.setattr(router_mod, "append_stats", lambda **kwargs: None)
    monkeypatch.setattr(router_mod, "format_summary_message", lambda *_args, **_kwargs: "summary")
    monkeypatch.setattr(router_mod, "PlannerAPIAdapter", FakePlanner)
    monkeypatch.setattr("telegram.Bot", FakeBot)

    response = asyncio.run(router_mod.report_stats(FakeRequest()))

    assert response.status_code == 200
    assert calls["add_action"] == 0
