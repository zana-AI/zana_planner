# Xaana MCP server

Exposes the accountability promise tracker (`PlannerAPIAdapter`) as a remote
**MCP** server over Streamable HTTP, so any MCP client — Claude, ChatGPT,
Perplexity, Grok, Mistral — can use the promise/goal tooling directly. Purely
additive: it reads the same Postgres through the same repositories as the bot,
and the bot + LLM layer are untouched.

## Layout

| File | Role |
|------|------|
| `server.py` | Builds the `FastMCP` server, wires the adapter, registers tools. |
| `tools.py` | Reflects adapter methods into MCP tools (reusing `llms.tool_wrappers._wrap_tool`) + the ChatGPT-compatible `search`/`fetch` pair. |
| `serialization.py` | Normalizes adapter return values toward JSON (the seam for the incremental string→JSON work). |
| `auth.py` | Per-request identity. **Phase 1 stub** (env user); **Phase 2** = WorkOS token validation. |
| `../../run_mcp_local.py` | ASGI entrypoint: `uvicorn run_mcp_local:app`. Serves `/mcp`. |

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

## Roadmap

- **Phase 1 (this)** — server + tool surface + stub identity; testable end-to-end.
- **Phase 2** — WorkOS OAuth: implement bearer-token validation in `auth.py`, add
  the RFC 9728 protected-resource-metadata endpoint, and build the Telegram↔OAuth
  account-linking table so the validated subject maps to a Zana `user_id`.
- **Phase 3** — deploy: `docker compose --profile mcp up -d zana-mcp`, DNS
  `mcp.xaana.club`, cert SAN, nginx route with `proxy_buffering off` and long read
  timeouts for streaming; then add as a custom connector in Claude and ChatGPT.
```
