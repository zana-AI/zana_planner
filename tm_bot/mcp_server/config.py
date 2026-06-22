"""Environment-driven configuration for the MCP server.

Auth turns on automatically when an OIDC issuer is configured (``MCP_OIDC_ISSUER``,
e.g. our self-hosted Ory Hydra). Until then the server runs in single-user mode,
scoping every request to ``MCP_DEFAULT_USER_ID`` for local testing.

Because Hydra authenticates users via Telegram (its login app sets the token
subject to the Telegram user_id), the token subject *is* the Zana user_id — no
account-linking step is needed.
"""

from __future__ import annotations

import os


class MCPConfig:
    def __init__(self) -> None:
        # Single-user fallback (used only when auth is disabled).
        self.default_user_id = os.getenv("MCP_DEFAULT_USER_ID")

        # Public base URL of this MCP server — the OAuth "resource" in the
        # RFC 9728 protected-resource-metadata document.
        self.resource_server_url = os.getenv("MCP_RESOURCE_URL", "https://mcp.xaana.club").rstrip("/")
        self.miniapp_url = os.getenv("MINIAPP_URL", "https://xaana.club").rstrip("/")

        # OIDC authorization server (Ory Hydra). Setting the issuer enables auth.
        self.oidc_issuer = os.getenv("MCP_OIDC_ISSUER")
        self._oidc_jwks_url = os.getenv("MCP_OIDC_JWKS_URL")
        # Optional expected audience. Leave unset (Claude omits the resource
        # indicator as of early 2026, so strict aud checks break the flow).
        self.oidc_audience = os.getenv("MCP_OIDC_AUDIENCE")

        self.required_scopes = [s.strip() for s in os.getenv("MCP_REQUIRED_SCOPES", "").split(",") if s.strip()]

    @property
    def jwks_url(self) -> "str | None":
        if self._oidc_jwks_url:
            return self._oidc_jwks_url
        if self.oidc_issuer:
            # Hydra serves its JWT signing keys here.
            return self.oidc_issuer.rstrip("/") + "/.well-known/jwks.json"
        return None

    @property
    def auth_enabled(self) -> bool:
        return bool(self.oidc_issuer and self.jwks_url)


config = MCPConfig()
