"""MCP account-linking endpoint.

Mints a short-lived one-time code for the authenticated Telegram user. The user
then enters this code in their AI client (via the `link_account` MCP tool) to
link their Claude/ChatGPT identity to their Xaana account.

Auth reuses the existing Telegram initData dependency — no new auth surface.
"""

import os

from fastapi import APIRouter, Depends, Request

from repositories.mcp_links_repo import McpLinksRepository
from webapp.dependencies import get_current_user

router = APIRouter(prefix="/api", tags=["mcp"])

_links = McpLinksRepository()


@router.post("/mcp/link-code")
async def create_mcp_link_code(request: Request, user_id: int = Depends(get_current_user)):
    ttl = int(os.getenv("MCP_LINK_CODE_TTL_SECONDS", "900"))
    code, expires_at = _links.create_link_code(user_id, ttl_seconds=ttl)
    return {"code": code, "expires_at": expires_at, "ttl_seconds": ttl}
