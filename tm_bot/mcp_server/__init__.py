"""MCP (Model Context Protocol) server for the Xaana accountability promise tracker.

This package exposes the existing ``PlannerAPIAdapter`` (the AI-agnostic core of
the bot) as a remote MCP server over Streamable HTTP, so any MCP client — Claude,
ChatGPT, Perplexity, Grok, Mistral — can use the promise/goal tooling directly.

The bot and its LLM layer are untouched: this server reads the same Postgres
through the same repositories. It is purely additive.

Phase 1 (current): server + tool surface, testable with the MCP Inspector using a
stub "current user" (``MCP_DEFAULT_USER_ID``). Phase 2 replaces that stub with
WorkOS-backed OAuth token validation in ``auth.py``.
"""

from .server import build_mcp_server

__all__ = ["build_mcp_server"]
