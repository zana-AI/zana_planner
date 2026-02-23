import os
import sys

import pytest

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms.llm_env_utils import load_llm_env  # noqa: E402


def test_load_llm_env_groq_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "")

    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        load_llm_env()


def test_load_llm_env_groq_returns_expected_config(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("GROQ_PLAN_TIER", "developer")

    cfg = load_llm_env()

    assert cfg["LLM_PROVIDER"] == "groq"
    assert cfg["GROQ_API_KEY"] == "test-groq-key"
    assert cfg["GROQ_BASE_URL"] == "https://api.groq.com/openai/v1"
    assert cfg["GROQ_PLAN_TIER"] == "developer"
    assert cfg["LLM_GROQ_ROUTER_MODEL"] == "openai/gpt-oss-20b"
    assert cfg["LLM_GROQ_PLANNER_MODEL"] == "openai/gpt-oss-20b"
    assert cfg["LLM_GROQ_RESPONDER_MODEL"] == "openai/gpt-oss-20b"


def test_load_llm_env_auto_prefers_groq_when_groq_and_gcp_exist(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("GCP_PROJECT_ID", "gcp-project")
    monkeypatch.setenv("GCP_CREDENTIALS_B64", "e30=")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")

    cfg = load_llm_env()
    assert cfg["LLM_PROVIDER"] == "groq"


def test_load_llm_env_groq_defaults_enable_provider_layer_and_fallback(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("ENV", "")
    monkeypatch.setenv("ENVIRONMENT", "")
    monkeypatch.delenv("LLM_PROVIDER_LAYER_ENABLED", raising=False)
    monkeypatch.delenv("LLM_FALLBACK_ENABLED", raising=False)
    monkeypatch.delenv("LLM_FALLBACK_PROVIDER", raising=False)

    cfg = load_llm_env()

    assert cfg["LLM_PROVIDER"] == "groq"
    assert cfg["LLM_PROVIDER_LAYER_ENABLED"] is True
    assert cfg["LLM_FALLBACK_ENABLED"] is True
    assert cfg["LLM_FALLBACK_PROVIDER"] == "groq"
    assert cfg["LLM_FALLBACK_GROQ_MODEL"] == "llama-3.3-70b-versatile"
