"""Environment-driven configuration for the MCP server.

Auth turns on automatically when WorkOS is configured (``WORKOS_ISSUER`` +
a resolvable JWKS URL). Until then the server runs in Phase 1 mode, scoping every
request to ``MCP_DEFAULT_USER_ID`` for local testing.
"""

from __future__ import annotations

import os


class MCPConfig:
    def __init__(self) -> None:
        # Phase 1 fallback identity (used only when auth is disabled).
        self.default_user_id = os.getenv("MCP_DEFAULT_USER_ID")

        # Public base URL of this MCP server — the OAuth "resource" in the
        # RFC 9728 protected-resource-metadata document.
        self.resource_server_url = os.getenv("MCP_RESOURCE_URL", "https://mcp.xaana.club").rstrip("/")
        self.miniapp_url = os.getenv("MINIAPP_URL", "https://xaana.club").rstrip("/")

        # WorkOS AuthKit = the authorization server.
        self.workos_issuer = os.getenv("WORKOS_ISSUER")  # e.g. https://<slug>.authkit.app
        # JWKS endpoint for verifying access-token signatures. Set explicitly from
        # the WorkOS dashboard; we only best-effort derive it from the issuer.
        self._workos_jwks_url = os.getenv("WORKOS_JWKS_URL")
        # Optional expected audience (the resource). Leave unset to skip aud check.
        self.workos_audience = os.getenv("WORKOS_AUDIENCE")

        self.required_scopes = [s.strip() for s in os.getenv("MCP_REQUIRED_SCOPES", "").split(",") if s.strip()]
        self.link_code_ttl_seconds = int(os.getenv("MCP_LINK_CODE_TTL_SECONDS", "900"))

    @property
    def jwks_url(self) -> "str | None":
        if self._workos_jwks_url:
            return self._workos_jwks_url
        if self.workos_issuer:
            return self.workos_issuer.rstrip("/") + "/oauth2/jwks"
        return None

    @property
    def auth_enabled(self) -> bool:
        return bool(self.workos_issuer and self.jwks_url)


config = MCPConfig()
