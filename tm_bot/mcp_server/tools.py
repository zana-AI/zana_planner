"""Register the promise-tracker tool surface on the MCP server.

Three groups of tools:

1. **Adapter tools** — reflected mechanically from ``PlannerAPIAdapter`` (the same
   approach ``llms.llm_handler._build_tools`` uses), reusing
   ``llms.tool_wrappers._wrap_tool`` to strip ``user_id``/``self`` and produce a
   clean, model-facing signature. Each call binds the authenticated user via
   ``bind_current_user`` before invoking the adapter.

2. **ChatGPT-compatible ``search`` / ``fetch``** — explicit read-only tools with
   declared output schemas (OpenAI "company knowledge" shape), required for
   ChatGPT's Deep Research surface. Claude ignores them.

No account-linking tools are needed: Hydra's subject is already the Telegram
user_id (see identity.py).
"""

from __future__ import annotations

import functools
from typing import List

from pydantic import BaseModel, Field

from llms.tool_wrappers import _wrap_tool
from llms.tool_exposure import MCP_EXCLUDED_TOOLS as EXCLUDED_TOOLS
from utils.logger import get_logger

from .config import config
from .identity import bind_current_user, resolve_user_id_or_none
from .serialization import normalize_result

logger = get_logger(__name__)

# Which adapter methods are exposed here is governed centrally — see
# llms/tool_exposure.py and docs/ADAPTER_API_CONTRACT.md. New public adapter
# methods are exposed by default unless listed there.


def _bound_tool(fn):
    """Bind the authenticated user, call the adapter method, normalize the result.

    Preserves the wrapped function's metadata (incl. the ``__signature__`` set by
    ``_wrap_tool``) so the MCP framework builds the correct input schema.
    """

    @functools.wraps(fn)
    def wrapper(**kwargs):
        with bind_current_user():
            return normalize_result(fn(**kwargs))

    return wrapper


def register_adapter_tools(mcp, adapter) -> int:
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
            mcp.add_tool(_bound_tool(_wrap_tool(candidate, attr_name)), name=attr_name, description=description)
            registered += 1
        except Exception as e:  # noqa: BLE001 — skip an un-schematizable method, keep the rest
            logger.warning(f"Skipping MCP tool {attr_name}: {e}")

    return registered


# --- ChatGPT-compatible search / fetch -------------------------------------


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


def _promise_field(d: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        if d.get(k) not in (None, ""):
            return str(d[k])
    return default


def register_search_fetch_tools(mcp, adapter) -> None:
    @mcp.tool(
        name="search",
        description=(
            "Search the user's accountability promises/goals by free-text query. "
            "Returns matching promises with ids to pass to fetch."
        ),
    )
    def search(query: str) -> SearchResults:
        user_id = resolve_user_id_or_none()
        if not user_id:
            return SearchResults(results=[])
        base = config.miniapp_url
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
        description="Fetch full details and the progress report for one promise by id (from search).",
    )
    def fetch(id: str) -> FetchResult:
        user_id = resolve_user_id_or_none()
        base = config.miniapp_url
        if not user_id:
            return FetchResult(id=id, title="", text="Not authenticated or account not linked.", url=f"{base}/promise/{id}")
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

