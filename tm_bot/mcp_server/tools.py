"""Register the promise-tracker tool surface on the MCP server.

Two groups of tools are registered:

1. **Adapter tools** — reflected mechanically from ``PlannerAPIAdapter`` (the same
   approach ``llms.llm_handler._build_tools`` uses for the LLM), reusing
   ``llms.tool_wrappers._wrap_tool`` to strip ``user_id`` and produce a clean,
   model-facing signature. This is the "extract and expose" core: each public
   adapter method becomes an MCP tool.

2. **ChatGPT-compatible ``search`` / ``fetch``** — explicit read-only tools with
   declared output schemas. ChatGPT's non-developer surfaces (Deep Research /
   company knowledge) reject any connector that lacks these. They map onto the
   user's promises so the same server is first-class in both Claude and ChatGPT.
"""

from __future__ import annotations

import functools
import inspect
import os
from typing import Any, List

from pydantic import BaseModel, Field

from llms.tool_wrappers import _current_user_id, _wrap_tool
from utils.logger import get_logger

from .serialization import normalize_result

logger = get_logger(__name__)


# Methods that should not be exposed as tools. Mirrors the LLM's exclusion list
# (llm_handler._build_tools) plus a few MCP-specific omissions: the raw SQL tools
# (unsafe to expose to arbitrary clients), batch plural variants (kept the
# singular forms for a clean first surface), and content-pipeline helpers that
# require non-MCP code paths.
EXCLUDED_TOOLS = {
    # Raw DB access — never expose to remote clients.
    "query_database",
    "get_db_schema",
    # Back-compat aliases superseded by user-verb names.
    "add_action",
    "add_plan_session",
    # Internal helpers.
    "no_op",
    "maybe_ask_profile_question",
    "clear_profile_pending_question",
    "set_llm_handler",
    # Batch plural variants — exposed as the singular forms instead.
    "schedule_sessions",
    "log_completed_activities",
    "create_reminders",
    # Background content-pipeline helpers (driven by non-MCP code).
    "process_shared_link",
    "estimate_time_for_content",
    "summarize_content",
    # Redundant DataFrame variant.
    "get_actions_df",
}


def _normalizing(fn):
    """Wrap a tool callable so its return value is normalized to JSON.

    Preserves the wrapped function's metadata — crucially ``__signature__`` and
    ``__annotations__`` set by ``_wrap_tool`` — so the MCP framework still builds
    the correct (user_id-stripped) input schema.
    """

    @functools.wraps(fn)
    def wrapper(**kwargs):
        return normalize_result(fn(**kwargs))

    return wrapper


def register_adapter_tools(mcp, adapter) -> int:
    """Register each eligible PlannerAPIAdapter method as an MCP tool.

    Returns the number of tools registered.
    """
    registered = 0
    for attr_name in dir(adapter):
        if attr_name.startswith("_") or attr_name in EXCLUDED_TOOLS:
            continue
        candidate = getattr(adapter, attr_name)
        if not callable(candidate):
            continue

        doc = (candidate.__doc__ or "").strip()
        first_line = doc.splitlines()[0].strip() if doc else ""
        if len(first_line) > 200:
            first_line = first_line[:197] + "..."
        description = first_line or f"Planner action {attr_name}"

        try:
            wrapped = _normalizing(_wrap_tool(candidate, attr_name))
            mcp.add_tool(wrapped, name=attr_name, description=description)
            registered += 1
        except Exception as e:  # noqa: BLE001 — skip an un-schematizable method, keep the rest
            logger.warning(f"Skipping MCP tool {attr_name}: {e}")

    return registered


# --- ChatGPT-compatible search / fetch -------------------------------------
# Output schemas follow OpenAI's "company knowledge" compatibility shape so the
# connector works in ChatGPT Deep Research, not just Developer Mode.


class SearchResult(BaseModel):
    id: str = Field(description="Stable identifier (the promise_id) to pass to fetch.")
    title: str = Field(description="Human-readable promise title.")
    url: str = Field(description="Deep link to the promise in the Xaana app.")


class SearchResults(BaseModel):
    results: List[SearchResult]


class FetchResult(BaseModel):
    id: str
    title: str
    text: str = Field(description="Full text/report content for the promise.")
    url: str
    metadata: dict = Field(default_factory=dict)


def _miniapp_url() -> str:
    return os.getenv("MINIAPP_URL", "https://xaana.club").rstrip("/")


def _promise_field(d: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        if d.get(k) not in (None, ""):
            return str(d[k])
    return default


def register_search_fetch_tools(mcp, adapter) -> None:
    """Register the ChatGPT-required read-only search/fetch pair."""

    @mcp.tool(
        name="search",
        description=(
            "Search the user's accountability promises/goals by free-text query. "
            "Returns matching promises with ids to pass to fetch."
        ),
    )
    def search(query: str) -> SearchResults:
        user_id = _current_user_id.get()
        if not user_id:
            return SearchResults(results=[])
        base = _miniapp_url()
        q = (query or "").strip().lower()
        out: List[SearchResult] = []
        for d in adapter.get_promises(user_id=user_id):
            title = _promise_field(d, "text", "promise_text", "title").replace("_", " ")
            pid = _promise_field(d, "id", "promise_id")
            if not pid:
                continue
            if not q or q in title.lower():
                out.append(SearchResult(id=pid, title=title, url=f"{base}/promise/{pid}"))
        return SearchResults(results=out)

    @mcp.tool(
        name="fetch",
        description=(
            "Fetch the full details and progress report for one promise by id "
            "(as returned by search)."
        ),
    )
    def fetch(id: str) -> FetchResult:
        user_id = _current_user_id.get()
        base = _miniapp_url()
        if not user_id:
            return FetchResult(id=id, title="", text="Not authenticated.", url=f"{base}/promise/{id}")
        report = adapter.get_promise_report(user_id=user_id, promise_id=id)
        promise = adapter.get_promise(user_id=user_id, promise_id=id)
        title = ""
        if promise is not None:
            title = str(getattr(promise, "text", "") or "").replace("_", " ")
        return FetchResult(
            id=id,
            title=title,
            text=str(report) if report is not None else "",
            url=f"{base}/promise/{id}",
            metadata={},
        )
