# WorkOS setup for the Xaana MCP server (Phase 2 auth)

WorkOS AuthKit is the OAuth **authorization server**: it hosts the login UI,
issues tokens, supports PKCE (S256), and registers MCP clients automatically via
CIMD/DCR. Our MCP server is the **resource server**: it serves RFC 9728 metadata
and validates the tokens. You only need to configure WorkOS and set a few env
vars — the code is already done.

## 1. WorkOS dashboard (~10 min)

1. **Create an application** — Dashboard → *Applications* → *Create application*.
2. **Enable Dynamic Client Registration** — *Applications → Configuration →
   Manage* under *Dynamic Client Registration*. Turn it on and add default
   scopes (start permissive, e.g. `openid profile email`). This lets Claude
   self-register.
3. **Enable CIMD** — *Connect → Configuration*, enable *Client ID Metadata
   Documents*. This is the newer (2025-11-25 spec) default that ChatGPT and
   newer Claude clients prefer; enabling both CIMD and DCR maximizes
   compatibility.
4. **Find your issuer + JWKS** — open
   `https://<your-authkit-domain>/.well-known/oauth-authorization-server`
   in a browser. Copy the `issuer` and `jwks_uri` values. The AuthKit domain is
   shown in the dashboard (looks like `https://<slug>.authkit.app`, or your
   custom domain).

That's the whole WorkOS side. No redirect URI to configure for us — Claude's
callback (`https://claude.ai/api/mcp/auth_callback`) and ChatGPT's are handled by
WorkOS via DCR/CIMD.

## 2. Env vars to set (in `/opt/zana-config/.env.prod`)

| Var | Value | Notes |
|-----|-------|-------|
| `WORKOS_ISSUER` | the `issuer` from step 4 | **Setting this enables auth.** |
| `WORKOS_JWKS_URL` | the `jwks_uri` from step 4 | If omitted, defaults to `<issuer>/oauth2/jwks` — but copy the real value to be safe. |
| `MCP_RESOURCE_URL` | `https://mcp.xaana.club` | This server's public URL (the PRM `resource`). Must match the connector URL's origin. |
| `WORKOS_AUDIENCE` | *(leave unset at first)* | Skips the `aud` check. Tighten later once you confirm what `aud` WorkOS puts in the token. |
| `MCP_REQUIRED_SCOPES` | *(leave empty at first)* | Comma-separated scopes to require, once you define them. |
| `MINIAPP_URL` | `https://xaana.club` | Promise deep links. |

## 3. What happens at connect time

1. User adds `https://mcp.xaana.club/mcp` as a custom connector (Claude:
   *Settings → Connectors → Add custom connector*; ChatGPT: Developer Mode).
2. Claude/ChatGPT hits the server unauthenticated → gets `401` +
   `WWW-Authenticate` pointing to `/.well-known/oauth-protected-resource`.
3. The client reads our PRM → finds WorkOS → registers (CIMD/DCR) → runs the
   OAuth 2.1 + PKCE login.
4. The client calls tools with the WorkOS access token; we validate it and map
   the subject to a Zana user. First time, the user runs `link_account` with a
   code from the Mini App.

## 4. Verify / troubleshoot

- `curl https://mcp.xaana.club/.well-known/oauth-protected-resource` → should
  return JSON listing `authorization_servers: [<WORKOS_ISSUER>]` and `resource`.
- If the OAuth flow completes in the browser but Claude then errors, it's almost
  always a **resource/audience mismatch**: make sure `MCP_RESOURCE_URL` exactly
  matches the connector URL origin, and don't set `WORKOS_AUDIENCE` until you've
  confirmed the token's `aud`.

## What I need back to deploy with auth on

Just the two values from step 4: **`WORKOS_ISSUER`** and **`WORKOS_JWKS_URL`**.
Then I apply migration `026`, bring up the `zana-mcp` container with these env
vars, and we connect Claude/ChatGPT.
