import json
import os
from types import SimpleNamespace
import pytest
from services import caption_dispatcher as service


@pytest.mark.parametrize("timeout", [False, True])
def test_dispatcher_bounds_fetch_and_completes_lease(monkeypatch, timeout):
    calls = []
    transcript = {"language": "en", "cues": [{"start": 0, "end": 2, "text": "Hello"}]}
    class Queue:
        def claim(self):
            return {"video_id": "dQw4w9WgXcQ", "lease_token": "lease"}
        def finish(self, *args, **kwargs):
            calls.append((args, kwargs))
    def process(args, **kwargs):
        assert kwargs["timeout"] == 45
        assert "BOT_TOKEN" not in kwargs["env"]
        assert "DATABASE_URL_PROD" not in kwargs["env"]
        if timeout:
            raise service.subprocess.TimeoutExpired(args, 45)
        return SimpleNamespace(stdout=json.dumps({"transcript": transcript}))
    monkeypatch.setenv("BOT_TOKEN", "test-secret")
    monkeypatch.setenv("DATABASE_URL_PROD", "test-secret")
    monkeypatch.setattr(service, "VideoTranscriptFetchQueueRepository", Queue)
    monkeypatch.setattr(service.subprocess, "run", process)
    service.work_one()
    args, result = calls[0]
    assert args == ("dQw4w9WgXcQ", "lease")
    assert result["error"] == ("timeout" if timeout else "fetch_failed")
    assert bool(result["transcript"]) != timeout
