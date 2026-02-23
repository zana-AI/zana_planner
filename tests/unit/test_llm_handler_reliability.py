import os
import sys

from langchain_core.messages import AIMessage, HumanMessage

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms.llm_handler import (  # noqa: E402
    LLMHandler,
    _is_fallback_eligible_error,
    _resolve_fallback_provider,
    _resolve_fallback_role_providers,
)
from llms.model_policy import mark_rate_limited  # noqa: E402


def test_resolve_fallback_provider_autoswitches_to_gemini_when_openai_key_missing():
    provider, reason = _resolve_fallback_provider(
        fallback_enabled=True,
        requested_fallback="openai",
        primary_provider="gemini",
        has_openai_key=False,
        has_deepseek_key=False,
        has_gemini_creds=True,
        has_groq_key=False,
    )
    assert provider == "gemini"
    assert reason == "openai_key_missing"


def test_resolve_fallback_provider_keeps_openai_when_key_present():
    provider, reason = _resolve_fallback_provider(
        fallback_enabled=True,
        requested_fallback="openai",
        primary_provider="gemini",
        has_openai_key=True,
        has_deepseek_key=False,
        has_gemini_creds=True,
        has_groq_key=False,
    )
    assert provider == "openai"
    assert reason is None


def test_resolve_fallback_provider_autoselects_deepseek_when_openai_key_missing_and_deepseek_available():
    provider, reason = _resolve_fallback_provider(
        fallback_enabled=True,
        requested_fallback="openai",
        primary_provider="gemini",
        has_openai_key=False,
        has_deepseek_key=True,
        has_gemini_creds=True,
        has_groq_key=False,
    )
    assert provider == "deepseek"
    assert reason == "openai_key_missing"


def test_resolve_fallback_provider_disabled_returns_none():
    provider, reason = _resolve_fallback_provider(
        fallback_enabled=False,
        requested_fallback="openai",
        primary_provider="gemini",
        has_openai_key=False,
        has_deepseek_key=False,
        has_gemini_creds=True,
        has_groq_key=False,
    )
    assert provider is None
    assert reason is None


def test_is_fallback_eligible_error_for_tool_choice_mismatch():
    err = Exception(
        "Error code: 400 - {'error': {'message': 'Tool choice is none, but model called a tool', "
        "'type': 'invalid_request_error', 'code': 'tool_use_failed'}}"
    )
    assert _is_fallback_eligible_error(err) is True


def test_resolve_fallback_role_providers_deepseek_prefers_gemini_for_structured_roles():
    providers = _resolve_fallback_role_providers(
        "deepseek",
        has_gemini_creds=True,
        has_openai_key=True,
        has_deepseek_key=True,
        has_groq_key=False,
    )
    assert providers == {
        "router": "gemini",
        "planner": "gemini",
        "responder": "deepseek",
    }


def test_resolve_fallback_role_providers_deepseek_uses_openai_when_gemini_unavailable():
    providers = _resolve_fallback_role_providers(
        "deepseek",
        has_gemini_creds=False,
        has_openai_key=True,
        has_deepseek_key=True,
        has_groq_key=False,
    )
    assert providers == {
        "router": "openai",
        "planner": "openai",
        "responder": "deepseek",
    }


def test_resolve_fallback_role_providers_deepseek_falls_back_to_deepseek_when_only_option():
    providers = _resolve_fallback_role_providers(
        "deepseek",
        has_gemini_creds=False,
        has_openai_key=False,
        has_deepseek_key=True,
        has_groq_key=False,
    )
    assert providers == {
        "router": "deepseek",
        "planner": "deepseek",
        "responder": "deepseek",
    }


def test_resolve_fallback_role_providers_gemini_requires_gemini_credentials():
    providers = _resolve_fallback_role_providers(
        "gemini",
        has_gemini_creds=False,
        has_openai_key=True,
        has_deepseek_key=True,
        has_groq_key=False,
    )
    assert providers is None


def test_resolve_fallback_provider_autoselects_groq_when_openai_missing_and_groq_available():
    provider, reason = _resolve_fallback_provider(
        fallback_enabled=True,
        requested_fallback="openai",
        primary_provider="gemini",
        has_openai_key=False,
        has_deepseek_key=False,
        has_gemini_creds=True,
        has_groq_key=True,
    )
    assert provider == "groq"
    assert reason == "openai_key_missing"


def test_resolve_fallback_role_providers_groq_requires_key():
    providers = _resolve_fallback_role_providers(
        "groq",
        has_gemini_creds=True,
        has_openai_key=True,
        has_deepseek_key=True,
        has_groq_key=False,
    )
    assert providers is None


def test_resolve_fallback_role_providers_groq_when_available():
    providers = _resolve_fallback_role_providers(
        "groq",
        has_gemini_creds=False,
        has_openai_key=False,
        has_deepseek_key=False,
        has_groq_key=True,
    )
    assert providers == {
        "router": "groq",
        "planner": "groq",
        "responder": "groq",
    }


def test_get_preblocked_primary_roles_returns_blocked_roles():
    blocked_model = "test-groq-model-blocked"
    mark_rate_limited("groq", blocked_model, retry_after_s=60)

    handler = object.__new__(LLMHandler)
    handler._primary_role_models = {
        "router": {"provider": "groq", "model": blocked_model},
        "planner": {"provider": "groq", "model": "test-model-open"},
        "responder": {"provider": "groq", "model": "test-model-open-2"},
    }

    blocked = handler._get_preblocked_primary_roles()
    assert len(blocked) == 1
    assert blocked[0]["role"] == "router"
    assert blocked[0]["provider"] == "groq"
    assert blocked[0]["model"] == blocked_model


def test_get_response_api_uses_fallback_immediately_when_primary_preblocked(monkeypatch):
    blocked_model = "test-groq-model-preblocked"
    mark_rate_limited("groq", blocked_model, retry_after_s=60)

    class DummyApp:
        def __init__(self, result=None, exc: Exception | None = None):
            self._result = result
            self._exc = exc
            self.called = 0

        def invoke(self, state):
            self.called += 1
            if self._exc:
                raise self._exc
            return self._result

    handler = object.__new__(LLMHandler)
    handler._progress_callback_default = None
    handler._progress_callback = None
    handler.chat_history = {}
    handler._langsmith_enabled = False
    handler._langsmith_project = None
    handler.max_iterations = 6
    handler._strict_mutation_execution = False
    handler._fallback_label = "router=groq:llama-3.3-70b-versatile"
    handler._primary_role_models = {
        "router": {"provider": "groq", "model": blocked_model},
        "planner": {"provider": "groq", "model": blocked_model},
        "responder": {"provider": "groq", "model": blocked_model},
    }
    handler._fallback_role_models = {
        "router": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "planner": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "responder": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
    }
    handler._build_memory_recall_context = lambda _user_id, _msg: ""
    handler._emit_progress = lambda *_args, **_kwargs: None
    handler.plan_adapter = type("PlanAdapter", (), {"root_dir": "."})()

    fallback_state = {
        "messages": [
            HumanMessage(content="hello"),
            AIMessage(content="fallback-response"),
        ],
        "iteration": 1,
        "final_response": "fallback-response",
        "executed_actions": [],
        "pending_clarification": None,
        "detected_intent": "NO_OP",
        "intent_confidence": "high",
    }
    handler.agent_app = DummyApp(exc=AssertionError("primary app should not be called"))
    fallback_app = DummyApp(result=fallback_state)
    handler._fallback_agent_app = fallback_app

    monkeypatch.setattr("llms.llm_handler.is_flush_enabled", lambda: False)

    result = handler.get_response_api(
        user_message="hello",
        user_id="1",
        user_language="en",
    )

    assert fallback_app.called == 1
    assert result["response_to_user"] == "fallback-response"


def test_is_mutation_intent_accepts_update_delete_prefixes():
    assert LLMHandler._is_mutation_intent("UPDATE_PROMISE") is True
    assert LLMHandler._is_mutation_intent("DELETE_ACTION") is True


def test_is_mutation_intent_accepts_edit_remove_aliases():
    assert LLMHandler._is_mutation_intent("EDIT_PROMISE") is True
    assert LLMHandler._is_mutation_intent("REMOVE_ACTION") is True


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


def test_strip_internal_reasoning_removes_protocol_artifacts_and_keeps_answer():
    raw = (
        "(calling tool)\n\n"
        "<|DSML|function_calls>\n"
        "<|DSML|invoke name=\"web_fetch\">\n"
        "<|DSML|parameter name=\"url\">https://api.example.com</|DSML|parameter>\n"
        "</|DSML|invoke>\n"
        "</|DSML|function_calls>\n"
        "The last two entries are November 1 and October 25.\n"
        "For troubleshooting, visit: https://docs.langchain.com/oss/python/langchain/errors/OUTPUT_PARSING_FAILURE"
    )
    output = LLMHandler._strip_internal_reasoning(raw)
    assert output == "The last two entries are November 1 and October 25."


def test_strip_internal_reasoning_returns_blank_when_only_protocol_artifacts():
    raw = (
        "(calling tool)\n"
        "<|DSML|function_calls>\n"
        "<|DSML|invoke name=\"web_fetch\">\n"
        "</|DSML|invoke>\n"
        "</|DSML|function_calls>\n"
    )
    output = LLMHandler._strip_internal_reasoning(raw)
    assert output == ""


def _build_strict_handler_for_contract() -> LLMHandler:
    # Build a minimal handler instance without running __init__ heavy setup.
    handler = object.__new__(LLMHandler)
    handler._strict_mutation_execution = True
    return handler


def test_mutation_contract_does_not_override_when_intent_unknown_and_no_actions():
    handler = _build_strict_handler_for_contract()
    output = handler._enforce_mutation_execution_contract(
        user_id="u1",
        user_message="what is my p09 promise",
        detected_intent=None,
        executed_actions=[],
        response_text="Your weekly report is completed and up to date.",
        pending_clarification=None,
    )
    assert output == "Your weekly report is completed and up to date."


def test_mutation_contract_does_not_override_read_only_intent_with_success_wording():
    handler = _build_strict_handler_for_contract()
    output = handler._enforce_mutation_execution_contract(
        user_id="u1",
        user_message="what are my tasks next week",
        detected_intent="QUERY_PROGRESS",
        executed_actions=[],
        response_text="You have not logged any time yet this week.",
        pending_clarification=None,
    )
    assert output == "You have not logged any time yet this week."


def test_mutation_contract_still_blocks_mutation_claim_without_successful_execution():
    handler = _build_strict_handler_for_contract()
    output = handler._enforce_mutation_execution_contract(
        user_id="u1",
        user_message="create a promise to run",
        detected_intent="CREATE_PROMISE",
        executed_actions=[],
        response_text="Done, created your new promise.",
        pending_clarification=None,
    )
    assert "please confirm" in output.lower()
    assert "create promise" in output.lower()


def test_mutation_contract_overrides_even_non_success_text_when_mutation_intent_without_success():
    handler = _build_strict_handler_for_contract()
    output = handler._enforce_mutation_execution_contract(
        user_id="u1",
        user_message="create a promise to run",
        detected_intent="CREATE_PROMISE",
        executed_actions=[],
        response_text="Can you clarify the exact target hours?",
        pending_clarification=None,
    )
    assert "please confirm" in output.lower()
    assert "create promise" in output.lower()


def test_mutation_contract_uses_missing_fields_for_safe_clarification():
    handler = _build_strict_handler_for_contract()
    output = handler._enforce_mutation_execution_contract(
        user_id="u1",
        user_message="log action",
        detected_intent="LOG_ACTION",
        executed_actions=[],
        response_text="Sure, done.",
        pending_clarification={"missing_fields": ["promise_id", "time_spent"]},
    )
    assert "please confirm" in output.lower()
    assert "promise_id" in output
    assert "time_spent" in output


def test_mutation_contract_reports_failed_mutation_when_action_attempted_but_unsuccessful():
    handler = _build_strict_handler_for_contract()
    output = handler._enforce_mutation_execution_contract(
        user_id="u1",
        user_message="log 2h on p01",
        detected_intent="LOG_ACTION",
        executed_actions=[{"tool_name": "add_action", "success": False}],
        response_text="Successfully logged 2 hours.",
        pending_clarification=None,
    )
    assert "please confirm" in output.lower()
