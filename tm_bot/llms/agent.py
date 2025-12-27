from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional, Sequence, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langgraph.graph import END, StateGraph

# ToolNode import path varies across langgraph versions.
try:
    from langgraph.prebuilt import ToolNode as _ToolNode  # type: ignore
except Exception:  # pragma: no cover
    _ToolNode = None

from llms.planning_schema import Plan, PlanStep


class AgentState(TypedDict):
    """State passed between LangGraph nodes."""

    messages: List[BaseMessage]
    iteration: int
    plan: Optional[List[dict]]
    step_idx: int
    final_response: Optional[str]
    planner_error: Optional[str]
    # Optional metadata used to support stateful clarifications.
    pending_meta_by_idx: Optional[Dict[int, dict]]
    pending_clarification: Optional[dict]
    tool_retry_counts: Optional[Dict[str, int]]


def _run_tool_calls(messages: List[BaseMessage], tools_by_name: Dict[str, object]) -> List[ToolMessage]:
    """
    Minimal ToolNode-compatible executor for langgraph installs lacking `langgraph.prebuilt`.
    Executes tool calls present on the last AIMessage and returns ToolMessage list.
    """
    last_msg = messages[-1] if messages else None
    tool_calls = getattr(last_msg, "tool_calls", None) if isinstance(last_msg, AIMessage) else None
    if not tool_calls:
        return []

    out: List[ToolMessage] = []
    for call in tool_calls:
        call = call or {}
        name = (call.get("name") or "").strip()
        args = call.get("args") or {}
        call_id = call.get("id") or "tool_call"
        tool = tools_by_name.get(name)
        if tool is None:
            payload = {"error": f"Unknown tool: {name}", "error_type": "unknown", "retryable": False}
            out.append(ToolMessage(content=json.dumps(payload), tool_call_id=call_id))
            continue

        try:
            # StructuredTool supports .invoke; fall back to .run if needed.
            if hasattr(tool, "invoke"):
                result = tool.invoke(args)
            elif hasattr(tool, "run"):
                result = tool.run(**args)  # type: ignore
            else:
                result = tool(**args)  # type: ignore

            content = json.dumps(result) if isinstance(result, (dict, list)) else ("" if result is None else str(result))
            out.append(ToolMessage(content=content, tool_call_id=call_id))
        except Exception as e:
            payload = {"error": str(e), "error_type": "unknown", "retryable": False}
            out.append(ToolMessage(content=json.dumps(payload), tool_call_id=call_id))
    return out


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
    tool_node = _ToolNode(tools) if _ToolNode else None
    tools_by_name = {getattr(t, "name", ""): t for t in tools if getattr(t, "name", "")}
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
        if tool_node:
            tool_results = tool_node.invoke({"messages": state["messages"]})
            result_messages = tool_results.get("messages", [])
        else:
            result_messages = _run_tool_calls(state["messages"], tools_by_name)
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
    tool_node = _ToolNode(tools) if _ToolNode else None
    tool_by_name = {getattr(t, "name", ""): t for t in tools if getattr(t, "name", "")}

    def _required_args_for_tool(tool_obj) -> List[str]:
        """
        Best-effort extraction of required args from a StructuredTool schema.
        Supports both Pydantic v1/v2 styles depending on LangChain version.
        """
        try:
            schema = getattr(tool_obj, "args_schema", None)
            if schema is None:
                return []
            # Pydantic v2
            fields = getattr(schema, "model_fields", None)
            if isinstance(fields, dict):
                required = []
                for name, field in fields.items():
                    try:
                        if getattr(field, "is_required", lambda: False)():
                            required.append(name)
                    except Exception:
                        # Fallback: required if default missing
                        if getattr(field, "default", None) is None and getattr(field, "default_factory", None) is None:
                            required.append(name)
                return required
            # Pydantic v1
            v1_fields = getattr(schema, "__fields__", None)
            if isinstance(v1_fields, dict):
                return [n for n, f in v1_fields.items() if getattr(f, "required", False)]
        except Exception:
            return []
        return []

    required_args_by_tool = {name: _required_args_for_tool(t) for name, t in tool_by_name.items()}

    MUTATION_PREFIXES = ("add_", "create_", "update_", "delete_", "log_")

    def _verification_step_for(tool_name: str, tool_args: dict) -> Optional[dict]:
        """
        Heuristic: after a mutation tool, add a lightweight read step to confirm.
        Only returns steps for tools that exist in this app's tool set.
        """
        tool_args = tool_args or {}
        if tool_name == "update_setting":
            setting_key = tool_args.get("setting_key")
            if setting_key and "get_setting" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Verify the updated setting.",
                    "tool_name": "get_setting",
                    "tool_args": {"setting_key": setting_key},
                }
            if "get_settings" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Verify updated settings.",
                    "tool_name": "get_settings",
                    "tool_args": {},
                }
        if "promise" in (tool_name or ""):
            # Prefer listing promises (stable display) unless we have a dedicated get_promise_report.
            pid = tool_args.get("promise_id")
            if pid and "get_promise_report" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Verify promise state after the change.",
                    "tool_name": "get_promise_report",
                    "tool_args": {"promise_id": pid},
                }
            if "get_promises" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Verify the updated promises list.",
                    "tool_name": "get_promises",
                    "tool_args": {},
                }
        if tool_name == "add_action":
            pid = tool_args.get("promise_id")
            if pid and "get_last_action_on_promise" in tool_by_name:
                return {
                    "kind": "tool",
                    "purpose": "Verify the last logged action for the promise.",
                    "tool_name": "get_last_action_on_promise",
                    "tool_args": {"promise_id": pid},
                }
        return None

    # Args that can be inferred or have smart defaults (don't ask user for these)
    INFERABLE_ARGS = {
        "time_spent": 1.0,  # Default to 1 hour when user says "worked on X"
    }
    
    # Args that can be resolved via search (prepend a search step instead of asking)
    SEARCHABLE_ARGS = {"promise_id"}
    
    def _can_infer_missing_args(tool_name: str, missing: List[str], tool_args: dict) -> tuple[bool, dict]:
        """
        Check if missing args can be inferred via defaults or search.
        Returns (can_infer, updated_args_or_prepend_steps).
        """
        updated_args = dict(tool_args)
        still_missing = []
        
        for arg in missing:
            if arg in INFERABLE_ARGS:
                # Apply default value
                updated_args[arg] = INFERABLE_ARGS[arg]
            elif arg in SEARCHABLE_ARGS:
                # This needs a search step prepended - handled separately
                still_missing.append(arg)
            else:
                still_missing.append(arg)
        
        return (len(still_missing) == 0, updated_args, still_missing)
    
    def _create_search_step_for_promise(tool_args: dict) -> Optional[dict]:
        """
        If promise_id is marked as FROM_SEARCH or missing, try to create a search step
        based on any query hints in the args.
        """
        # Check if there's a query hint embedded (planner might put "FROM_SEARCH" as placeholder)
        promise_id = tool_args.get("promise_id", "")
        if promise_id and promise_id != "FROM_SEARCH" and not str(promise_id).startswith("FROM"):
            return None  # Already has a real promise_id
        
        # Look for any text hint that could be used as search query
        # The planner might include a "query" or similar hint
        query = tool_args.get("_search_query") or tool_args.get("query")
        if not query:
            return None
        
        return {
            "kind": "tool",
            "purpose": f"Find promise matching '{query}'",
            "tool_name": "search_promises",
            "tool_args": {"query": query},
        }

    def _validate_and_repair_plan_steps(plan_steps: List[dict]) -> tuple[List[dict], Dict[int, dict]]:
        """
        Validate planner-provided steps and repair common issues:
        - Unknown tool -> ask_user (only as last resort)
        - Missing required args -> try to infer/default first, then ask_user
        - Mutation tool -> auto-add verify-by-reading step (best-effort)
        
        Philosophy: Prefer action over asking. Use smart defaults when possible.
        """
        pending_meta_by_idx: Dict[int, dict] = {}
        repaired: List[dict] = []

        for i, raw in enumerate(plan_steps or []):
            step = dict(raw or {})
            kind = step.get("kind")

            if kind == "tool":
                tool_name = (step.get("tool_name") or "").strip()
                tool_args = step.get("tool_args") or {}

                if not tool_name or tool_name not in tool_by_name:
                    pending_meta_by_idx[i] = {
                        "reason": "unknown_tool",
                        "tool_name": tool_name,
                        "provided_args": tool_args,
                    }
                    repaired.append(
                        {
                            "kind": "ask_user",
                            "purpose": "Clarify the requested action (unknown tool).",
                            "question": "I'm not sure which action you want me to take. Can you rephrase what you want to do?",
                        }
                    )
                    continue

                required_args = required_args_by_tool.get(tool_name, [])
                missing = [
                    a
                    for a in required_args
                    if a not in tool_args or tool_args.get(a) in (None, "", [], "FROM_SEARCH")
                ]
                
                if missing:
                    # Try to infer missing args using defaults
                    can_infer, updated_args, still_missing = _can_infer_missing_args(
                        tool_name, missing, tool_args
                    )
                    
                    if can_infer:
                        # All missing args were inferred - update step and continue
                        step["tool_args"] = updated_args
                        repaired.append(step)
                        
                        # Auto verify-by-reading after mutations
                        if tool_name.startswith(MUTATION_PREFIXES):
                            verify = _verification_step_for(tool_name, updated_args)
                            if verify:
                                repaired.append(verify)
                        continue
                    
                    # Check if the only missing arg is promise_id and can be searched
                    if still_missing == ["promise_id"] and "search_promises" in tool_by_name:
                        # Check if there's context that suggests what to search for
                        search_step = _create_search_step_for_promise(tool_args)
                        if search_step:
                            # Prepend search step - the executor will handle chaining
                            repaired.append(search_step)
                            # Update the tool step with inferred args and keep it
                            step["tool_args"] = updated_args
                            step["tool_args"]["promise_id"] = "FROM_SEARCH"  # Placeholder
                            repaired.append(step)
                            continue
                    
                    # Still have unresolvable missing args - must ask user
                    # But be more helpful in the question
                    pending_meta_by_idx[i] = {
                        "reason": "missing_required_args",
                        "tool_name": tool_name,
                        "missing_fields": still_missing,
                        "partial_args": updated_args,
                    }
                    
                    # Create a friendlier question
                    if still_missing == ["promise_id"]:
                        question = (
                            "Which promise/goal should I use for this? "
                            "You can say the name (like 'sport' or 'reading') or the ID (like 'P01')."
                        )
                    elif still_missing == ["time_spent"]:
                        question = "How much time did you spend? (e.g., '2 hours' or '30 minutes')"
                    elif "promise_id" in still_missing and "time_spent" in still_missing:
                        question = (
                            "I need a bit more info:\n"
                            "• Which promise/goal? (name or ID like 'P01')\n"
                            "• How much time did you spend?"
                        )
                    else:
                        fields = ", ".join(still_missing)
                        question = f"I need: {fields}. Can you provide these?"
                    
                    repaired.append(
                        {
                            "kind": "ask_user",
                            "purpose": f"Get missing info for {tool_name}.",
                            "question": question,
                        }
                    )
                    continue

                # Keep tool step (all args present)
                repaired.append(step)

                # Auto verify-by-reading after mutations (best-effort, capped later)
                if tool_name.startswith(MUTATION_PREFIXES):
                    verify = _verification_step_for(tool_name, tool_args)
                    if verify:
                        repaired.append(verify)

            elif kind in ("respond", "ask_user"):
                repaired.append(step)
            else:
                # Unknown step kind: respond directly
                repaired.append(
                    {
                        "kind": "respond",
                        "purpose": "Respond directly (unknown plan step kind).",
                        "response_hint": "Respond concisely and ask one clarifying question if needed.",
                    }
                )

        # Ensure a respond step exists if the plan doesn't already ask the user.
        if repaired and not any((s.get("kind") == "ask_user") for s in repaired):
            if repaired[-1].get("kind") != "respond":
                repaired.append(
                    {
                        "kind": "respond",
                        "purpose": "Respond to the user after completing tool steps.",
                        "response_hint": "Summarize results briefly and encouragingly. Use emojis for status (✅ done, 🔥 streak).",
                    }
                )

        # Cap to 6 steps to avoid runaway plans.
        if len(repaired) > 6:
            repaired = repaired[:6]

        return repaired, pending_meta_by_idx

    def _last_tool_error(messages: List[BaseMessage]) -> Optional[dict]:
        """
        If the last ToolMessage looks like an error payload, return it as a dict.
        Expected shapes:
        - {"error": "...", "error_type": "...", "retryable": bool, ...}
        """
        try:
            for m in reversed(messages or []):
                if not isinstance(m, ToolMessage):
                    continue
                content = getattr(m, "content", None)
                if not content:
                    continue
                parsed = None
                if isinstance(content, str):
                    try:
                        parsed = json.loads(content)
                    except Exception:
                        parsed = None
                if isinstance(parsed, dict) and parsed.get("error"):
                    return parsed
        except Exception:
            return None
        return None

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
        plan_dicts, pending_meta_by_idx = _validate_and_repair_plan_steps(plan_dicts)

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
            "pending_meta_by_idx": pending_meta_by_idx,
            "pending_clarification": None,
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
            tool_err = _last_tool_error(state["messages"])
            if tool_err:
                hint = (
                    "A tool call failed. Respond with a user-safe, action-oriented message:\n"
                    "1) What I tried (one short sentence)\n"
                    "2) What failed (plain language; no internal traces)\n"
                    "3) Next step (one concrete action): ask for missing info, suggest retry, or provide an alternative\n"
                    "If retryable is true, suggest the user try again.\n"
                    "Keep it friendly and helpful - don't make the user feel bad about the error."
                )
                result = responder_model.invoke(state["messages"] + [SystemMessage(content=hint)])
            else:
                # Default responder hint for good UX
                default_hint = (
                    "RESPONSE GUIDELINES:\n"
                    "- Be friendly, encouraging, and concise (2-4 sentences max)\n"
                    "- Summarize what was done using natural language\n"
                    "- Use emojis sparingly: ✅ for success, 🔥 for streaks, 📊 for reports\n"
                    "- If showing progress, highlight achievements and encourage continued effort\n"
                    "- End with a subtle prompt for next action if relevant (e.g., 'Keep up the great work!')\n"
                    "- Format lists with bullet points (•) for readability\n"
                    "- Do NOT include raw tool outputs or JSON - summarize in human terms"
                )
                result = responder_model.invoke(state["messages"] + [SystemMessage(content=default_hint)])
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
            pending = (state.get("pending_meta_by_idx") or {}).get(idx)
            return {
                **state,
                "iteration": new_iteration,
                "final_response": step.question or "Could you clarify what you mean?",
                "pending_clarification": pending,
                "step_idx": idx + 1,
            }

        if step.kind == "respond":
            # Add a lightweight instruction message (no tools).
            base_hint = step.response_hint or "Respond to the user based on tool results above."
            
            # Build comprehensive response guidelines
            ux_guidelines = (
                "\n\nRESPONSE STYLE:\n"
                "- Be friendly and encouraging (you're Zana, a helpful assistant)\n"
                "- Keep it concise: 2-4 sentences for simple actions, up to 6 for reports\n"
                "- Use natural language, not technical jargon\n"
                "- Emojis: ✅ success, 🔥 streaks, 📊 reports, 💪 encouragement (use sparingly)\n"
                "- Format lists with bullet points (•) for readability\n"
                "- Highlight achievements and progress positively\n"
                "- Do NOT output raw JSON or tool responses - summarize them\n"
                "- Do NOT call any tools in your response"
            )
            
            hint = base_hint + ux_guidelines
            
            tool_err = _last_tool_error(state["messages"])
            if tool_err:
                err_type = tool_err.get("error_type", "unknown")
                retryable = bool(tool_err.get("retryable"))
                failure_hint = (
                    "\n\nNOTE: A tool call failed. Handle gracefully:\n"
                    "1) Briefly explain what you tried\n"
                    "2) What went wrong (no technical details)\n"
                    "3) Suggest a next step\n"
                    f"Context: error_type={err_type}, retryable={retryable}.\n"
                    "Be reassuring - errors happen!"
                )
                hint = hint + failure_hint
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

        def _is_transient_error(err: Exception) -> bool:
            # Best-effort: treat common network/timeouts as transient.
            transient_types = (TimeoutError, ConnectionError)
            if isinstance(err, transient_types):
                return True
            # Some libs raise OSError/socket-related errors for transient failures.
            if isinstance(err, OSError):
                return True
            return False

        retry_counts = dict(state.get("tool_retry_counts") or {})
        attempts = retry_counts.get(call_id or "", 0)

        # If ToolNode isn't available (older langgraph), run the last tool call manually
        # so we can support retry-once semantics.
        if not tool_node and last_tool_calls and isinstance(last_tool_calls, list) and last_tool_calls:
            call = last_tool_calls[-1] or {}
            tool_name = (call.get("name") or "").strip()
            tool_args = call.get("args") or {}
            tool_call_id = call.get("id") or "tool_call"
            tool_obj = tool_by_name.get(tool_name)
            try:
                if tool_obj is None:
                    raise ValueError(f"Unknown tool: {tool_name}")
                if hasattr(tool_obj, "invoke"):
                    result = tool_obj.invoke(tool_args)
                elif hasattr(tool_obj, "run"):
                    result = tool_obj.run(**tool_args)  # type: ignore
                else:
                    result = tool_obj(**tool_args)  # type: ignore
            except Exception as e:
                if tool_call_id and attempts < 1 and _is_transient_error(e):
                    retry_counts[tool_call_id] = attempts + 1
                    _emit(
                        progress_getter,
                        "tool_retry",
                        {"iteration": state.get("iteration", 0), "tool_call_id": tool_call_id, "attempt": attempts + 1},
                    )
                    try:
                        if tool_obj is None:
                            raise ValueError(f"Unknown tool: {tool_name}")
                        if hasattr(tool_obj, "invoke"):
                            result = tool_obj.invoke(tool_args)
                        elif hasattr(tool_obj, "run"):
                            result = tool_obj.run(**tool_args)  # type: ignore
                        else:
                            result = tool_obj(**tool_args)  # type: ignore
                    except Exception as e2:
                        err_payload = {
                            "error": str(e2),
                            "error_type": "transient" if _is_transient_error(e2) else "unknown",
                            "retryable": False,
                            "retried": True,
                        }
                        result_messages = [ToolMessage(content=json.dumps(err_payload), tool_call_id=tool_call_id)]
                    else:
                        content = json.dumps(result) if isinstance(result, (dict, list)) else ("" if result is None else str(result))
                        result_messages = [ToolMessage(content=content, tool_call_id=tool_call_id)]
                else:
                    err_payload = {
                        "error": str(e),
                        "error_type": "transient" if _is_transient_error(e) else "unknown",
                        "retryable": _is_transient_error(e) and attempts < 1,
                        "retried": False,
                    }
                    result_messages = [ToolMessage(content=json.dumps(err_payload), tool_call_id=tool_call_id)]
            else:
                content = json.dumps(result) if isinstance(result, (dict, list)) else ("" if result is None else str(result))
                result_messages = [ToolMessage(content=content, tool_call_id=tool_call_id)]

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

            return {
                **state,
                "messages": state["messages"] + result_messages,
                "step_idx": int(state.get("step_idx", 0) or 0) + 1,
                "tool_retry_counts": retry_counts,
            }

        try:
            if tool_node:
                tool_results = tool_node.invoke({"messages": state["messages"]})
                result_messages = tool_results.get("messages", [])
            else:
                result_messages = _run_tool_calls(state["messages"], tool_by_name)
        except Exception as e:
            # Retry once for transient failures.
            if call_id and attempts < 1 and _is_transient_error(e):
                retry_counts[call_id] = attempts + 1
                _emit(
                    progress_getter,
                    "tool_retry",
                    {"iteration": state.get("iteration", 0), "tool_call_id": call_id, "attempt": attempts + 1},
                )
                try:
                    if tool_node:
                        tool_results = tool_node.invoke({"messages": state["messages"]})
                        result_messages = tool_results.get("messages", [])
                    else:
                        result_messages = _run_tool_calls(state["messages"], tool_by_name)
                except Exception as e2:
                    err_payload = {
                        "error": str(e2),
                        "error_type": "transient" if _is_transient_error(e2) else "unknown",
                        "retryable": False,
                        "retried": True,
                    }
                    result_messages = [
                        ToolMessage(content=json.dumps(err_payload), tool_call_id=call_id or "tool_error")
                    ]
            else:
                # Preserve loop stability: convert tool error into ToolMessage.
                err_payload = {
                    "error": str(e),
                    "error_type": "transient" if _is_transient_error(e) else "unknown",
                    "retryable": _is_transient_error(e) and attempts < 1,
                    "retried": False,
                }
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
            "tool_retry_counts": retry_counts,
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
