"""Build the Xaana promise-tracker MCP server."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from repositories.mcp_links_repo import McpLinksRepository
from services.planner_api_adapter import PlannerAPIAdapter
from utils.logger import get_logger

from .auth import WorkOSTokenVerifier, build_auth_settings
from .config import config
from .tools import register_adapter_tools, register_link_tools, register_search_fetch_tools

logger = get_logger(__name__)

SERVER_INSTRUCTIONS = (
    "Xaana is an accountability promise tracker. Use these tools to create and "
    "manage a user's promises (recurring weekly goals), log completed activities, "
    "set reminders, schedule plan sessions, and report on progress and streaks. "
    "Promise ids look like 'P1', 'P2'. When a promise id is unknown, use `search` "
    "to find it, then `fetch` for full details. If a tool reports the account is "
    "not linked, tell the user to get a code from the Xaana app and call "
    "`link_account` with it."
)


def build_mcp_server(root_dir: str, *, stateless_http: bool = True) -> FastMCP:
    """Create the FastMCP server, wire the adapter, and register all tools.

    Auth is enabled automatically when WorkOS is configured (see config). When it
    is, FastMCP serves the RFC 9728 protected-resource-metadata document and
    rejects unauthenticated requests. Otherwise the server runs in Phase 1 mode
    (single user via MCP_DEFAULT_USER_ID) — do not expose that publicly.
    """
    auth_kwargs = {}
    if config.auth_enabled:
        auth_kwargs = {
            "token_verifier": WorkOSTokenVerifier(
                jwks_url=config.jwks_url,
                issuer=config.workos_issuer,
                audience=config.workos_audience,
                required_scopes=config.required_scopes,
            ),
            "auth": build_auth_settings(config),
        }
        logger.info("MCP auth ENABLED (WorkOS) — resource=%s", config.resource_server_url)
    else:
        logger.warning(
            "MCP auth DISABLED — falling back to MCP_DEFAULT_USER_ID. Do not expose "
            "this server publicly until WorkOS env vars are set."
        )

    mcp = FastMCP(
        name="Xaana Accountability Promise Tracker",
        instructions=SERVER_INSTRUCTIONS,
        stateless_http=stateless_http,
        **auth_kwargs,
    )

    adapter = PlannerAPIAdapter(root_dir=root_dir)
    links_repo = McpLinksRepository()

    n = register_adapter_tools(mcp, adapter)
    register_search_fetch_tools(mcp, adapter)
    register_link_tools(mcp, links_repo)
    logger.info(f"MCP server ready: {n} adapter tools + search/fetch + account linking")

    return mcp
