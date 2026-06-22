# Xaana MCP server

Exposes the accountability promise tracker (`PlannerAPIAdapter`) as a remote
**MCP** server over Streamable HTTP, so any MCP client — Claude, ChatGPT,
Perplexity, Grok, Mistral — can use the promise/goal tooling directly. Purely
additive: it reads the same Postgres through the same repositories as the bot,
and the bot + LLM layer are untouched.

Auth is provided by a **self-hosted Ory Hydra** that authenticates users via
**Telegram**. Because Hydra sets the token subject to the Telegram user_id, the
validated subject *is* the Zana user_id — no account-linking step.

## Layout

| File | Role |
|------|------|
| `server.py` | Builds the `FastMCP` server, wires the adapter, enables auth when an OIDC issuer (Hydra) is configured, registers tools. |
| `tools.py` | Reflects adapter methods into MCP tools (reusing `llms.tool_wrappers._wrap_tool`) + the ChatGPT-compatible `search`/`fetch` pair. |
| `serialization.py` | Normalizes adapter return values toward JSON (the seam for the incremental string→JSON work). |
| `config.py` | Env-driven config; `auth_enabled` flips when `MCP_OIDC_ISSUER` is set. |
| `auth.py` | `OidcTokenVerifier` (JWKS/JWT validation against Hydra) + `AuthSettings` builder. |
| `identity.py` | `user_id = access_token.subject` (Telegram id), with `MCP_DEFAULT_USER_ID` fallback when auth is off. |
| `../webapp/routers/oauth_consent.py` | Telegram login + consent app that drives Hydra's accept-login/consent (`/api/oauth/*`). |
| `../../run_mcp_local.py` | ASGI entrypoint: `uvicorn run_mcp_local:app`. Serves `/mcp` (+ `/.well-known/oauth-protected-resource` when auth is on). |

The Hydra OAuth server, its Postgres, and a one-shot migration container live in
`docker-compose.yml` under the `mcp` profile. See **`HYDRA_SETUP.md`** for the
full deploy + connect guide.

## Run locally (no auth)

```bash
pip install -r requirements.mcp.txt
export ROOT_DIR=$(pwd)/USERS_DATA_DIR
export MCP_DEFAULT_USER_ID=<your-telegram-user-id>   # scopes all calls to this user
export DATABASE_URL_STAGING=...                      # tools hit the real DB at call time
# leave MCP_OIDC_ISSUER unset to keep auth off
uvicorn run_mcp_local:app --host 0.0.0.0 --port 8090
```

Inspect the tool surface with the MCP Inspector (`npx
@modelcontextprotocol/inspector`, connect to `http://localhost:8090/mcp`).
`tools/list` works without a database; calling a tool needs DB env + a user.

## Env vars

| Var | Purpose |
|-----|---------|
| `MCP_OIDC_ISSUER` | Hydra public URL, e.g. `https://auth.xaana.club`. **Setting this enables auth.** |
| `MCP_OIDC_JWKS_URL` | Defaults to `<issuer>/.well-known/jwks.json`. |
| `MCP_OIDC_AUDIENCE` | Optional expected `aud`. Leave unset (Claude omits the resource indicator as of early 2026). |
| `MCP_RESOURCE_URL` | Public URL of this server (the PRM `resource`), e.g. `https://mcp.xaana.club`. |
| `MCP_REQUIRED_SCOPES` | Optional comma-separated required scopes. |
| `MCP_DEFAULT_USER_ID` | No-auth fallback only; ignored once auth is enabled. |
| `MINIAPP_URL` | Base for promise deep links (default `https://xaana.club`). |

## Tool surface

- **Adapter tools** — most public `PlannerAPIAdapter` methods. See `EXCLUDED_TOOLS`
  in `tools.py` for what's held back (raw SQL, internal helpers, batch plural
  variants, content-pipeline helpers).
- **`search` / `fetch`** — read-only, with declared output schemas (OpenAI
  "company knowledge" shape). Required for ChatGPT's Deep Research surface.
