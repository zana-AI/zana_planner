"""
Conversation eval harness: load transcripts, run Tier 1 (graph + mock planner), evaluate rubric.
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
from llms.agent import create_plan_execute_graph
from llms.tool_wrappers import _current_user_id, _wrap_tool
from services.planner_api_adapter import PlannerAPIAdapter
from langchain.tools import StructuredTool

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
