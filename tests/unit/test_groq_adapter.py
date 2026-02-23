import os
import sys

import pytest

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms.providers.groq_adapter import GroqProviderAdapter  # noqa: E402
from llms.providers.types import LLMInvokeOptions  # noqa: E402


def test_groq_adapter_blocks_model_on_tool_choice_mismatch(monkeypatch: pytest.MonkeyPatch):
    adapter = GroqProviderAdapter({})
    blocked = {}

    def _fake_mark_rate_limited(provider, model_id, retry_after_s=None, reset_hint=None):
        blocked["provider"] = provider
        blocked["model_id"] = model_id
        blocked["retry_after_s"] = retry_after_s
        blocked["reset_hint"] = reset_hint

    monkeypatch.setattr("llms.providers.groq_adapter.mark_rate_limited", _fake_mark_rate_limited)

    class _Model:
        model_name = "openai/gpt-oss-20b"

        def invoke(self, _messages, **_kwargs):
            raise Exception(
                "Error code: 400 - {'error': {'message': 'Tool choice is none, but model called a tool', "
                "'type': 'invalid_request_error', 'code': 'tool_use_failed'}}"
            )

    with pytest.raises(Exception):
        adapter.invoke(
            model=_Model(),
            messages=[],
            options=LLMInvokeOptions(
                purpose="router",
                metadata={"provider": "groq", "model": "openai/gpt-oss-20b"},
            ),
        )

    assert blocked["provider"] == "groq"
    assert blocked["model_id"] == "openai/gpt-oss-20b"
    assert blocked["retry_after_s"] == 60.0
    assert blocked["reset_hint"] is None
