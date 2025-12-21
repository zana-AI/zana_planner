from __future__ import annotations

from typing import Callable, List, Optional, Sequence, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.runnables import Runnable
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode


class AgentState(TypedDict):
    """State passed between LangGraph nodes."""

    messages: List[BaseMessage]
    iteration: int


def _emit(
    progress_getter: Optional[Callable[[], Optional[Callable[[str, dict], None]]]],
    event: str,
    payload: dict,
) -> None:
    """Call the current progress callback (if any) in a UI-agnostic way."""
    if not progress_getter:
        return

    cb = progress_getter()
    if cb:
        try:
            cb(event, payload)
        except Exception:
            # Progress is best-effort; never break the agent loop.
            pass


def create_agent_graph(
    tools: Sequence,
    model: Runnable,
    max_iterations: int = 6,
    progress_getter: Optional[Callable[[], Optional[Callable[[str, dict], None]]]] = None,
):
    """
    Build a LangGraph app that can iterate between the LLM and tools.

    Args:
        tools: LangChain tools to expose.
        model: Chat model (will be bound to tools before invocation).
        max_iterations: Hard cap to prevent runaway loops.
        progress_getter: Optional callable returning a per-invoke progress callback.

    Returns:
        A compiled LangGraph app.
    """
    tool_node = ToolNode(tools)
    model_with_tools = model.bind_tools(tools)

    graph = StateGraph(AgentState)

    def call_agent(state: AgentState) -> AgentState:
        result = model_with_tools.invoke(state["messages"])
        new_iteration = state["iteration"] + 1
        _emit(
            progress_getter,
            "agent_step",
            {"iteration": new_iteration, "content": getattr(result, "content", None)},
        )
        return {"messages": state["messages"] + [result], "iteration": new_iteration}

    def call_tools(state: AgentState) -> AgentState:
        tool_results = tool_node.invoke({"messages": state["messages"]})
        result_messages = tool_results.get("messages", [])
        _emit(
            progress_getter,
            "tool_step",
            {
                "iteration": state["iteration"],
                "tool_results": [
                    getattr(m, "content", None) for m in result_messages if isinstance(m, ToolMessage)
                ],
            },
        )
        return {"messages": state["messages"] + result_messages, "iteration": state["iteration"]}

    def should_continue(state: AgentState):
        if state["iteration"] >= max_iterations:
            return END

        last_msg = state["messages"][-1] if state["messages"] else None
        has_tool_calls = isinstance(last_msg, AIMessage) and getattr(last_msg, "tool_calls", None)
        return "tools" if has_tool_calls else END

    graph.add_node("agent", call_agent)
    graph.add_node("tools", call_tools)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()
