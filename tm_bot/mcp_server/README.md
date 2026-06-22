# Xaana MCP server

Exposes the accountability promise tracker (`PlannerAPIAdapter`) as a remote
**MCP** server over Streamable HTTP, so any MCP client — Claude, ChatGPT,
Perplexity, Grok, Mistral — can use the promise/goal tooling directly. Purely
additive: it reads the same Postgres through the same repositories as the bot,
and the bot + LLM layer are untouched.

## Layout

| File | Role |
|------|------|
| `server.py` | Builds the `FastMCP` server, wires the adapter, enables auth when WorkOS is configured, registers tools. |
| `tools.py` | Reflects adapter methods into MCP tools (reusing `llms.tool_wrappers._wrap_tool`), the ChatGPT-compatible `search`/`fetch` pair, and `account_status`/`link_account`. |
| `serialization.py` | Normalizes adapter return values toward JSON (the seam for the incremental string→JSON work). |
| `config.py` | Env-driven config; `auth_enabled` flips when WorkOS is set. |
| `auth.py` | `WorkOSTokenVerifier` (JWKS/JWT validation) + `AuthSettings` builder. |
| `identity.py` | Maps the validated OAuth subject → Zana `user_id` (account-link table) and binds it per call; falls back to `MCP_DEFAULT_USER_ID` when auth is off. |
| `../repositories/mcp_links_repo.py` | Account-link + one-time-code persistence (migration `026`). |
| `../webapp/routers/mcp_link.py` | `POST /api/mcp/link-code` — mints a code for the authed Telegram user. |
| `../../run_mcp_local.py` | ASGI entrypoint: `uvicorn run_mcp_local:app`. Serves `/mcp` (+ `/.well-known/oauth-protected-resource` when auth is on). |

## Run locally

```bash
pip install -r requirements.mcp.txt          # adds the `mcp` SDK on top of the app deps
export ROOT_DIR=$(pwd)/USERS_DATA_DIR
export MCP_DEFAULT_USER_ID=<your-telegram-user-id>   # Phase 1: scopes all calls to this user
export DATABASE_URL_STAGING=...              # tools hit the real DB at call time
uvicorn run_mcp_local:app --host 0.0.0.0 --port 8090
```

Inspect/test the tool surface with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector
# connect to: http://localhost:8090/mcp  (Streamable HTTP)
```

`tools/list` works without a database (it only introspects signatures). Calling a
tool requires DB env and `MCP_DEFAULT_USER_ID`.

## Tool surface

- **Adapter tools** — most public `PlannerAPIAdapter` methods (add/update/delete
  promises, log activities, reminders, plan sessions, reports, streaks, settings,
  social, profile). See `EXCLUDED_TOOLS` in `tools.py` for what's held back (raw
  SQL, internal helpers, batch plural variants, content-pipeline helpers).
- **`search` / `fetch`** — read-only, with declared output schemas in OpenAI's
  "company knowledge" shape. Required for ChatGPT's Deep Research surface; Claude
  ignores them.

## Auth (Phase 2 — WorkOS)

Auth turns on automatically once WorkOS is configured. FastMCP then serves the
RFC 9728 metadata at `/.well-known/oauth-protected-resource`, rejects
unauthenticated calls with `401 + WWW-Authenticate`, and validates each bearer
token against WorkOS's JWKS. WorkOS (AuthKit) is the authorization server — it
runs the OAuth 2.1 + PKCE flow, dynamic client registration, and login UI that
Claude/ChatGPT drive; this server only verifies tokens and maps identity.

### Env vars

| Var | Purpose |
|-----|---------|
| `WORKOS_ISSUER` | AuthKit issuer, e.g. `https://<slug>.authkit.app`. Setting it enables auth. |
| `WORKOS_JWKS_URL` | JWKS endpoint (from the WorkOS dashboard). Defaults to `<issuer>/oauth2/jwks`. |
| `WORKOS_AUDIENCE` | Optional expected `aud`. Unset = skip audience check. |
| `MCP_RESOURCE_URL` | Public URL of this server (the PRM `resource`), e.g. `https://mcp.xaana.club`. |
| `MCP_REQUIRED_SCOPES` | Optional comma-separated scopes required on the token. |
| `MCP_LINK_CODE_TTL_SECONDS` | Link-code lifetime (default 900). |
| `MCP_DEFAULT_USER_ID` | Phase 1 fallback only; ignored once auth is enabled. |
| `MINIAPP_URL` | Base for promise deep links (default `https://xaana.club`). |

### Account linking (Telegram ↔ OAuth)

The OAuth identity (a WorkOS subject) is bridged to a Zana `user_id`:

1. In the Xaana Mini App, the user hits `POST /api/mcp/link-code` (authed by the
   existing Telegram initData) and gets a short one-time code.
2. In their AI client (connected to this server), the user calls the
   `link_account` tool with that code. The server redeems it, mapping
   `(issuer, subject) → user_id` in `mcp_account_links`.
3. Subsequent calls auto-resolve. `account_status` reports link state; unlinked
   action tools return a clear "get a code and call link_account" message.

> Requires migration `026_add_mcp_account_links` and a frontend "Connect AI"
> action that calls `POST /api/mcp/link-code` (not yet built).

## Roadmap

- **Phase 1 (done)** — server + tool surface + stub identity.
- **Phase 2 (this)** — WorkOS token validation, RFC 9728 metadata, Telegram↔OAuth
  account linking. *Needs:* a WorkOS tenant + env vars, migration `026` applied,
  and the Mini App "Connect AI" button.
- **Phase 3** — deploy: apply migration `026`; `docker compose --profile mcp up -d
  zana-mcp`; DNS `mcp.xaana.club`; cert SAN; nginx route with `proxy_buffering
  off` and long read timeouts; then add as a custom connector in Claude and
  ChatGPT.
```
