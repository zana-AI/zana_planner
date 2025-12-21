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

