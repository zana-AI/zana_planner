import os
import sys

import pytest

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms.llm_env_utils import load_llm_env  # noqa: E402


def _clear_other_llm_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "GCP_PROJECT_ID",
        "GCP_CREDENTIALS_B64",
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "GROK_API_KEY",
    ):
        monkeypatch.setenv(key, "")


def test_load_llm_env_xai_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    _clear_other_llm_keys(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "xai")
    monkeypatch.setenv("XAI_API_KEY", "")

    with pytest.raises(ValueError, match="XAI_API_KEY"):
        load_llm_env()


def test_load_llm_env_accepts_grok_alias_and_returns_xai_config(monkeypatch: pytest.MonkeyPatch):
    _clear_other_llm_keys(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "grok")
    monkeypatch.setenv("XAI_API_KEY", "test-xai-key")
    monkeypatch.setenv("XAI_BASE_URL", "https://api.x.ai/v1")

    cfg = load_llm_env()

    assert cfg["LLM_PROVIDER"] == "xai"
    assert cfg["LLM_PROVIDER_REQUESTED"] == "grok"
    assert cfg["XAI_API_KEY"] == "test-xai-key"
    assert cfg["XAI_BASE_URL"] == "https://api.x.ai/v1"
    assert cfg["LLM_XAI_ROUTER_MODEL"] == "grok-4-1-fast-non-reasoning"
    assert cfg["LLM_XAI_PLANNER_MODEL"] == "grok-4-1-fast-non-reasoning"
    assert cfg["LLM_XAI_RESPONDER_MODEL"] == "grok-4-1-fast-non-reasoning"
    # xAI fallback escalates to the slower, heavier model rather than repeating
    # the primary, so it must differ from the role models above.
    assert cfg["LLM_FALLBACK_XAI_MODEL"] == "grok-4.3"
    assert cfg["LLM_FALLBACK_XAI_MODEL"] != cfg["LLM_XAI_ROUTER_MODEL"]


def test_load_llm_env_accepts_grok_api_key_alias(monkeypatch: pytest.MonkeyPatch):
    _clear_other_llm_keys(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "xai")
    monkeypatch.setenv("XAI_API_KEY", "")
    monkeypatch.setenv("GROK_API_KEY", "test-grok-key")

    cfg = load_llm_env()

    assert cfg["LLM_PROVIDER"] == "xai"
    assert cfg["XAI_API_KEY"] == "test-grok-key"


def test_load_llm_env_auto_uses_xai_when_only_xai_key_present(monkeypatch: pytest.MonkeyPatch):
    _clear_other_llm_keys(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("XAI_API_KEY", "test-xai-key")

    cfg = load_llm_env()

    assert cfg["LLM_PROVIDER"] == "xai"
    assert cfg["LLM_PROVIDER_LAYER_ENABLED"] is True
    assert cfg["LLM_PLANNER_MODEL"] == "grok-4-1-fast-non-reasoning"


def test_fallback_stays_enabled_in_production_for_non_groq_providers(
    monkeypatch: pytest.MonkeyPatch,
):
    """Pinning a non-Groq provider must not silently disable the fallback chain.

    The default used to be `llm_provider == "groq" or env_name in {staging,...}`,
    so switching production from Groq to xAI left prod with no fallback at all:
    any xAI outage would surface as an error string in the club group.
    """
    _clear_other_llm_keys(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "xai")
    monkeypatch.setenv("XAI_API_KEY", "test-xai-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("LLM_FALLBACK_ENABLED", raising=False)

    cfg = load_llm_env()

    assert cfg["LLM_PROVIDER"] == "xai"
    assert cfg["LLM_FALLBACK_ENABLED"] is True
    assert cfg["LLM_FALLBACK_PROVIDER"] != "xai"


def test_explicit_fallback_disable_is_still_respected(monkeypatch: pytest.MonkeyPatch):
    _clear_other_llm_keys(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "xai")
    monkeypatch.setenv("XAI_API_KEY", "test-xai-key")
    monkeypatch.setenv("LLM_FALLBACK_ENABLED", "false")

    assert load_llm_env()["LLM_FALLBACK_ENABLED"] is False
