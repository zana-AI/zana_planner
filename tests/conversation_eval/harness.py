"""
Conversation eval harness: load transcripts, run Tier 1 (graph + mock planner), evaluate rubric.

Tier 1: mock planner, real tools + DB — validates plan-execute logic.
Tier 2: real router + planner LLMs — validates routing, datetime resolution, clarification flow.
         Requires GROQ_API_KEY (or another provider key) in the environment.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

# Ensure tm_bot on path
TM_BOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tm_bot"))
if TM_BOT_DIR not in sys.path:
    sys.path.insert(0, TM_BOT_DIR)

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from llms.agent import create_plan_execute_graph, create_routed_plan_execute_graph
from llms.tool_wrappers import _current_user_id, _wrap_tool
from services.planner_api_adapter import PlannerAPIAdapter
from langchain_core.tools import StructuredTool

EXCLUDED_TOOLS = {"query_database", "get_db_schema"}


def build_tools_from_adapter(adapter: PlannerAPIAdapter) -> list:
    """Build LangChain StructuredTools from PlannerAPIAdapter (same as test_llm_action_db)."""
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
    """Turn-aware: returns one pre-baked plan per invoke (list of AIMessage)."""

    def __init__(self, plan_responses: List[AIMessage], responder_fn: Optional[Callable] = None):
        self._plan_responses = list(plan_responses)
        self._responder_fn = responder_fn

    def invoke(self, messages):
        if self._responder_fn is not None:
            return self._responder_fn(messages)
        if not self._plan_responses:
            raise RuntimeError("No more fake plan responses available")
        return self._plan_responses.pop(0)


@dataclass
class EvalResult:
    passed: bool
    per_turn_responses: List[str] = field(default_factory=list)
    db_final: Dict[str, Any] = field(default_factory=dict)
    rubric_scores: Dict[str, bool] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


def load_transcript(path: str | Path) -> Dict[str, Any]:
    """Load a transcript YAML file and return parsed dict."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _run_setup(adapter: PlannerAPIAdapter, user_id: int, setup: List[Dict[str, Any]]) -> None:
    """Run setup steps (e.g. add_promise) before turns."""
    for step in setup or []:
        for method_name, kwargs in step.items():
            if not kwargs:
                kwargs = {}
            fn = getattr(adapter, method_name, None)
            if callable(fn):
                fn(user_id, **kwargs)


def run_tier1(
    transcript: Dict[str, Any],
    adapter: PlannerAPIAdapter,
    user_id: int,
) -> EvalResult:
    """
    Run Tier 1 eval: graph with mock planner, real tools and DB.
    Transcript keys: name, turns, rubric, optional setup.
    """
    errors: List[str] = []
    per_turn_responses: List[str] = []
    turns = transcript.get("turns") or []
    rubric = transcript.get("rubric") or {}
    setup = transcript.get("setup") or []

    # Setup (e.g. create promise P01 for log_action scenario)
    try:
        _run_setup(adapter, user_id, setup)
    except Exception as e:
        errors.append(f"Setup failed: {e}")
        return EvalResult(passed=False, per_turn_responses=[], db_final={}, rubric_scores={}, errors=errors)

    # Build plan responses for planner: one per turn that has a plan
    plan_dicts: List[Dict] = []
    for t in turns:
        p = t.get("plan")
        if p is not None and isinstance(p, dict):
            plan_dicts.append(p)

    planner_responses = [AIMessage(content=json.dumps(p)) for p in plan_dicts]
    planner = FakeModel(planner_responses)

    def responder_fn(messages):
        for m in reversed(messages):
            if isinstance(m, ToolMessage):
                return AIMessage(content="Done.")
        return AIMessage(content="Done.")

    responder = FakeModel([], responder_fn=responder_fn)
    tools = build_tools_from_adapter(adapter)
    app = create_plan_execute_graph(
        tools=tools,
        planner_model=planner,
        responder_model=responder,
        planner_prompt="Return JSON only.",
        emit_plan=False,
        max_iterations=6,
    )

    state: Dict[str, Any] = {
        "messages": [],
        "iteration": 0,
        "plan": None,
        "step_idx": 0,
        "final_response": None,
        "planner_error": None,
        "detected_intent": None,
        "intent_confidence": None,
        "safety": None,
    }

    token = _current_user_id.set(str(user_id))
    try:
        plan_index = 0
        for i, turn in enumerate(turns):
            user_msg = turn.get("user") or ""
            state["messages"] = list(state.get("messages") or []) + [HumanMessage(content=user_msg)]

            # If this turn has a plan, clear state.plan so planner runs (FakeModel returns next plan)
            turn_plan = turn.get("plan")
            if turn_plan is not None and isinstance(turn_plan, dict):
                state["plan"] = None
            # else: keep existing plan (e.g. continue from previous)

            try:
                result = app.invoke(state)
            except Exception as e:
                errors.append(f"Turn {i + 1} invoke failed: {e}")
                break

            # Update state from result
            state = dict(result)
            final_response = state.get("final_response") or ""
            per_turn_responses.append(final_response)

            pending = state.get("pending_clarification") or {}
            expect_pending = turn.get("expect_pending_clarification") is True
            execute_pending = turn.get("execute_pending", True)  # default True for backward compatibility

            if pending and expect_pending and execute_pending:
                # Simulate "user said yes": run the pending tool
                tool_name = pending.get("tool_name")
                tool_args = pending.get("tool_args") or {}
                try:
                    fn = getattr(adapter, tool_name, None)
                    if callable(fn):
                        fn(user_id, **tool_args)
                except Exception as e:
                    errors.append(f"Execute pending {tool_name} failed: {e}")
            # When execute_pending is False, we simulate user decline (e.g. cancel); do not run the tool.

            # state already has messages updated by the graph (incl. assistant response)
    finally:
        _current_user_id.reset(token)

    # DB state after all turns
    db_final: Dict[str, Any] = {}
    try:
        promises = adapter.get_promises(user_id)
        actions = adapter.get_actions(user_id)
        db_final["promises"] = promises
        db_final["actions"] = actions
    except Exception as e:
        errors.append(f"DB read failed: {e}")

    # Rubric evaluation
    rubric_scores = evaluate_rubric(transcript, db_final, per_turn_responses, errors)
    passed = len(errors) == 0 and all(rubric_scores.get(k, True) for k in ("intent", "correctness", "db_checks"))

    return EvalResult(
        passed=passed,
        per_turn_responses=per_turn_responses,
        db_final=db_final,
        rubric_scores=rubric_scores,
        errors=errors,
    )


def evaluate_rubric(
    transcript: Dict[str, Any],
    db_final: Dict[str, Any],
    per_turn_responses: List[str],
    errors: List[str],
) -> Dict[str, bool]:
    """
    Evaluate rubric dimensions. Returns dict of dimension -> passed (bool).
    """
    rubric = transcript.get("rubric") or {}
    db_spec = rubric.get("db_final") or {}
    scores: Dict[str, bool] = {}

    # Intent: pass if no explicit check or we have no errors (plan was used)
    scores["intent"] = rubric.get("intent", True) if isinstance(rubric.get("intent"), bool) else True

    # Correctness: no tool/run errors
    scores["correctness"] = len(errors) == 0

    # db_checks: assert db_final constraints
    db_checks = True
    promises = db_final.get("promises") or []
    actions = db_final.get("actions") or []

    if "promises_count" in db_spec:
        expected = int(db_spec["promises_count"])
        db_checks = db_checks and len(promises) == expected
    if "promise_text_contains" in db_spec:
        sub = str(db_spec["promise_text_contains"]).lower()
        db_checks = db_checks and any(sub in (p.get("text") or "").lower() for p in promises)
    if "action_on_promise" in db_spec:
        spec = db_spec["action_on_promise"]
        pid = spec.get("promise_id")
        time_spent = spec.get("time_spent")
        matching = [a for a in actions if (pid is None or a[2] == pid) and (time_spent is None or a[3] == time_spent)]
        db_checks = db_checks and len(matching) >= 1
    if "promise_deleted_id" in db_spec:
        deleted_id = str(db_spec["promise_deleted_id"])
        ids_now = [p["id"] for p in promises]
        db_checks = db_checks and deleted_id not in ids_now

    scores["db_checks"] = db_checks
    scores["tone"] = True  # Stub: always pass
    scores["follow_up"] = True  # Stub: always pass
    return scores


# ---------------------------------------------------------------------------
# Tier 2 — real router + planner LLMs
# ---------------------------------------------------------------------------

# Router prompt (mirrors LLMHandler.system_message_router_prompt).
_ROUTER_PROMPT = (
    "=== ROLE ===\n"
    "You are a ROUTER for a task management assistant.\n"
    "Your job: classify the user's message into one of four agent modes.\n\n"
    "=== MODES ===\n"
    "- **operator**: Transactional actions (create/update/delete promises, log actions, change settings). "
    "Examples: 'I want to call a friend tomorrow', 'log 2 hours on reading', 'delete my gym promise'.\n"
    "- **strategist**: High-level goals, coaching, advice, progress analysis, strategic planning. "
    "Examples: 'what should I focus on this week?', 'am I on track with my goals?'\n"
    "- **social**: Community features (followers, following, feed, public promises).\n"
    "- **engagement**: Casual chat, humor, thanks, greetings, sharing personal facts.\n\n"
    "=== ROUTING RULES ===\n"
    "- If the user wants to DO something (create, log, delete, update, remind) → operator\n"
    "- If the user wants ADVICE, COACHING, or ANALYSIS → strategist\n"
    "- 'social' is Xaana's INTERNAL COMMUNITY ONLY (followers, feed, public promises).\n"
    "- If the user is just CHATTING → engagement\n"
    "- When in doubt between operator and strategist, prefer operator for concrete actions.\n"
    "- Set needs_live_data=true ONLY for breaking news, live prices, fact-checking specific recent claims.\n"
    "- Set needs_live_data=false for coaching, casual chat, or anything from the user's own data.\n\n"
    "=== OUTPUT ===\n"
    "Output ONLY valid JSON:\n"
    '{"mode": "operator"|"strategist"|"social"|"engagement", '
    '"confidence": "high"|"medium"|"low", '
    '"reason": "short label", '
    '"needs_live_data": true|false}\n'
)

_PLANNER_PROMPT_BASE = (
    "=== ROLE ===\n"
    "You are the PLANNER for a task management assistant.\n"
    "Produce a short plan as JSON the executor can follow.\n\n"

    "=== DATETIME RESOLUTION (MANDATORY) ===\n"
    "ANY time a tool requires a datetime/time argument, you MUST:\n"
    "1. Add a resolve_datetime step FIRST with the time expression from the user.\n"
    '2. In the subsequent tool step, use "FROM_TOOL:resolve_datetime:" as the value '
    "for the datetime/time argument (e.g., remind_at, planned_start, due_date).\n"
    "The executor will substitute FROM_TOOL:resolve_datetime: with the resolved ISO 8601 time.\n"
    "Never pass the raw time string directly to remind_at or planned_start — always resolve first.\n\n"

    "=== TOOL SELECTION GUIDE ===\n"
    "- User wants a NOTIFICATION at a time → create_reminder(text, remind_at)\n"
    "- User wants to PLAN a work session for a promise → schedule_session(promise_id, planned_start)\n"
    "- User wants to LOG completed work → log_completed_activity(promise_id, time_spent)\n"
    "- User wants to CREATE a new ongoing promise → add_promise(promise_text, num_hours_promised_per_week)\n"
    "- User wants to see/analyse their promises → get_promises() then respond\n\n"

    "=== OUTPUT FORMAT ===\n"
    "Return ONLY valid JSON:\n"
    "{\n"
    '  "steps": [\n'
    '    {"kind": "tool", "purpose": "...", "tool_name": "resolve_datetime", '
    '     "tool_args": {"datetime_text": "<phrase from user>"}},\n'
    '    {"kind": "tool", "purpose": "...", "tool_name": "create_reminder", '
    '     "tool_args": {"text": "...", "remind_at": "FROM_TOOL:resolve_datetime:"}},\n'
    '    {"kind": "respond", "purpose": "...", "response_hint": "..."}\n'
    "  ],\n"
    '  "detected_intent": "...",\n'
    '  "intent_confidence": "high"|"medium"|"low",\n'
    '  "safety": {"requires_confirmation": false}\n'
    "}\n"
)


def _build_tier2_models():
    """Build real router/planner/responder models from env vars. Returns (router, planner, responder)."""
    from dotenv import load_dotenv
    load_dotenv()

    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if groq_key:
        from langchain_openai import ChatOpenAI
        base_url = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        model_name = "llama-3.3-70b-versatile"
        router = ChatOpenAI(openai_api_key=groq_key, base_url=base_url, model=model_name, temperature=0.0)
        planner = ChatOpenAI(openai_api_key=groq_key, base_url=base_url, model=model_name, temperature=0.2)
        responder = ChatOpenAI(openai_api_key=groq_key, base_url=base_url, model=model_name, temperature=0.3)
        return router, planner, responder

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        from langchain_openai import ChatOpenAI
        model_name = "gpt-4o-mini"
        router = ChatOpenAI(openai_api_key=openai_key, model=model_name, temperature=0.0)
        planner = ChatOpenAI(openai_api_key=openai_key, model=model_name, temperature=0.2)
        responder = ChatOpenAI(openai_api_key=openai_key, model=model_name, temperature=0.3)
        return router, planner, responder

    raise RuntimeError(
        "Tier-2 tests require GROQ_API_KEY or OPENAI_API_KEY in environment. "
        "Add them to .env or export before running."
    )


def _wrap_tracking(tool: Any, called_log: List[str]) -> Any:
    """Return a copy of tool whose func records its name in called_log on each invocation."""
    original_fn = tool.func if hasattr(tool, "func") else None
    if original_fn is None:
        return tool

    tool_name = getattr(tool, "name", "unknown")

    def _tracked(*args, **kwargs):
        called_log.append(tool_name)
        return original_fn(*args, **kwargs)

    return StructuredTool.from_function(
        func=_tracked,
        name=tool_name,
        description=getattr(tool, "description", ""),
        args_schema=getattr(tool, "args_schema", None),
    )


def _get_planner_prompt_for_mode(mode: str) -> str:
    if mode == "operator":
        directive = (
            "=== MODE: OPERATOR ===\n"
            "Handle transactional actions. You can use all tools including mutations "
            "(add_promise, create_reminder, schedule_session, log_completed_activity, etc.).\n\n"
        )
    elif mode == "strategist":
        directive = (
            "=== MODE: STRATEGIST ===\n"
            "Focus on coaching and analysis. AVOID mutation tools. "
            "Use read-only tools (get_promises, get_weekly_report, get_profile_status).\n\n"
        )
    elif mode == "social":
        directive = (
            "=== MODE: SOCIAL ===\n"
            "Handle community features (followers, feed, public promises).\n\n"
        )
    else:
        directive = (
            "=== MODE: ENGAGEMENT ===\n"
            "Respond with warmth, humor, or encouragement. "
            "Use memory_write to save personal facts the user shares.\n\n"
        )
    return directive + _PLANNER_PROMPT_BASE


def _initial_routed_state(user_text: str) -> Dict[str, Any]:
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


def _build_tools_overview(tools: List[Any]) -> str:
    """Build a concise tool overview string for the planner system message."""
    lines = ["AVAILABLE TOOLS:"]
    for t in tools:
        name = getattr(t, "name", "?")
        desc = (getattr(t, "description", "") or "").splitlines()[0][:80]
        lines.append(f"  - {name}: {desc}")
    return "\n".join(lines)


def run_tier2(
    transcript: Dict[str, Any],
    adapter: PlannerAPIAdapter,
    user_id: int,
) -> EvalResult:
    """
    Run Tier 2 eval: real router + planner LLMs, real tools and DB.
    Asserts on expect_route (mode) and expect_tools (tool call list) per turn.
    Requires GROQ_API_KEY or OPENAI_API_KEY in environment.
    """
    errors: List[str] = []
    per_turn_responses: List[str] = []
    called_tools_per_turn: List[List[str]] = []
    rubric_scores: Dict[str, bool] = {}

    turns = transcript.get("turns") or []
    setup = transcript.get("setup") or []

    try:
        _run_setup(adapter, user_id, setup)
    except Exception as e:
        errors.append(f"Setup failed: {e}")
        return EvalResult(passed=False, per_turn_responses=[], db_final={}, rubric_scores={}, errors=errors)

    try:
        router_model, planner_model, responder_model = _build_tier2_models()
    except Exception as e:
        errors.append(f"Model build failed: {e}")
        return EvalResult(passed=False, per_turn_responses=[], db_final={}, rubric_scores={}, errors=errors)

    # Build tools with call tracking
    called_tools_global: List[str] = []
    raw_tools = build_tools_from_adapter(adapter)
    tracked_tools = [_wrap_tracking(t, called_tools_global) for t in raw_tools]

    # Add LLM-based resolve_datetime tool
    try:
        from llms.resolvers import resolve_datetime_with_llm
        def _resolve_datetime_tool(datetime_text: str) -> str:
            called_tools_global.append("resolve_datetime")
            return resolve_datetime_with_llm(router_model, datetime_text, "UTC")
        tracked_tools.append(StructuredTool.from_function(
            func=_resolve_datetime_tool,
            name="resolve_datetime",
            description="Resolve a natural-language date/time phrase to ISO 8601.",
        ))
    except Exception as e:
        errors.append(f"resolve_datetime tool build failed: {e}")

    # Build planner system message that includes tool list so the planner can form valid plans.
    tools_overview = _build_tools_overview(tracked_tools)

    from langchain_core.messages import SystemMessage as _SystemMessage

    def _get_system_message_for_mode(user_id_ctx, mode, user_lang):
        return _SystemMessage(content=tools_overview)

    def _get_planner_prompt_with_tools(mode: str) -> str:
        return _get_planner_prompt_for_mode(mode) + "\n\n" + tools_overview

    app = create_routed_plan_execute_graph(
        tools=tracked_tools,
        router_model=router_model,
        planner_model=planner_model,
        responder_model=responder_model,
        router_prompt=_ROUTER_PROMPT,
        get_planner_prompt_for_mode=_get_planner_prompt_with_tools,
        get_system_message_for_mode=_get_system_message_for_mode,
        emit_plan=False,
        max_iterations=8,
    )

    token = _current_user_id.set(str(user_id))
    state: Dict[str, Any] = _initial_routed_state("")

    try:
        for i, turn in enumerate(turns):
            user_msg = turn.get("user") or ""

            start_idx = len(called_tools_global)

            state = _initial_routed_state(user_msg)

            try:
                result = app.invoke(state)
            except Exception as e:
                errors.append(f"Turn {i + 1} invoke failed: {e}")
                called_tools_per_turn.append([])
                per_turn_responses.append("")
                continue

            state = dict(result)
            final_response = state.get("final_response") or ""
            per_turn_responses.append(final_response)

            turn_called = list(called_tools_global[start_idx:])
            # Also count any tool that the planner decided to call but is pending
            # confirmation or arg resolution — it was PLANNED, which is what we test.
            pending = state.get("pending_clarification") or {}
            pending_tool = pending.get("tool_name")
            if pending_tool and pending_tool not in turn_called:
                turn_called.append(pending_tool)

            called_tools_per_turn.append(turn_called)

            actual_mode = state.get("mode") or ""
            expect_route = turn.get("expect_route")
            if expect_route and actual_mode != expect_route:
                errors.append(
                    f"Turn {i + 1}: expected route={expect_route!r} but got {actual_mode!r}"
                )

            expect_tools = turn.get("expect_tools") or []
            for tool_name in expect_tools:
                if tool_name not in turn_called:
                    errors.append(
                        f"Turn {i + 1}: expected tool {tool_name!r} to be called but it wasn't. "
                        f"Called: {turn_called}"
                    )

            expect_no_tools = turn.get("expect_no_tools") or []
            for tool_name in expect_no_tools:
                if tool_name in turn_called:
                    errors.append(
                        f"Turn {i + 1}: expected tool {tool_name!r} NOT to be called but it was. "
                        f"Called: {turn_called}"
                    )

            expect_pending = turn.get("expect_pending_clarification")
            actual_pending = bool(state.get("pending_clarification"))
            if expect_pending is True and not actual_pending:
                errors.append(f"Turn {i + 1}: expected pending_clarification but none was set.")
            elif expect_pending is False and actual_pending:
                errors.append(f"Turn {i + 1}: expected NO pending_clarification but one was set.")

    finally:
        _current_user_id.reset(token)

    db_final: Dict[str, Any] = {}
    try:
        promises = adapter.get_promises(user_id)
        actions = adapter.get_actions(user_id)
        db_final["promises"] = promises
        db_final["actions"] = actions
    except Exception as e:
        errors.append(f"DB read failed: {e}")

    rubric_scores = evaluate_rubric(transcript, db_final, per_turn_responses, errors)
    rubric_scores["routing"] = not any("expected route=" in e for e in errors)
    rubric_scores["tool_coverage"] = not any("expected tool" in e for e in errors)
    passed = len(errors) == 0

    return EvalResult(
        passed=passed,
        per_turn_responses=per_turn_responses,
        db_final=db_final,
        rubric_scores=rubric_scores,
        errors=errors,
    )
