import json
import os
import sys

from langchain.tools import StructuredTool
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
        }
    )

    assert "To do that, I need:" in (result.get("final_response") or "")
    pending = result.get("pending_clarification") or {}
    assert pending.get("tool_name") == "get_setting"
    assert "setting_key" in (pending.get("missing_fields") or [])


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
        ]
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
        }
    )

    assert result.get("final_response") == "ok:2"
    assert attempts["n"] == 2




