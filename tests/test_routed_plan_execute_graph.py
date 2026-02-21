import json
import os
import sys

from langchain_core.tools import StructuredTool
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms.agent import create_routed_plan_execute_graph  # noqa: E402


class FakeModel:
    """Simple stand-in model that returns pre-baked AI messages."""

    def __init__(self, responses=None, responder_fn=None):
        self._responses = list(responses or [])
        self._responder_fn = responder_fn

    def invoke(self, messages):
        if self._responder_fn is not None:
            return self._responder_fn(messages)
        if not self._responses:
            raise RuntimeError("No more fake responses available")
        return self._responses.pop(0)


def _initial_state(user_text: str) -> dict:
    return {
        "messages": [HumanMessage(content=user_text)],
        "iteration": 0,
        "plan": None,
        "step_idx": 0,
        "final_response": None,
        "planner_error": None,
        "pending_meta_by_idx": None,
        "pending_clarification": None,
        "tool_retry_counts": {},
        "tool_call_history": [],
        "tool_loop_warning_buckets": {},
        "detected_intent": None,
        "intent_confidence": None,
        "safety": None,
        "mode": None,
        "route_confidence": None,
        "route_reason": None,
        "executed_actions": [],
    }


def test_routed_strategist_query_misplan_recovers_to_read_only_count():
    calls = []

    def _add_promise(promise_text: str, num_hours_promised_per_week: float):
        calls.append(("add_promise", promise_text, num_hours_promised_per_week))
        return "created"

    def _count_promises():
        calls.append(("count_promises",))
        return 3

    tools = [
        StructuredTool.from_function(func=_add_promise, name="add_promise", description="Create a promise."),
        StructuredTool.from_function(func=_count_promises, name="count_promises", description="Count user promises."),
    ]

    router = FakeModel(
        [
            AIMessage(
                content=json.dumps(
                    {"mode": "strategist", "confidence": "high", "reason": "coaching_intent"}
                )
            )
        ]
    )

    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Create a promise.",
                "tool_name": "add_promise",
                "tool_args": {"promise_text": "new promise", "num_hours_promised_per_week": 1.0},
            },
            {
                "kind": "respond",
                "purpose": "Confirm creation.",
                "response_hint": "Confirm promise creation.",
            },
        ],
        "detected_intent": "QUESTION",
        "intent_confidence": "high",
        "safety": {"requires_confirmation": False},
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])

    def responder_fn(messages):
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                return AIMessage(content=f"You currently have {msg.content} promises.")
        return AIMessage(content="No data.")

    responder = FakeModel(responder_fn=responder_fn)

    app = create_routed_plan_execute_graph(
        tools=tools,
        router_model=router,
        planner_model=planner,
        responder_model=responder,
        router_prompt="Output route JSON.",
        get_planner_prompt_for_mode=lambda _mode: "Output plan JSON.",
        get_system_message_for_mode=None,
        emit_plan=False,
        max_iterations=8,
    )

    result = app.invoke(_initial_state("how many promises do I have"))
    final_response = (result.get("final_response") or "").lower()

    assert "3" in final_response
    assert "switch to operator mode" not in final_response
    assert ("count_promises",) in calls
    assert not any(call[0] == "add_promise" for call in calls)


def test_routed_strategist_explicit_mutation_still_blocks():
    calls = []

    def _add_promise(promise_text: str, num_hours_promised_per_week: float):
        calls.append(("add_promise", promise_text, num_hours_promised_per_week))
        return "created"

    tools = [
        StructuredTool.from_function(func=_add_promise, name="add_promise", description="Create a promise."),
    ]

    router = FakeModel(
        [
            AIMessage(
                content=json.dumps(
                    {"mode": "strategist", "confidence": "high", "reason": "coaching_intent"}
                )
            )
        ]
    )

    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Create a promise.",
                "tool_name": "add_promise",
                "tool_args": {"promise_text": "exercise daily", "num_hours_promised_per_week": 2.0},
            },
            {
                "kind": "respond",
                "purpose": "Confirm creation.",
                "response_hint": "Confirm promise creation.",
            },
        ],
        "detected_intent": "CREATE_PROMISE",
        "intent_confidence": "high",
        "safety": {"requires_confirmation": False},
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])
    responder = FakeModel([AIMessage(content="should not be used")])

    app = create_routed_plan_execute_graph(
        tools=tools,
        router_model=router,
        planner_model=planner,
        responder_model=responder,
        router_prompt="Output route JSON.",
        get_planner_prompt_for_mode=lambda _mode: "Output plan JSON.",
        get_system_message_for_mode=None,
        emit_plan=False,
        max_iterations=6,
    )

    result = app.invoke(_initial_state("create a promise to exercise daily"))
    final_response = (result.get("final_response") or "").lower()

    assert "switch to operator mode" in final_response
    assert len(calls) == 0

