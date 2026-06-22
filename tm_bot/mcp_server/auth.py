"""OIDC access-token verification for the MCP server.

The MCP server is an OAuth *resource server*: our self-hosted Ory Hydra (the
authorization server) runs the OAuth 2.1 + PKCE flow, dynamic client
registration, and — via its login app — Telegram authentication. Clients (Claude,
ChatGPT, ...) present the resulting JWT access token here as
``Authorization: Bearer``. We verify the signature against Hydra's JWKS and
surface the subject (which Hydra sets to the Telegram user_id).

Wiring this verifier + ``build_auth_settings`` into FastMCP also makes it serve
the RFC 9728 protected-resource-metadata document and reject unauthenticated
requests with a spec-correct ``401 / WWW-Authenticate``.
"""

from __future__ import annotations

from typing import List, Optional

import anyio
import jwt
from jwt import PyJWKClient

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings

from utils.logger import get_logger

from .config import MCPConfig

logger = get_logger(__name__)


def _extract_scopes(claims: dict) -> List[str]:
    """Scopes may be a space-delimited `scope`, an `scp` list, or `permissions`."""
    scope = claims.get("scope")
    if isinstance(scope, str):
        return [s for s in scope.split() if s]
    for key in ("scp", "permissions"):
        val = claims.get(key)
        if isinstance(val, list):
            return [str(s) for s in val]
    return []


class OidcTokenVerifier(TokenVerifier):
    """Validate a JWT access token from the OIDC AS (Hydra) and return an MCP AccessToken."""

    def __init__(
        self,
        jwks_url: str,
        issuer: Optional[str],
        audience: Optional[str] = None,
        required_scopes: Optional[List[str]] = None,
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        self.required_scopes = set(required_scopes or [])
        # PyJWKClient fetches and caches signing keys; reused across requests.
        self._jwk_client = PyJWKClient(jwks_url)

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        try:
            # JWKS fetch/verify is blocking; keep it off the event loop.
            signing_key = await anyio.to_thread.run_sync(
                self._jwk_client.get_signing_key_from_jwt, token
            )
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience if self.audience else None,
                options={"verify_aud": bool(self.audience)},
            )
        except Exception as e:  # noqa: BLE001 — any failure is an invalid token
            logger.warning(f"MCP token rejected: {e}")
            return None

        subject = claims.get("sub")
        if not subject:
            return None

        scopes = _extract_scopes(claims)
        if self.required_scopes and not self.required_scopes.issubset(set(scopes)):
            logger.warning("MCP token missing required scopes")
            return None

        return AccessToken(
            token=token,
            client_id=claims.get("client_id") or claims.get("azp") or "",
            scopes=scopes,
            expires_at=claims.get("exp"),
            resource=self.audience,
            subject=str(subject),
            claims=claims,
        )


def build_auth_settings(config: MCPConfig) -> AuthSettings:
    return AuthSettings(
        issuer_url=config.oidc_issuer,
        resource_server_url=config.resource_server_url,
        required_scopes=config.required_scopes or None,
    )
