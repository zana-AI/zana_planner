import json
import os
import sys

from langchain_core.tools import StructuredTool
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms.agent import create_plan_execute_graph  # noqa: E402


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


def _get_setting(setting_key: str):
    if setting_key == "language":
        return "fr"
    return None


def _count_actions_today():
    return 3


def _make_tools():
    return [
        StructuredTool.from_function(func=_get_setting, name="get_setting", description="Get a user setting."),
        StructuredTool.from_function(
            func=_count_actions_today, name="count_actions_today", description="Count actions today."
        ),
    ]


def test_plan_execute_tool_then_respond_emits_plan_when_enabled():
    tools = _make_tools()
    events = []

    def progress(event, payload):
        events.append(event)

    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Fetch preferred language from settings.",
                "tool_name": "get_setting",
                "tool_args": {"setting_key": "language"},
            },
            {
                "kind": "respond",
                "purpose": "Answer using fetched setting.",
                "response_hint": "Respond with the language value.",
            },
        ]
    }

    planner = FakeModel([AIMessage(content=json.dumps(plan))])

    def responder_fn(messages):
        last_tool = None
        for m in reversed(messages):
            if isinstance(m, ToolMessage):
                last_tool = m.content
                break
        if last_tool == "fr":
            return AIMessage(content="Your preferred language is fr.")
        return AIMessage(content="done")

    responder = FakeModel(responder_fn=responder_fn)

    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=True,
        max_iterations=6,
        progress_getter=lambda: progress,
    )

    result = app.invoke(
        {
            "messages": [HumanMessage(content="what is my preferred language?")],
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

    assert "plan" in events
    assert result.get("final_response") == "Your preferred language is fr."


def test_plan_execute_does_not_emit_plan_when_disabled():
    tools = _make_tools()
    events = []

    def progress(event, payload):
        events.append(event)

    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Count actions today.",
                "tool_name": "count_actions_today",
                "tool_args": {},
            },
            {"kind": "respond", "purpose": "Answer with the count.", "response_hint": "Respond with the count."},
        ]
    }

    planner = FakeModel([AIMessage(content=json.dumps(plan))])

    def responder_fn(messages):
        last_tool = None
        for m in reversed(messages):
            if isinstance(m, ToolMessage):
                last_tool = m.content
                break
        if str(last_tool) == "3":
            return AIMessage(content="You logged 3 actions today.")
        return AIMessage(content="done")

    responder = FakeModel(responder_fn=responder_fn)

    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=6,
        progress_getter=lambda: progress,
    )

    result = app.invoke(
        {
            "messages": [HumanMessage(content="how many actions did I do today?")],
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

    assert "plan" not in events
    assert result.get("final_response") == "You logged 3 actions today."


def test_plan_validation_missing_required_args_converts_to_ask_user_and_sets_pending():
    tools = _make_tools()

    # Missing required arg: get_setting(setting_key)
    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Fetch preferred language from settings.",
                "tool_name": "get_setting",
                "tool_args": {},
            }
        ]
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])
    responder = FakeModel([AIMessage(content="should not be used")])

    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=6,
    )

    result = app.invoke(
        {
            "messages": [HumanMessage(content="what is my preferred language?")],
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

    assert "To do that, I need:" in (result.get("final_response") or "")
    pending = result.get("pending_clarification") or {}
    assert pending.get("tool_name") == "get_setting"
    assert "setting_key" in (pending.get("missing_fields") or [])


def test_plan_validation_infers_datetime_text_for_resolve_datetime():
    def _resolve_datetime(datetime_text: str):
        return f"resolved:{datetime_text}"

    tools = [
        StructuredTool.from_function(
            func=_resolve_datetime,
            name="resolve_datetime",
            description="Resolve natural language datetime.",
        )
    ]

    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Resolve requested period.",
                "tool_name": "resolve_datetime",
                "tool_args": {},
            },
            {"kind": "respond", "purpose": "Answer.", "response_hint": "Answer with resolved period."},
        ]
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])

    def responder_fn(messages):
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                return AIMessage(content=f"Window: {msg.content}")
        return AIMessage(content="No window.")

    responder = FakeModel(responder_fn=responder_fn)

    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=6,
    )

    result = app.invoke(
        {
            "messages": [HumanMessage(content="what are my main tasks next week")],
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

    assert "resolved:what are my main tasks next week" in (result.get("final_response") or "").lower()
    assert result.get("pending_clarification") is None


def test_verify_by_reading_appends_verification_tool_after_mutation():
    calls = []

    def _add_action(promise_id: str, time_spent: float):
        calls.append(("add_action", promise_id, time_spent))
        return "ok"

    def _get_last_action_on_promise(promise_id: str):
        calls.append(("get_last_action_on_promise", promise_id))
        return "verified"

    tools = [
        StructuredTool.from_function(func=_add_action, name="add_action", description="Add an action."),
        StructuredTool.from_function(
            func=_get_last_action_on_promise,
            name="get_last_action_on_promise",
            description="Get last action for a promise.",
        ),
    ]

    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Log an action.",
                "tool_name": "add_action",
                "tool_args": {"promise_id": "P01", "time_spent": 1.0},
            },
            {"kind": "respond", "purpose": "Confirm.", "response_hint": "Confirm success."},
        ],
        "detected_intent": "LOG_ACTION",
        "intent_confidence": "high",
        "safety": {"requires_confirmation": False},
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])

    def responder_fn(messages):
        # After verification, last tool output should be "verified"
        last_tool = None
        for m in reversed(messages):
            if isinstance(m, ToolMessage):
                last_tool = m.content
                break
        if last_tool == "verified":
            return AIMessage(content="Logged and verified.")
        return AIMessage(content="done")

    responder = FakeModel(responder_fn=responder_fn)

    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=6,
    )

    result = app.invoke(
        {
            "messages": [HumanMessage(content="log 1h on P01")],
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

    assert result.get("final_response") == "Logged and verified."
    # Both mutation and verification tool should have been called.
    assert ("add_action", "P01", 1.0) in calls
    assert ("get_last_action_on_promise", "P01") in calls
    tool_msgs = [m for m in result.get("messages", []) if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 2


def test_retry_once_on_transient_tool_failure():
    attempts = {"n": 0}

    def _flaky_tool(x: int):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise TimeoutError("temporary timeout")
        return x + 1

    tools = [StructuredTool.from_function(func=_flaky_tool, name="flaky_tool", description="Sometimes fails.")]

    plan = {
        "steps": [
            {"kind": "tool", "purpose": "Call flaky tool.", "tool_name": "flaky_tool", "tool_args": {"x": 1}},
            {"kind": "respond", "purpose": "Answer.", "response_hint": "Respond with the tool output."},
        ]
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])

    def responder_fn(messages):
        last_tool = None
        for m in reversed(messages):
            if isinstance(m, ToolMessage):
                last_tool = m.content
                break
        if str(last_tool) == "2":
            return AIMessage(content="ok:2")
        return AIMessage(content="done")

    responder = FakeModel(responder_fn=responder_fn)

    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=6,
    )

    result = app.invoke(
        {
            "messages": [HumanMessage(content="run")],
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

    assert result.get("final_response") == "ok:2"
    assert attempts["n"] == 2


def test_loop_detection_blocks_repeated_tool_calls(monkeypatch):
    monkeypatch.setenv("LLM_TOOL_LOOP_DETECTION_ENABLED", "1")
    monkeypatch.setenv("LLM_TOOL_LOOP_WARNING_THRESHOLD", "2")
    monkeypatch.setenv("LLM_TOOL_LOOP_CRITICAL_THRESHOLD", "3")
    monkeypatch.setenv("LLM_TOOL_LOOP_GLOBAL_THRESHOLD", "4")

    def _poll_status():
        return {"status": "pending"}

    tools = [
        StructuredTool.from_function(
            func=_poll_status,
            name="poll_status",
            description="Poll status.",
        )
    ]

    plan = {
        "steps": [
            {"kind": "tool", "purpose": "Poll.", "tool_name": "poll_status", "tool_args": {}},
            {"kind": "tool", "purpose": "Poll again.", "tool_name": "poll_status", "tool_args": {}},
            {"kind": "tool", "purpose": "Poll again.", "tool_name": "poll_status", "tool_args": {}},
            {"kind": "tool", "purpose": "Poll again.", "tool_name": "poll_status", "tool_args": {}},
            {"kind": "respond", "purpose": "Answer.", "response_hint": "Use final tool output."},
        ]
    }

    planner = FakeModel([AIMessage(content=json.dumps(plan))])

    def responder_fn(messages):
        for m in reversed(messages):
            if isinstance(m, ToolMessage):
                return AIMessage(content=str(m.content))
        return AIMessage(content="done")

    responder = FakeModel(responder_fn=responder_fn)

    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=10,
    )

    result = app.invoke(
        {
            "messages": [HumanMessage(content="poll until done")],
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

    tool_outputs = [m.content for m in result.get("messages", []) if isinstance(m, ToolMessage)]
    assert any("loop_detected" in str(content) for content in tool_outputs)


def test_dynamic_replan_asks_user_when_from_search_is_ambiguous():
    def _search_promises(query: str):
        # Multi-match output (non-JSON) like PlannerAPIAdapter.search_promises
        return (
            "Found 2 promise(s) matching 'sport':\n\n"
            "• #P10 **Do sport**\n"
            "  Target: 2.0 h/week | Total logged: 10.0 hours\n"
            "• #P11 **Sport cardio**\n"
            "  Target: 1.0 h/week | Total logged: 3.0 hours"
        )

    calls = []

    def _add_action(promise_id: str, time_spent: float):
        calls.append(("add_action", promise_id, time_spent))
        return "ok"

    tools = [
        StructuredTool.from_function(func=_search_promises, name="search_promises", description="Search promises."),
        StructuredTool.from_function(func=_add_action, name="add_action", description="Add an action."),
    ]

    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Search promises for the user topic.",
                "tool_name": "search_promises",
                "tool_args": {"query": "sport"},
            },
            {
                "kind": "tool",
                "purpose": "Log time on the selected promise.",
                "tool_name": "add_action",
                "tool_args": {"promise_id": "FROM_SEARCH", "time_spent": 1.0},
            },
            {"kind": "respond", "purpose": "Confirm.", "response_hint": "Confirm success."},
        ]
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])
    responder = FakeModel([AIMessage(content="should not be used")])

    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=6,
    )

    result = app.invoke(
        {
            "messages": [HumanMessage(content="I did sport")],
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

    assert "multiple matching promises" in (result.get("final_response") or "").lower()
    pending = result.get("pending_clarification") or {}
    assert pending.get("reason") == "ambiguous_promise_id"
    assert pending.get("tool_name") == "add_action"
    assert pending.get("missing_fields") == ["promise_id"]
    # Tool should not be invoked with unresolved FROM_SEARCH placeholder.
    assert ("add_action", "FROM_SEARCH", 1.0) not in calls


def test_generic_from_tool_placeholder_is_resolved_from_json_tool_output():
    calls = []

    def _make_item():
        return json.dumps({"item_id": "X123", "message": "created"})

    def _use_item(item_id: str):
        calls.append(("use_item", item_id))
        return "ok"

    tools = [
        StructuredTool.from_function(func=_make_item, name="make_item", description="Create an item."),
        StructuredTool.from_function(func=_use_item, name="use_item", description="Use an item."),
    ]

    plan = {
        "steps": [
            {"kind": "tool", "purpose": "Create.", "tool_name": "make_item", "tool_args": {}},
            {
                "kind": "tool",
                "purpose": "Use created.",
                "tool_name": "use_item",
                "tool_args": {"item_id": "FROM_TOOL:make_item:item_id"},
            },
            {"kind": "respond", "purpose": "Confirm.", "response_hint": "Confirm."},
        ]
    }

    planner = FakeModel([AIMessage(content=json.dumps(plan))])

    def responder_fn(messages):
        return AIMessage(content="done")

    responder = FakeModel(responder_fn=responder_fn)

    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=6,
    )

    result = app.invoke(
        {
            "messages": [HumanMessage(content="go")],
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

    assert result.get("final_response") == "done"
    assert ("use_item", "X123") in calls


def test_low_confidence_mutation_asks_confirmation():
    """Test that low-confidence mutation tools trigger a confirmation question."""
    calls = []

    def _add_action(promise_id: str, time_spent: float):
        calls.append(("add_action", promise_id, time_spent))
        return "ok"

    tools = [
        StructuredTool.from_function(func=_add_action, name="add_action", description="Add an action."),
    ]

    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Log time on promise.",
                "tool_name": "add_action",
                "tool_args": {"promise_id": "P01", "time_spent": 2.0},
            },
            {"kind": "respond", "purpose": "Confirm.", "response_hint": "Confirm success."},
        ]
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])
    responder = FakeModel([AIMessage(content="should not be used")])

    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=6,
    )

    result = app.invoke(
        {
            "messages": [HumanMessage(content="maybe log 2h on P01")],
            "iteration": 0,
            "plan": plan["steps"],
            "step_idx": 0,
            "final_response": None,
            "planner_error": None,
            "detected_intent": "LOG_ACTION",
            "intent_confidence": "medium",  # Not high
            "safety": {"requires_confirmation": False},
        }
    )

    # Should ask for confirmation before executing
    assert "confirm" in (result.get("final_response") or "").lower()
    pending = result.get("pending_clarification") or {}
    assert pending.get("reason") == "pre_mutation_confirmation"
    assert pending.get("tool_name") == "add_action"
    # Tool should NOT have been called yet
    assert len(calls) == 0


def test_high_confidence_mutation_proceeds_normally():
    """Test that high-confidence mutation tools proceed without confirmation."""
    calls = []

    def _add_action(promise_id: str, time_spent: float):
        calls.append(("add_action", promise_id, time_spent))
        return "ok"

    tools = [
        StructuredTool.from_function(func=_add_action, name="add_action", description="Add an action."),
    ]

    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Log time on promise.",
                "tool_name": "add_action",
                "tool_args": {"promise_id": "P01", "time_spent": 2.0},
            },
            {"kind": "respond", "purpose": "Confirm.", "response_hint": "Confirm success."},
        ]
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])

    def responder_fn(messages):
        return AIMessage(content="Logged 2 hours on P01.")

    responder = FakeModel(responder_fn=responder_fn)

    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=6,
    )

    result = app.invoke(
        {
            "messages": [HumanMessage(content="log 2h on P01")],
            "iteration": 0,
            "plan": plan["steps"],
            "step_idx": 0,
            "final_response": None,
            "planner_error": None,
            "detected_intent": "LOG_ACTION",
            "intent_confidence": "high",  # High confidence
            "safety": {"requires_confirmation": False},
        }
    )

    # Should proceed without asking for confirmation
    assert "confirm" not in (result.get("final_response") or "").lower()
    # Tool should have been called
    assert ("add_action", "P01", 2.0) in calls
    assert result.get("final_response") == "Logged 2 hours on P01."


def test_safety_requires_confirmation_triggers_ask():
    """Test that safety.requires_confirmation=True triggers confirmation even with high confidence."""
    calls = []

    def _delete_promise(promise_id: str):
        calls.append(("delete_promise", promise_id))
        return "ok"

    tools = [
        StructuredTool.from_function(func=_delete_promise, name="delete_promise", description="Delete a promise."),
    ]

    plan = {
        "steps": [
            {
                "kind": "tool",
                "purpose": "Delete promise.",
                "tool_name": "delete_promise",
                "tool_args": {"promise_id": "P01"},
            },
            {"kind": "respond", "purpose": "Confirm.", "response_hint": "Confirm deletion."},
        ]
    }
    planner = FakeModel([AIMessage(content=json.dumps(plan))])
    responder = FakeModel([AIMessage(content="should not be used")])

    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=6,
    )

    result = app.invoke(
        {
            "messages": [HumanMessage(content="delete P01")],
            "iteration": 0,
            "plan": plan["steps"],
            "step_idx": 0,
            "final_response": None,
            "planner_error": None,
            "detected_intent": "DELETE_PROMISE",
            "intent_confidence": "high",
            "safety": {"requires_confirmation": True},  # Explicitly requires confirmation
        }
    )

    # Should ask for confirmation even with high confidence
    assert "confirm" in (result.get("final_response") or "").lower()
    pending = result.get("pending_clarification") or {}
    assert pending.get("reason") == "pre_mutation_confirmation"
    # Tool should NOT have been called yet
    assert len(calls) == 0
