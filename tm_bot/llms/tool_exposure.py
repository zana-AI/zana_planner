"""Single source of truth for which ``PlannerAPIAdapter`` methods are exposed as tools.

Two channels reflect the adapter into a model-facing tool surface:

* the in-app LLM agent — ``llms.llm_handler.PlannerLLMHandler._build_tools``
* the MCP server — ``tm_bot.mcp_server.tools.register_adapter_tools``

Both iterate ``dir(adapter)`` and expose every public method *except* the names
listed here. Exposure is therefore a **denylist**: a newly added public adapter
method is exposed by default. When you add a public method, decide whether it
should reach the LLM and/or remote MCP clients and, if not, add it to the
relevant set below.

The two sets are intentionally allowed to differ (e.g. MCP keeps the singular
write-verbs and drops batch variants), but keeping them in one file makes the
differences reviewable. ``docs/ADAPTER_API_CONTRACT.md`` explains the policy, and
``tm_bot/tests/test_adapter_tool_contract.py`` snapshots the resulting surface so
any drift shows up in review.
"""

from __future__ import annotations

from typing import Iterable, List, Set

# Excluded from the LLM agent's tool surface.
LLM_EXCLUDED_TOOLS: Set[str] = {
    "query_database",   # SQL tool - complex, rarely needed, adds schema bloat
    "get_db_schema",    # Database schema - on-demand only
    # Back-compat aliases superseded by user-verb names; hidden so the planner
    # only sees one canonical tool per intent.
    "add_action",          # → log_completed_activity
    "add_plan_session",    # → schedule_session
    # Internal helpers that pollute the planner's tool vocabulary.
    "no_op",
    "maybe_ask_profile_question",
    "set_llm_handler",   # internal wiring, not a user-facing tool
    # Superseded by LLM-based resolvers added in _build_tools.
    "resolve_datetime",
    "search_promises",
    # Async wrappers — the LLM should call the sync method instead.
    "async_get_settings",
    "async_save_settings",
    "async_get_promises",
    "async_get_promise_report",
    "async_get_weekly_summary",
    # Redundant DataFrame variant; get_actions covers the LLM use case.
    "get_actions_df",
    # Background content-pipeline helpers; called from non-LLM code paths.
    "process_shared_link",
    "estimate_time_for_content",
    "summarize_content",
}

# Excluded from the remote MCP tool surface. Shares the LLM exclusions for the
# internal/unsafe/redundant methods (raw SQL, internal helpers, the async_*
# duplicates of sync methods, resolve_datetime, and search_promises — the
# ChatGPT `search`/`fetch` tools cover remote search), then diverges
# deliberately by *also* hiding the batch/plural write variants (keeping the
# singular forms schedule_session / log_completed_activity / create_reminder)
# and clear_profile_pending_question (bot-flow only).
MCP_EXCLUDED_TOOLS: Set[str] = LLM_EXCLUDED_TOOLS | {
    "clear_profile_pending_question",
    "schedule_sessions",
    "log_completed_activities",
    "create_reminders",
}


def public_adapter_methods(adapter_or_cls) -> List[str]:
    """Public (non-underscore) callable attribute names on an adapter or its class.

    Accepts either an instance or the class so callers (and the contract test)
    can enumerate the surface without instantiating the adapter.
    """
    names: List[str] = []
    for attr_name in dir(adapter_or_cls):
        if attr_name.startswith("_"):
            continue
        if not callable(getattr(adapter_or_cls, attr_name, None)):
            continue
        names.append(attr_name)
    return names


def exposed_tools(adapter_or_cls, excluded: Iterable[str]) -> List[str]:
    """Tool names a reflecting surface would expose: public methods minus ``excluded``."""
    excluded_set = set(excluded)
    return sorted(n for n in public_adapter_methods(adapter_or_cls) if n not in excluded_set)
