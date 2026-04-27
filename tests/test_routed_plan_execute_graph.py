import json
import os
import sys

from langchain_core.tools import StructuredTool
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms.agent import create_routed_plan_execute_graph  # noqa: E402


class FakeModel:
    """Simple stand-in model that returns pre-baked AI messages."""

    def __init__(self, responses=None, responder_fn=None):
        self._responses = list(responses or [])
        self._responder_fn = responder_fn
        self.invocations = []

    def invoke(self, messages):
        self.invocations.append(messages)
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


def _latest_tool_result_summary(messages) -> str:
    for msg in reversed(messages or []):
        if isinstance(msg, SystemMessage) and "Executed tool results for this turn" in str(msg.content):
            return str(msg.content)
    return ""


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
        summary = _latest_tool_result_summary(messages)
        if "count_promises" in summary and "-> 3" in summary:
            return AIMessage(content="You currently have 3 promises.")
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


def test_routed_operator_add_promise_missing_args_infers_from_user_text():
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
                    {"mode": "operator", "confidence": "high", "reason": "transactional_intent"}
                )
            )
        ]
    )

    # Missing both required args: promise_text + num_hours_promised_per_week
    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Create a promise.",
                "tool_name": "add_promise",
                "tool_args": {},
            },
            {"kind": "respond", "purpose": "Confirm.", "response_hint": "Confirm success."},
        ],
        "detected_intent": "CREATE_PROMISE",
        "intent_confidence": "high",
        "safety": {"requires_confirmation": False},
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])

    def responder_fn(messages):
        return AIMessage(content="Done")

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
        max_iterations=6,
    )

    result = app.invoke(_initial_state("add a promise to drink water 10 minutes a day"))
    final_response = (result.get("final_response") or "").lower()

    # add_promise requires confirmation in operator mode; ensure inference happened before that gate.
    assert "shall i go ahead" in final_response
    pending = result.get("pending_clarification") or {}
    assert pending.get("reason") == "pre_mutation_confirmation"
    assert pending.get("tool_name") == "add_promise"
    tool_args = pending.get("tool_args") or {}
    assert tool_args.get("promise_text") == "drink water"
    assert abs(float(tool_args.get("num_hours_promised_per_week")) - 1.1667) < 0.01
    assert calls == []


def test_routed_strategist_infers_datetime_text_for_resolve_datetime():
    def _resolve_datetime(datetime_text: str):
        return f"resolved:{datetime_text}"

    tools = [
        StructuredTool.from_function(
            func=_resolve_datetime,
            name="resolve_datetime",
            description="Resolve natural language datetime.",
        ),
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
                "purpose": "Resolve requested period.",
                "tool_name": "resolve_datetime",
                "tool_args": {},
            },
            {"kind": "respond", "purpose": "Answer.", "response_hint": "Answer with resolved period."},
        ],
        "detected_intent": "QUERY_PROGRESS",
        "intent_confidence": "high",
        "safety": {"requires_confirmation": False},
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])

    def responder_fn(messages):
        summary = _latest_tool_result_summary(messages)
        if "resolve_datetime" in summary:
            return AIMessage(content=f"Window: {summary}")
        return AIMessage(content="No window.")

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
        max_iterations=6,
    )

    result = app.invoke(_initial_state("what are my main tasks next week"))

    assert "resolved:what are my main tasks next week" in (result.get("final_response") or "").lower()
    assert result.get("pending_clarification") is None


def test_routed_responder_receives_no_tool_protocol_or_tool_docs():
    def _count_promises():
        return 3

    tools = [
        StructuredTool.from_function(func=_count_promises, name="count_promises", description="Count user promises."),
    ]
    router = FakeModel(
        [
            AIMessage(
                content=json.dumps(
                    {"mode": "operator", "confidence": "high", "reason": "query_intent"}
                )
            )
        ]
    )
    plan = {
        "steps": [
            {"kind": "tool", "purpose": "Count promises.", "tool_name": "count_promises", "tool_args": {}},
            {"kind": "respond", "purpose": "Answer.", "response_hint": "Answer with the count."},
        ],
        "detected_intent": "QUERY_PROGRESS",
        "intent_confidence": "high",
        "safety": {"requires_confirmation": False},
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])
    responder = FakeModel([AIMessage(content="You have 3 promises.")])

    app = create_routed_plan_execute_graph(
        tools=tools,
        router_model=router,
        planner_model=planner,
        responder_model=responder,
        router_prompt="Output route JSON.",
        get_planner_prompt_for_mode=lambda _mode: "Output plan JSON.",
        get_system_message_for_mode=lambda *_args: SystemMessage(
            content="=== AVAILABLE TOOLS ===\n- count_promises()\n\n=== LANGUAGE MANAGEMENT ===\nReply in English."
        ),
        get_response_system_message_for_mode=lambda *_args: SystemMessage(
            content="=== LANGUAGE MANAGEMENT ===\nReply in English."
        ),
        emit_plan=False,
        max_iterations=6,
    )

    result = app.invoke(_initial_state("how many promises do I have"))

    responder_messages = responder.invocations[-1]
    combined = "\n".join(str(getattr(m, "content", "") or "") for m in responder_messages)
    assert result.get("final_response") == "You have 3 promises."
    assert "AVAILABLE TOOLS" not in combined
    assert "count_promises()" not in combined
    assert "Executed tool results for this turn" in combined
    assert not any(isinstance(m, ToolMessage) for m in responder_messages)
    assert not any(isinstance(m, AIMessage) and getattr(m, "tool_calls", None) for m in responder_messages)


def test_routed_engagement_responder_is_not_bound_to_tools():
    def _memory_write(text: str):
        return f"saved:{text}"

    tools = [
        StructuredTool.from_function(func=_memory_write, name="memory_write", description="Save a memory."),
    ]
    router = FakeModel(
        [
            AIMessage(
                content=json.dumps(
                    {"mode": "engagement", "confidence": "high", "reason": "casual_chat"}
                )
            )
        ]
    )
    planner = FakeModel(
        [
            AIMessage(
                content=json.dumps(
                    {
                        "steps": [],
                        "final_response_if_no_tools": "planner fallback",
                        "detected_intent": "NO_OP",
                        "intent_confidence": "high",
                        "safety": {"requires_confirmation": False},
                    }
                )
            )
        ]
    )
    responder = FakeModel([AIMessage(content="Nice to hear from you.")])

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

    result = app.invoke(_initial_state("my cat is called Rex"))

    assert result.get("final_response") == "Nice to hear from you."
    combined = "\n".join(str(getattr(m, "content", "") or "") for m in responder.invocations[-1])
    assert "Do not call or imitate tools" in combined
    assert "memory_write" not in combined
