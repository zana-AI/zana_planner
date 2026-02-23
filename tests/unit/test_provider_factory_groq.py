import os
import sys

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms.providers.factory import create_provider_adapter  # noqa: E402
from llms.providers.groq_adapter import GroqProviderAdapter  # noqa: E402


def test_create_provider_adapter_returns_groq_for_explicit_provider():
    cfg = {
        "LLM_PROVIDER": "groq",
        "GROQ_API_KEY": "test-key",
    }
    adapter = create_provider_adapter(cfg)
    assert isinstance(adapter, GroqProviderAdapter)
    assert adapter.name == "groq"


def test_create_provider_adapter_auto_uses_groq_when_only_groq_key_present():
    cfg = {
        "LLM_PROVIDER": "auto",
        "GROQ_API_KEY": "test-key",
        "OPENAI_API_KEY": "",
        "DEEPSEEK_API_KEY": "",
        "GCP_PROJECT_ID": "",
    }
    adapter = create_provider_adapter(cfg)
    assert isinstance(adapter, GroqProviderAdapter)


def test_create_provider_adapter_auto_prefers_groq_over_gcp():
    cfg = {
        "LLM_PROVIDER": "auto",
        "GROQ_API_KEY": "test-key",
        "GCP_PROJECT_ID": "proj-1",
    }
    adapter = create_provider_adapter(cfg)
    assert isinstance(adapter, GroqProviderAdapter)
