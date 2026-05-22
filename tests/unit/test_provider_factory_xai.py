import os
import sys
from types import SimpleNamespace

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from langchain_core.messages import HumanMessage  # noqa: E402

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


def test_xai_live_search_uses_responses_web_and_x_search_tools(monkeypatch):
    import openai

    captured = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                id="resp_123",
                model=kwargs["model"],
                output_text="live answer",
                usage=SimpleNamespace(input_tokens=3, output_tokens=4),
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.responses = FakeResponses()

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)

    adapter = XAIProviderAdapter({})
    model = adapter.build_role_model(
        "responder",
        {
            "xai_api_key": "test-key",
            "xai_base_url": "https://api.x.ai/v1",
            "xai_model": "grok-4.3",
            "live_search": True,
            "temperatures": {"responder": 0.2},
            "request_timeout_seconds": 12,
            "max_retries": 0,
        },
    )

    response = model.invoke([HumanMessage(content="What happened today?")])

    assert response.content == "live answer"
    assert captured["client_kwargs"]["base_url"] == "https://api.x.ai/v1"
    assert captured["model"] == "grok-4.3"
    assert captured["tools"] == [{"type": "web_search"}, {"type": "x_search"}]
    assert "search_parameters" not in captured


def test_xai_live_search_passes_x_search_parameters(monkeypatch):
    import openai

    captured = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(id="resp_123", model=kwargs["model"], output_text="live answer")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)

    adapter = XAIProviderAdapter({})
    model = adapter.build_role_model(
        "responder",
        {
            "xai_api_key": "test-key",
            "xai_base_url": "https://api.x.ai/v1",
            "xai_model": "grok-4.3",
            "live_search": True,
            "x_search_parameters": {
                "allowed_x_handles": ["xai"],
                "from_date": "2026-05-01",
                "enable_video_understanding": True,
                "ignored": "not forwarded",
            },
        },
    )

    model.invoke([HumanMessage(content="What are people saying about xAI?")])

    assert captured["tools"] == [
        {"type": "web_search"},
        {
            "type": "x_search",
            "allowed_x_handles": ["xai"],
            "from_date": "2026-05-01",
            "enable_video_understanding": True,
        },
    ]
