# Hydra OAuth setup for the Xaana MCP server

Self-hosted **Ory Hydra** is the OAuth 2.1 authorization server; it authenticates
users via **Telegram** (our login/consent app) and issues JWT access tokens whose
`subject` is the Telegram user_id. The MCP server validates those tokens against
Hydra's JWKS. No external SaaS, no account linking.

```
Claude / ChatGPT
  → https://mcp.xaana.club/mcp        (401 → RFC 9728 metadata → finds Hydra)
  → https://auth.xaana.club           (Hydra: OAuth 2.1 + PKCE + DCR)
       → /api/oauth/login             (our app: "Log in with Telegram" widget)
       → Hydra accept-login(subject = telegram_user_id)
  → tokens → back to mcp.xaana.club    (subject == Zana user_id)
```

Everything is in `docker-compose.yml` under the `mcp` profile: `hydra`,
`hydra-postgres`, `hydra-migrate`, `zana-mcp`. The Telegram login/consent pages
are served by the existing `zana-webapp` at `/api/oauth/*`.

## 1. Secrets / env (`/opt/zana-config/.env.prod`)

| Var | Value |
|-----|-------|
| `HYDRA_SECRETS_SYSTEM` | a random 32+ char secret (`openssl rand -hex 32`) |
| `HYDRA_DB_PASSWORD` | password for Hydra's Postgres |
| `HYDRA_PUBLIC_URL` | `https://auth.xaana.club` |
| `MCP_RESOURCE_URL` | `https://mcp.xaana.club` |
| `BOT_USERNAME` | the bot's @username (no `@`) — for the Telegram Login Widget |
| `MINIAPP_URL` | `https://xaana.club` |

The MCP server reads `MCP_OIDC_ISSUER`/`MCP_OIDC_JWKS_URL` (defaulted from
`HYDRA_PUBLIC_URL` in compose), so setting `HYDRA_PUBLIC_URL` enables auth.

## 2. DNS + nginx (two new vhosts)

- `auth.xaana.club` → `hydra:4444` (public OAuth endpoints). TLS at nginx; Hydra
  trusts the proxy via `SERVE_TLS_ALLOW_TERMINATION_FROM`.
- `mcp.xaana.club` → `zana-mcp:8090` with **`proxy_buffering off`** and long read
  timeouts (Streamable HTTP / SSE).
- Keep Hydra's admin port `4445` internal only (never expose it).

## 3. Telegram

In BotFather, set the login domain: `/setdomain` → `xaana.club`. This authorizes
the Telegram Login Widget on the consent page.

## 4. Bring it up

```bash
cd /opt/zana-bot
docker compose --profile mcp up -d hydra-postgres hydra-migrate hydra zana-mcp
# verify:
curl https://mcp.xaana.club/.well-known/oauth-protected-resource     # lists auth.xaana.club
curl https://auth.xaana.club/.well-known/oauth-authorization-server  # issuer + jwks_uri
```

Hydra 2.2 does not expose RFC 7591 dynamic client registration itself. Nginx
routes `/oauth2/register` and RFC 8414 metadata to the webapp's constrained DCR
facade, which creates public OAuth clients through Hydra's internal admin API.
Claude/ChatGPT therefore self-register without exposing Hydra's admin port.

## 5. Connect

- **Claude:** Settings → Connectors → Add custom connector → `https://mcp.xaana.club/mcp`.
- **ChatGPT:** Developer Mode → add MCP connector with the same URL.

First connect: the client hits the server, gets the 401 + metadata, discovers
Hydra, runs the OAuth flow, you "Log in with Telegram", and you're in.

## Notes / gotchas

- **JWT access tokens** are on (`STRATEGIES_ACCESS_TOKEN=jwt`) so the MCP server
  can verify via JWKS. If you ever switch Hydra to opaque tokens, the verifier
  must use token introspection instead.
- **Audience:** leave `MCP_OIDC_AUDIENCE` unset — Claude doesn't send the RFC 8707
  resource indicator as of early 2026, so a strict `aud` check breaks the flow.
- The DCR facade intentionally supports authorization-code/refresh-token grants
  and HTTPS redirects (plus localhost HTTP) only. Registration management
  endpoints are not exposed; the Claude/ChatGPT connect flow does not need them.
- This validates at deploy time — the Telegram-HMAC + Hydra-admin flow and the
  token verification can't be exercised without the running stack.
