#!/usr/bin/env python3
"""ASGI entrypoint for the Xaana MCP server.

Usage:
    uvicorn run_mcp_local:app --host 0.0.0.0 --port 8090

The MCP endpoint is served at ``/mcp`` (Streamable HTTP).

Environment variables:
    ROOT_DIR             Root directory for user data (default: ./USERS_DATA_DIR)
    MCP_DEFAULT_USER_ID  Phase 1 only: the user_id every request is scoped to,
                         so the server is testable before OAuth exists. In Phase 2
                         this is replaced by WorkOS bearer-token validation in
                         tm_bot/mcp_server/auth.py.
    MINIAPP_URL          Base URL for promise deep links (default: https://xaana.club)
"""

import os
import sys
from pathlib import Path

# Match run_webapp_local.py: make tm_bot's packages importable as top-level.
sys.path.insert(0, str(Path(__file__).parent / "tm_bot"))

from mcp_server.server import build_mcp_server  # noqa: E402
from mcp_server.auth import CurrentUserMiddleware  # noqa: E402
from utils.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

root_dir = os.path.abspath(os.getenv("ROOT_DIR", str(Path(__file__).parent / "USERS_DATA_DIR")))
os.makedirs(root_dir, exist_ok=True)

_mcp = build_mcp_server(root_dir=root_dir)

# Streamable HTTP ASGI app, wrapped so each request carries the current user_id.
app = CurrentUserMiddleware(_mcp.streamable_http_app())

if not os.getenv("MCP_DEFAULT_USER_ID"):
    logger.warning(
        "MCP_DEFAULT_USER_ID is not set — tool calls will fail with 'No active "
        "user_id set' until it is configured (Phase 1) or OAuth is wired (Phase 2)."
    )

logger.info("=" * 60)
logger.info("Xaana MCP server loaded")
logger.info(f"  Root directory: {root_dir}")
logger.info("  MCP endpoint:   http://localhost:8090/mcp")
logger.info("=" * 60)
