import os
import sys

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms.providers.factory import create_provider_adapter  # noqa: E402
from llms.providers.xai_adapter import XAIProviderAdapter  # noqa: E402


def test_create_provider_adapter_returns_xai_for_explicit_provider():
    cfg = {
        "LLM_PROVIDER": "xai",
        "XAI_API_KEY": "test-key",
    }
    adapter = create_provider_adapter(cfg)
    assert isinstance(adapter, XAIProviderAdapter)
    assert adapter.name == "xai"


def test_create_provider_adapter_accepts_grok_alias_for_xai():
    cfg = {
        "LLM_PROVIDER": "grok",
        "XAI_API_KEY": "test-key",
    }
    adapter = create_provider_adapter(cfg)
    assert isinstance(adapter, XAIProviderAdapter)
    assert adapter.name == "xai"


def test_create_provider_adapter_auto_uses_xai_when_only_xai_key_present():
    cfg = {
        "LLM_PROVIDER": "auto",
        "XAI_API_KEY": "test-key",
        "GROQ_API_KEY": "",
        "OPENAI_API_KEY": "",
        "DEEPSEEK_API_KEY": "",
        "GCP_PROJECT_ID": "",
    }
    adapter = create_provider_adapter(cfg)
    assert isinstance(adapter, XAIProviderAdapter)
