import importlib.util
from pathlib import Path
import pytest


def client():
    spec = importlib.util.spec_from_file_location("relay_client", Path(__file__).parents[2] / "scripts/caption_relay/client.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("server", ["http://xaana.club", "https://name:password@xaana.club", "https://xaana.club/?token=x"])
def test_credentials_never_sent_to_unsafe_origin(server):
    with pytest.raises(ValueError):
        client().api(server, "claim", "secret")


def test_fetch_rejects_urls_and_shell_fragments():
    with pytest.raises(ValueError):
        client().fetch("https://example.com/")


def test_pair_does_not_overwrite_existing_credentials(tmp_path):
    mod = client()
    path = tmp_path / "device.json"
    mod.save_config(path, {"token": "first"})
    with pytest.raises(FileExistsError):
        mod.save_config(path, {"token": "second"})
    assert "first" in path.read_text()


def test_subprocess_timeout_returns_retryable_result(monkeypatch):
    mod = client()
    def timeout(*args, **kwargs):
        raise mod.subprocess.TimeoutExpired("fetch", 90)
    monkeypatch.setattr(mod.subprocess, "run", timeout)
    assert mod.fetch("dQw4w9WgXcQ") == {"error": "timeout"}
