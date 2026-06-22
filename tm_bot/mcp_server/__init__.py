"""MCP (Model Context Protocol) server for the Xaana accountability promise tracker.

This package exposes the existing ``PlannerAPIAdapter`` (the AI-agnostic core of
the bot) as a remote MCP server over Streamable HTTP, so any MCP client — Claude,
ChatGPT, Perplexity, Grok, Mistral — can use the promise/goal tooling directly.

The bot and its LLM layer are untouched: this server reads the same Postgres
through the same repositories. It is purely additive.

Auth (Phase 2) turns on automatically when WorkOS is configured; otherwise the
server runs single-user via ``MCP_DEFAULT_USER_ID`` (Phase 1).

``build_mcp_server`` is intentionally imported lazily (it pulls in the adapter and
DB layer) so lightweight submodules like ``config`` and ``auth`` stay importable
on their own.
"""

__all__ = ["build_mcp_server"]


def __getattr__(name):
    if name == "build_mcp_server":
        from .server import build_mcp_server

        return build_mcp_server
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
