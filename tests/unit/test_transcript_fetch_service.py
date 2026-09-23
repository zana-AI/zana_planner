import importlib.util
from pathlib import Path


def _service_module():
    path = Path(__file__).parents[2] / "scripts" / "transcript_fetch_service.py"
    spec = importlib.util.spec_from_file_location("transcript_fetch_service_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_claim_treats_postgres_update_zero_as_an_empty_queue(monkeypatch):
    service = _service_module()
    monkeypatch.setattr(service, "sql", lambda _statement: "UPDATE 0")

    assert service.claim(900) is None


def test_claim_returns_the_video_and_attempt_count(monkeypatch):
    service = _service_module()
    monkeypatch.setattr(service, "sql", lambda _statement: "dQw4w9WgXcQ|2")

    assert service.claim(900) == ("dQw4w9WgXcQ", 2)
