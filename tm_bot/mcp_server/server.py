"""Build the Xaana promise-tracker MCP server."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from services.planner_api_adapter import PlannerAPIAdapter
from utils.logger import get_logger

from .tools import register_adapter_tools, register_search_fetch_tools

logger = get_logger(__name__)

SERVER_INSTRUCTIONS = (
    "Xaana is an accountability promise tracker. Use these tools to create and "
    "manage a user's promises (recurring weekly goals), log completed activities, "
    "set reminders, schedule plan sessions, and report on progress and streaks. "
    "Promise ids look like 'P1', 'P2'. When a promise id is unknown, use `search` "
    "to find it, then `fetch` for full details."
)


def build_mcp_server(root_dir: str, *, stateless_http: bool = True) -> FastMCP:
    """Create the FastMCP server, wire the adapter, and register all tools.

    Args:
        root_dir: Root directory for user data (passed to PlannerAPIAdapter).
        stateless_http: Run the Streamable HTTP transport statelessly. Our tools
            hold no per-connection state, so this keeps the server easy to scale
            and proxy behind nginx.
    """
    mcp = FastMCP(
        name="Xaana Accountability Promise Tracker",
        instructions=SERVER_INSTRUCTIONS,
        stateless_http=stateless_http,
    )

    adapter = PlannerAPIAdapter(root_dir=root_dir)
    n = register_adapter_tools(mcp, adapter)
    register_search_fetch_tools(mcp, adapter)
    logger.info(f"MCP server ready: {n} adapter tools + search/fetch registered")

    return mcp
