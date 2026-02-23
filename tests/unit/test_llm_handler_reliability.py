import os
import sys

from langchain_core.messages import AIMessage

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms.llm_handler import LLMHandler, _resolve_fallback_provider  # noqa: E402


def test_resolve_fallback_provider_autoswitches_to_gemini_when_openai_key_missing():
    provider, reason = _resolve_fallback_provider(
        fallback_enabled=True,
        requested_fallback="openai",
        primary_provider="gemini",
        has_openai_key=False,
        has_gemini_creds=True,
    )
    assert provider == "gemini"
    assert reason == "openai_key_missing"


def test_resolve_fallback_provider_keeps_openai_when_key_present():
    provider, reason = _resolve_fallback_provider(
        fallback_enabled=True,
        requested_fallback="openai",
        primary_provider="gemini",
        has_openai_key=True,
        has_gemini_creds=True,
    )
    assert provider == "openai"
    assert reason is None


def test_resolve_fallback_provider_disabled_returns_none():
    provider, reason = _resolve_fallback_provider(
        fallback_enabled=False,
        requested_fallback="openai",
        primary_provider="gemini",
        has_openai_key=False,
        has_gemini_creds=True,
    )
    assert provider is None
    assert reason is None


def test_classify_stop_reason_no_final_when_ai_and_final_response_missing():
    reason = LLMHandler._classify_stop_reason(
        iteration=0,
        max_iterations=6,
        final_ai=None,
        final_response_text="",
    )
    assert reason == "no_final_ai_message"


def test_classify_stop_reason_completed_when_final_response_exists_without_ai():
    reason = LLMHandler._classify_stop_reason(
        iteration=0,
        max_iterations=6,
        final_ai=None,
        final_response_text="ok",
    )
    assert reason == "completed"


def test_classify_stop_reason_tool_calls_executed_when_last_ai_has_tool_calls():
    ai = AIMessage(content="(calling tool)", tool_calls=[{"name": "get_promises", "args": {}, "id": "call_1"}])
    reason = LLMHandler._classify_stop_reason(
        iteration=0,
        max_iterations=6,
        final_ai=ai,
        final_response_text="",
    )
    assert reason == "tool_calls_executed"


def test_apply_final_response_failsafe_injects_message_when_blank():
    text, used = LLMHandler._apply_final_response_failsafe("   ")
    assert used is True
    assert "temporary issue" in text.lower()


def test_apply_final_response_failsafe_keeps_existing_text():
    text, used = LLMHandler._apply_final_response_failsafe("Hello there")
    assert used is False
    assert text == "Hello there"
