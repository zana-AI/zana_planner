import os
import sys

from langchain_core.tools import StructuredTool
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.append(TM_BOT_DIR)

from llms.agent import create_agent_graph  # noqa: E402


class FakeModel:
    """Simple stand-in model that returns pre-baked AI messages."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.tools = None

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        if not self._responses:
            raise RuntimeError("No more fake responses available")
        return self._responses.pop(0)


def _echo_tool(text: str) -> str:
    return f"echo:{text}"


def _add_one(x: int) -> int:
    return x + 1


def _make_tools():
    return [
        StructuredTool.from_function(func=_echo_tool, name="echo_tool", description="Echo input text"),
        StructuredTool.from_function(func=_add_one, name="add_one", description="Increment a number"),
    ]


def test_agent_runs_tool_then_answers():
    tools = _make_tools()
    progress_events = []

    def progress(event, payload):
        progress_events.append(event)

    responses = [
        AIMessage(content="", tool_calls=[{"name": "echo_tool", "args": {"text": "hi"}, "id": "call1"}]),
        AIMessage(content="done"),
    ]
    app = create_agent_graph(tools=tools, model=FakeModel(responses), max_iterations=4, progress_getter=lambda: progress)

    result = app.invoke({"messages": [HumanMessage(content="hi")], "iteration": 0})
    messages = result["messages"]

    assert result["iteration"] == 2
    assert isinstance(messages[-1], AIMessage)
    assert messages[-1].content == "done"
    assert any(isinstance(m, ToolMessage) for m in messages)
    assert "agent_step" in progress_events and "tool_step" in progress_events


def test_agent_stops_on_max_iterations_before_tool_execution():
    tools = _make_tools()
    responses = [
        AIMessage(content="", tool_calls=[{"name": "echo_tool", "args": {"text": "hi"}, "id": "call1"}]),
    ]
    app = create_agent_graph(tools=tools, model=FakeModel(responses), max_iterations=1)

    result = app.invoke({"messages": [HumanMessage(content="hi")], "iteration": 0})
    messages = result["messages"]

    assert result["iteration"] == 1  # Only the agent step ran
    assert not any(isinstance(m, ToolMessage) for m in messages)


def test_agent_returns_direct_answer_without_tools():
    tools = _make_tools()
    responses = [AIMessage(content="final answer")]
    app = create_agent_graph(tools=tools, model=FakeModel(responses), max_iterations=3)

    result = app.invoke({"messages": [HumanMessage(content="just answer")], "iteration": 0})
    messages = result["messages"]

    assert result["iteration"] == 1
    assert isinstance(messages[-1], AIMessage)
    assert messages[-1].content == "final answer"
    assert not any(isinstance(m, ToolMessage) for m in messages)
