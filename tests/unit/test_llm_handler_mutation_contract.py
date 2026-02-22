import os
import sys

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms.llm_handler import LLMHandler  # noqa: E402


def _make_handler(strict: bool = True) -> LLMHandler:
    handler = LLMHandler.__new__(LLMHandler)
    handler._strict_mutation_execution = strict
    return handler


def test_contract_blocks_success_when_no_mutation_executed():
    handler = _make_handler(strict=True)
    response = handler._enforce_mutation_execution_contract(
        user_id="42",
        user_message="add a promise to drink water",
        detected_intent="CREATE_PROMISE",
        executed_actions=[],
        response_text="Done! I added your promise.",
    )
    assert "could not confirm any change" in response.lower()


def test_contract_blocks_success_when_mutation_failed():
    handler = _make_handler(strict=True)
    response = handler._enforce_mutation_execution_contract(
        user_id="42",
        user_message="delete promise P01",
        detected_intent="DELETE_PROMISE",
        executed_actions=[
            {
                "tool_name": "delete_promise",
                "args": {"promise_id": "P01"},
                "success": False,
            }
        ],
        response_text="Done! I deleted it.",
    )
    assert "did not complete successfully" in response.lower()


def test_contract_allows_success_when_mutation_succeeded():
    handler = _make_handler(strict=True)
    original = "Done! I added your promise."
    response = handler._enforce_mutation_execution_contract(
        user_id="42",
        user_message="add a promise to drink water",
        detected_intent="CREATE_PROMISE",
        executed_actions=[
            {
                "tool_name": "add_promise",
                "args": {"promise_text": "drink water"},
                "success": True,
            }
        ],
        response_text=original,
    )
    assert response == original


def test_contract_disabled_keeps_original_response():
    handler = _make_handler(strict=False)
    original = "Done! I added your promise."
    response = handler._enforce_mutation_execution_contract(
        user_id="42",
        user_message="add a promise",
        detected_intent="CREATE_PROMISE",
        executed_actions=[],
        response_text=original,
    )
    assert response == original


def test_contract_preserves_clarification_response_when_pending():
    handler = _make_handler(strict=True)
    clarification = "To do that, I need: num_hours_promised_per_week. Can you provide this?"
    response = handler._enforce_mutation_execution_contract(
        user_id="42",
        user_message="add a promise to drink water",
        detected_intent="CREATE_PROMISE",
        executed_actions=[],
        response_text=clarification,
        pending_clarification={"reason": "missing_required_args"},
    )
    assert response == clarification
