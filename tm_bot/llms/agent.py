from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional, Sequence, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from llms.planning_schema import Plan, PlanStep


class AgentState(TypedDict):
    """State passed between LangGraph nodes."""

    messages: List[BaseMessage]
    iteration: int
    plan: Optional[List[dict]]
    step_idx: int
    final_response: Optional[str]
    planner_error: Optional[str]


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


def create_plan_execute_graph(
    tools: Sequence,
    planner_model: Runnable,
    responder_model: Runnable,
    planner_prompt: str,
    emit_plan: bool = False,
    max_iterations: int = 6,
    progress_getter: Optional[Callable[[], Optional[Callable[[str, dict], None]]]] = None,
):
    """
    Build a LangGraph app that runs a planner phase first, then executes steps.

    - Planner: produces a structured Plan JSON (no tool calls).
    - Executor: runs one step at a time (tool calls via ToolNode), then responds.
    """
    tool_node = ToolNode(tools)

    graph = StateGraph(AgentState)

    def _parse_plan(text: str) -> Plan:
        # Be forgiving: allow fenced JSON or extra text.
        cleaned = (text or "").strip()
        if "```" in cleaned:
            # take first fenced block
            parts = cleaned.split("```")
            if len(parts) >= 2:
                cleaned = parts[1].strip()
                # strip possible language tag line
                if "\n" in cleaned and cleaned.split("\n", 1)[0].lower() in {"json"}:
                    cleaned = cleaned.split("\n", 1)[1].strip()
        return Plan.model_validate_json(cleaned)

    def planner(state: AgentState) -> AgentState:
        messages = list(state.get("messages") or [])
        messages = [SystemMessage(content=planner_prompt)] + messages

        result = planner_model.invoke(messages)
        content = getattr(result, "content", "") or ""

        plan: Optional[Plan] = None
        planner_error: Optional[str] = None
        try:
            plan = _parse_plan(content)
        except Exception as e:
            planner_error = str(e)
            # fallback: always respond
            plan = Plan(
                steps=[
                    PlanStep(
                        kind="respond",
                        purpose="Answer the user directly (planner parsing failed).",
                        response_hint="Be concise and ask one clarifying question if needed.",
                    )
                ]
            )

        plan_dicts = [s.model_dump() for s in plan.steps]

        if emit_plan:
            _emit(
                progress_getter,
                "plan",
                {
                    "steps": [
                        {
                            "kind": s.get("kind"),
                            "purpose": s.get("purpose"),
                            "tool_name": s.get("tool_name"),
                            "tool_args_keys": sorted(list((s.get("tool_args") or {}).keys())),
                        }
                        for s in plan_dicts
                    ],
                    "planner_error": planner_error,
                },
            )

        return {
            "messages": state["messages"],
            "iteration": state.get("iteration", 0),
            "plan": plan_dicts,
            "step_idx": 0,
            "final_response": plan.final_response_if_no_tools,
            "planner_error": planner_error,
        }

    def executor(state: AgentState) -> AgentState:
        # If planner already provided final response and there are no steps, finish.
        if state.get("final_response") and not (state.get("plan") or []):
            return state

        plan = state.get("plan") or []
        idx = int(state.get("step_idx", 0) or 0)

        # If we already have a final response, finish.
        if state.get("final_response"):
            return state

        # If no more steps, use responder model to craft an answer from messages.
        if idx >= len(plan):
            result = responder_model.invoke(state["messages"])
            return {
                **state,
                "messages": state["messages"] + [result],
                "final_response": getattr(result, "content", None),
            }

        step = PlanStep.model_validate(plan[idx])
        new_iteration = int(state.get("iteration", 0) or 0) + 1

        if new_iteration > max_iterations:
            # hard stop: respond with best effort
            result = responder_model.invoke(state["messages"])
            return {
                **state,
                "messages": state["messages"] + [result],
                "iteration": new_iteration,
                "final_response": getattr(result, "content", None),
            }

        if step.kind == "ask_user":
            return {
                **state,
                "iteration": new_iteration,
                "final_response": step.question or "Could you clarify what you mean?",
                "step_idx": idx + 1,
            }

        if step.kind == "respond":
            # Add a lightweight instruction message (no tools).
            hint = step.response_hint or "Respond to the user based on tool results above. Do not call tools."
            result = responder_model.invoke(state["messages"] + [SystemMessage(content=hint)])
            return {
                **state,
                "messages": state["messages"] + [result],
                "iteration": new_iteration,
                "final_response": getattr(result, "content", None),
                "step_idx": idx + 1,
            }

        if step.kind == "tool":
            tool_name = step.tool_name or ""
            tool_args = step.tool_args or {}
            call_id = f"plan_{idx}_iter_{new_iteration}"
            tool_call = {"name": tool_name, "args": tool_args, "id": call_id, "type": "tool_call"}

            # IMPORTANT:
            # Vertex/Gemini requires each "content" item to include at least one "parts" entry.
            # Some LangChain serializers will drop tool_calls when the model isn't bound to tools,
            # and an empty assistant message (content="") can become a request with missing parts,
            # yielding: "400 Unable to submit request ... must include at least one parts field".
            #
            # We keep a minimal, non-empty content to ensure request validity.
            ai = AIMessage(content="(calling tool)", tool_calls=[tool_call])
            _emit(
                progress_getter,
                "executor_step",
                {"iteration": new_iteration, "step_idx": idx, "kind": "tool", "tool": tool_name},
            )
            return {
                **state,
                "messages": state["messages"] + [ai],
                "iteration": new_iteration,
            }

        # Unknown step kind: skip
        return {**state, "iteration": new_iteration, "step_idx": idx + 1}

    def tools_node(state: AgentState) -> AgentState:
        # Execute the last tool call (ToolNode supports multiple tool calls too).
        last_msg = state["messages"][-1] if state.get("messages") else None
        last_tool_calls = getattr(last_msg, "tool_calls", None) if last_msg else None
        call_id = None
        if last_tool_calls and isinstance(last_tool_calls, list):
            call_id = last_tool_calls[-1].get("id")

        try:
            tool_results = tool_node.invoke({"messages": state["messages"]})
            result_messages = tool_results.get("messages", [])
        except Exception as e:
            # Preserve loop stability: convert tool error into ToolMessage.
            err_payload = {"error": str(e)}
            result_messages = [
                ToolMessage(content=json.dumps(err_payload), tool_call_id=call_id or "tool_error")
            ]

        _emit(
            progress_getter,
            "tool_step",
            {
                "iteration": state.get("iteration", 0),
                "tool_results": [
                    getattr(m, "content", None) for m in result_messages if isinstance(m, ToolMessage)
                ],
            },
        )

        # After a tool step, advance plan index.
        return {
            **state,
            "messages": state["messages"] + result_messages,
            "step_idx": int(state.get("step_idx", 0) or 0) + 1,
        }

    def should_continue(state: AgentState):
        if state.get("final_response"):
            return END
        if int(state.get("iteration", 0) or 0) >= max_iterations:
            return END
        last_msg = state["messages"][-1] if state.get("messages") else None
        has_tool_calls = isinstance(last_msg, AIMessage) and getattr(last_msg, "tool_calls", None)
        return "tools" if has_tool_calls else "executor"

    graph.add_node("planner", planner)
    graph.add_node("executor", executor)
    graph.add_node("tools", tools_node)
    graph.set_entry_point("planner")
    graph.add_edge("planner", "executor")
    graph.add_conditional_edges("executor", should_continue, {"tools": "tools", "executor": "executor", END: END})
    graph.add_edge("tools", "executor")

    return graph.compile()
