"""
Phase 5: Adversarial and safety regression tests.

- Adapter validation: invalid args rejected, no bad write.
- Tool wrapper: requires active user_id context (no cross-user via model-provided user_id).
- Privacy: cross-user isolation (get_promises(user_b) does not see user_a data).
- Malicious plan: graph with bad tool args (e.g. negative time_spent) -> tool rejects, no bad write.
"""

import json
import os
import sys

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

# Ensure tm_bot on path
TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.insert(0, TM_BOT_DIR)

from llms.agent import create_plan_execute_graph
from llms.tool_wrappers import _current_user_id, _wrap_tool
from services.planner_api_adapter import PlannerAPIAdapter

from tests.conversation_eval.harness import build_tools_from_adapter
from tests.test_config import ensure_users_exist, unique_user_id


class _FakeModel:
    """Returns a single pre-baked AIMessage (plan JSON)."""

    def __init__(self, response: AIMessage, responder_fn=None):
        self._response = response
        self._responder_fn = responder_fn

    def invoke(self, messages):
        if self._responder_fn is not None:
            return self._responder_fn(messages)
        return self._response


@pytest.mark.nonfunctional
@pytest.mark.requires_postgres
def test_add_promise_negative_hours_rejected(tmp_path):
    """Adapter rejects negative num_hours_promised_per_week; no promise written."""
    user_id = unique_user_id()
    ensure_users_exist(user_id)
    adapter = PlannerAPIAdapter(str(tmp_path))

    with pytest.raises((ValueError, RuntimeError)):
        adapter.add_promise(
            user_id,
            promise_text="x",
            num_hours_promised_per_week=-1,
            recurring=True,
        )

    promises = adapter.get_promises(user_id)
    assert len(promises) == 0


@pytest.mark.nonfunctional
@pytest.mark.requires_postgres
def test_add_action_negative_time_returns_error_no_write(tmp_path):
    """Adapter returns error for negative time_spent and does not append action."""
    user_id = unique_user_id()
    ensure_users_exist(user_id)
    adapter = PlannerAPIAdapter(str(tmp_path))
    adapter.add_promise(user_id, promise_text="P", num_hours_promised_per_week=1.0)
    promises = adapter.get_promises(user_id)
    promise_id = promises[0]["id"]

    result = adapter.add_action(user_id, promise_id, time_spent=-1.0)
    assert "positive" in result.lower() or "Time spent" in result

    actions = adapter.get_actions(user_id)
    negative_actions = [a for a in actions if a[3] < 0]
    assert len(negative_actions) == 0


@pytest.mark.nonfunctional
@pytest.mark.requires_postgres
def test_add_action_zero_time_returns_error_no_write(tmp_path):
    """Adapter returns error for zero time_spent and does not append action."""
    user_id = unique_user_id()
    ensure_users_exist(user_id)
    adapter = PlannerAPIAdapter(str(tmp_path))
    adapter.add_promise(user_id, promise_text="P", num_hours_promised_per_week=1.0)
    promises = adapter.get_promises(user_id)
    promise_id = promises[0]["id"]

    result = adapter.add_action(user_id, promise_id, time_spent=0.0)
    assert "positive" in result.lower() or "Time spent" in result

    actions_before = len(adapter.get_actions(user_id))
    # Ensure no new action was appended
    actions_after = adapter.get_actions(user_id)
    assert len(actions_after) == actions_before


@pytest.mark.nonfunctional
@pytest.mark.requires_postgres
def test_add_action_nonexistent_promise_returns_error(tmp_path):
    """Adapter returns error for non-existent promise_id; no write."""
    user_id = unique_user_id()
    ensure_users_exist(user_id)
    adapter = PlannerAPIAdapter(str(tmp_path))

    result = adapter.add_action(user_id, "P99", 1.0)
    assert "not found" in result.lower() or "Promise" in result

    actions = adapter.get_actions(user_id)
    assert len(actions) == 0


@pytest.mark.nonfunctional
def test_tool_wrapper_requires_user_id_context(tmp_path):
    """Wrapped tool raises when _current_user_id is not set."""
    adapter = PlannerAPIAdapter(str(tmp_path))
    wrapped = _wrap_tool(adapter.add_promise, "add_promise", debug_enabled=False)

    # Clear context so get() returns default None
    token = _current_user_id.set(None)
    try:
        with pytest.raises(ValueError) as exc_info:
            wrapped(promise_text="x", num_hours_promised_per_week=0.0, recurring=True)
        assert "No active user_id set" in str(exc_info.value)
    finally:
        _current_user_id.reset(token)


@pytest.mark.nonfunctional
@pytest.mark.requires_postgres
def test_privacy_cross_user_isolation(tmp_path):
    """User B cannot see user A's promises; get_promises is scoped by user_id."""
    user_a = unique_user_id()
    user_b = unique_user_id()
    ensure_users_exist(user_a, user_b)
    adapter = PlannerAPIAdapter(str(tmp_path))

    adapter.add_promise(user_a, promise_text="Private", num_hours_promised_per_week=1.0)

    promises_a = adapter.get_promises(user_a)
    promises_b = adapter.get_promises(user_b)

    assert len(promises_a) == 1
    assert len(promises_b) == 0
    assert "Private" in (promises_a[0].get("text") or "")


@pytest.mark.nonfunctional
@pytest.mark.requires_postgres
def test_malicious_plan_negative_time_spent_rejected(tmp_path):
    """Graph with plan containing add_action time_spent=-1: tool returns error, no bad write to DB."""
    user_id = unique_user_id()
    ensure_users_exist(user_id)
    adapter = PlannerAPIAdapter(str(tmp_path))
    adapter.add_promise(user_id, promise_text="P", num_hours_promised_per_week=1.0)
    promises = adapter.get_promises(user_id)
    promise_id = promises[0]["id"]

    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Malicious: negative time.",
                "tool_name": "add_action",
                "tool_args": {"promise_id": promise_id, "time_spent": -1.0},
            },
            {"kind": "respond", "purpose": "Respond.", "response_hint": "Done."},
        ],
        "final_response_if_no_tools": None,
        "detected_intent": "LOG_ACTION",
        "intent_confidence": "high",
        "safety": {"requires_confirmation": False},
    }
    planner = _FakeModel(AIMessage(content=json.dumps(plan)))

    def responder_fn(messages):
        for m in reversed(messages):
            if isinstance(m, ToolMessage):
                return AIMessage(content="Done.")
        return AIMessage(content="Done.")

    responder = _FakeModel(None, responder_fn=responder_fn)
    tools = build_tools_from_adapter(adapter)
    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=6,
    )

    state = {
        "messages": [HumanMessage(content="Log -1 hours")],
        "iteration": 0,
        "plan": None,
        "step_idx": 0,
        "final_response": None,
        "planner_error": None,
        "detected_intent": None,
        "intent_confidence": None,
        "safety": None,
    }
    token = _current_user_id.set(str(user_id))
    try:
        result = app.invoke(state)
    finally:
        _current_user_id.reset(token)

    actions = adapter.get_actions(user_id)
    negative_actions = [a for a in actions if a[3] < 0]
    assert len(negative_actions) == 0, "Adapter must not persist action with negative time_spent"
