"""
Integration tests: natural language → (mock) planner → real tools → real DB → assert DB.

Tier 1: Mock planner returns a fixed plan; real tools from PlannerAPIAdapter; real PostgreSQL.
No API keys; marked @pytest.mark.integration and @pytest.mark.requires_postgres.
"""

import json
import os
import sys

import pytest
from langchain_core.tools import StructuredTool
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

# Ensure tm_bot is on path (conftest does this for tests/; integration may run separately)
TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.insert(0, TM_BOT_DIR)

from llms.agent import create_plan_execute_graph
from llms.tool_wrappers import _current_user_id, _wrap_tool
from services.planner_api_adapter import PlannerAPIAdapter

from tests.test_config import ensure_users_exist, unique_user_id

pytestmark = [pytest.mark.integration, pytest.mark.requires_postgres]

EXCLUDED_TOOLS = {"query_database", "get_db_schema"}


def build_tools_from_adapter(adapter: PlannerAPIAdapter):
    """Build LangChain StructuredTools from PlannerAPIAdapter (same logic as LLMHandler._build_tools)."""
    tools = []
    for attr_name in dir(adapter):
        if attr_name.startswith("_"):
            continue
        if attr_name in EXCLUDED_TOOLS:
            continue
        candidate = getattr(adapter, attr_name)
        if not callable(candidate):
            continue
        doc = (candidate.__doc__ or "").strip() or f"Planner action {attr_name}"
        first_line = doc.splitlines()[0].strip() if doc else ""
        if len(first_line) > 120:
            first_line = first_line[:120] + "..."
        sanitized_desc = first_line or f"Planner action {attr_name}"
        try:
            tool = StructuredTool.from_function(
                func=_wrap_tool(candidate, attr_name, debug_enabled=False),
                name=attr_name,
                description=sanitized_desc,
            )
            tools.append(tool)
        except Exception:
            pass
    return tools


class FakeModel:
    """Returns pre-baked AI messages (e.g. fixed plan JSON)."""

    def __init__(self, responses=None, responder_fn=None):
        self._responses = list(responses or [])
        self._responder_fn = responder_fn

    def invoke(self, messages):
        if self._responder_fn is not None:
            return self._responder_fn(messages)
        if not self._responses:
            raise RuntimeError("No more fake responses available")
        return self._responses.pop(0)


# --- Tier 1: create promise (plan → confirmation; then we run tool and assert DB) ---


@pytest.mark.integration
@pytest.mark.requires_postgres
def test_create_promise_plan_then_tool_assert_db(tmp_path):
    """
    Natural language 'Create a promise called Reading' → mock plan with add_promise →
    graph returns pending_clarification (add_promise always confirms); run adapter.add_promise
    with pending args → assert DB has one promise with text Reading.
    """
    user_id = unique_user_id()
    ensure_users_exist(user_id)
    adapter = PlannerAPIAdapter(str(tmp_path))
    tools = build_tools_from_adapter(adapter)

    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Create a promise called Reading.",
                "tool_name": "add_promise",
                "tool_args": {
                    "promise_text": "Reading",
                    "num_hours_promised_per_week": 2.0,
                    "recurring": True,
                },
            },
            {"kind": "respond", "purpose": "Confirm.", "response_hint": "Confirm success."},
        ],
        "detected_intent": "CREATE_PROMISE",
        "intent_confidence": "high",
        "safety": {"requires_confirmation": False},
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])

    def responder_fn(messages):
        for m in reversed(messages):
            if isinstance(m, ToolMessage):
                return AIMessage(content="Promise added.")
        return AIMessage(content="Done.")

    responder = FakeModel(responder_fn=responder_fn)
    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=6,
    )

    token = _current_user_id.set(str(user_id))
    try:
        result = app.invoke(
            {
                "messages": [HumanMessage(content="Create a promise called Reading")],
                "iteration": 0,
                "plan": None,
                "step_idx": 0,
                "final_response": None,
                "planner_error": None,
                "detected_intent": None,
                "intent_confidence": None,
                "safety": None,
            }
        )
    finally:
        _current_user_id.reset(token)

    # add_promise is in ALWAYS_CONFIRM_TOOLS so we expect pending_clarification
    pending = result.get("pending_clarification") or {}
    assert pending.get("reason") == "pre_mutation_confirmation"
    assert pending.get("tool_name") == "add_promise"
    tool_args = pending.get("tool_args") or {}
    assert tool_args.get("promise_text") == "Reading"

    # Run the tool with same args (same path the graph would use after user confirms)
    adapter.add_promise(user_id, **tool_args)

    promises = adapter.get_promises(user_id)
    assert len(promises) == 1
    # Adapter normalizes: spaces -> underscores
    assert promises[0]["text"] == "Reading"


# --- Tier 1: log action (high intent → no confirmation → graph runs tool → assert DB) ---


@pytest.mark.integration
@pytest.mark.requires_postgres
def test_log_action_via_plan_and_graph_assert_db(tmp_path):
    """
    Create promise P01 in test; natural language 'Log 2 hours on P01' → mock plan add_action
    with intent_confidence high → graph runs tool → assert DB has action with 2.0h on P01.
    """
    user_id = unique_user_id()
    ensure_users_exist(user_id)
    adapter = PlannerAPIAdapter(str(tmp_path))
    # Create P01 so add_action can run
    adapter.add_promise(user_id, promise_text="Reading", num_hours_promised_per_week=2.0)
    promises = adapter.get_promises(user_id)
    assert len(promises) == 1
    promise_id = promises[0]["id"]

    tools = build_tools_from_adapter(adapter)
    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Log 2 hours on P01.",
                "tool_name": "add_action",
                "tool_args": {"promise_id": promise_id, "time_spent": 2.0},
            },
            {"kind": "respond", "purpose": "Confirm.", "response_hint": "Confirm logged."},
        ],
        "detected_intent": "LOG_ACTION",
        "intent_confidence": "high",
        "safety": {"requires_confirmation": False},
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])

    def responder_fn(messages):
        for m in reversed(messages):
            if isinstance(m, ToolMessage):
                return AIMessage(content="Logged 2 hours.")
        return AIMessage(content="Done.")

    responder = FakeModel(responder_fn=responder_fn)
    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=6,
    )

    token = _current_user_id.set(str(user_id))
    try:
        result = app.invoke(
            {
                "messages": [HumanMessage(content="Log 2 hours on P01")],
                "iteration": 0,
                "plan": None,
                "step_idx": 0,
                "final_response": None,
                "planner_error": None,
                "detected_intent": None,
                "intent_confidence": None,
                "safety": None,
            }
        )
    finally:
        _current_user_id.reset(token)

    assert result.get("final_response")
    actions = adapter.get_actions(user_id)
    assert actions
    # get_actions returns list of [date, time, promise_id, time_spent]
    matching = [a for a in actions if a[2] == promise_id and a[3] == 2.0]
    assert len(matching) == 1


# --- Tier 1 (optional): delete promise → assert gone ---


@pytest.mark.integration
@pytest.mark.requires_postgres
def test_delete_promise_via_plan_and_graph_assert_db(tmp_path):
    """
    Create promise P01; plan with delete_promise P01 and high intent → graph runs tool →
    assert promise P01 is no longer in list_promises.
    """
    user_id = unique_user_id()
    ensure_users_exist(user_id)
    adapter = PlannerAPIAdapter(str(tmp_path))
    adapter.add_promise(user_id, promise_text="ToDelete", num_hours_promised_per_week=0.0)
    promises = adapter.get_promises(user_id)
    assert len(promises) == 1
    promise_id = promises[0]["id"]

    tools = build_tools_from_adapter(adapter)
    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Delete promise.",
                "tool_name": "delete_promise",
                "tool_args": {"promise_id": promise_id},
            },
            {"kind": "respond", "purpose": "Confirm.", "response_hint": "Confirm deleted."},
        ],
        "detected_intent": "DELETE_PROMISE",
        "intent_confidence": "high",
        "safety": {"requires_confirmation": False},
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])

    def responder_fn(messages):
        for m in reversed(messages):
            if isinstance(m, ToolMessage):
                return AIMessage(content="Deleted.")
        return AIMessage(content="Done.")

    responder = FakeModel(responder_fn=responder_fn)
    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=6,
    )

    token = _current_user_id.set(str(user_id))
    try:
        result = app.invoke(
            {
                "messages": [HumanMessage(content="Delete promise " + promise_id)],
                "iteration": 0,
                "plan": None,
                "step_idx": 0,
                "final_response": None,
                "planner_error": None,
                "detected_intent": None,
                "intent_confidence": None,
                "safety": None,
            }
        )
    finally:
        _current_user_id.reset(token)

    assert result.get("final_response")
    promises_after = adapter.get_promises(user_id)
    ids_after = [p["id"] for p in promises_after]
    assert promise_id not in ids_after
