---
name: local-preview
description: Launch the Xaana webapp locally (Dockerized backend on :8080 vs the real prod DB + Vite frontend on :5173) so it can be previewed and edited in the embedded preview, authenticated as the admin user with no Telegram.
---

# local-preview

Bring up the full Xaana Mini App locally for previewing and editing **in the embedded
preview panel**, showing **real prod data**, logged in as the admin user — no Telegram,
no token copying.

> **Invoke:** `/local-preview` — optionally pass `staging` to use the staging DB instead
> of prod, or `rebuild` to force a Docker image rebuild.

## Why this shape

- The embedded preview only renders **localhost** URLs. Proxying `/api` to the live
  `xaana.club` backend gets blocked (avatars/redirects resolve off-localhost), so the
  backend must run **locally** → everything is `localhost`.
- A host Python venv is unreliable here: the repo pins langchain 1.2.x (local conda
  envs are on 0.3.x) and `uvloop` has no Windows wheels. So the backend runs in Docker
  via `Dockerfile.webapp` — the supported, reproducible path.
- `WEBAPP_DEV_AUTH_ENABLED=1` + `WEBAPP_DEV_ADMIN_USER_ID=<admin id>` lets
  `/api/auth/dev-admin-login` mint a session as the real admin user (dev auth is
  refused when `ENVIRONMENT=production`, so the container runs as `staging` with
  `DATABASE_URL_STAGING` overridden to the chosen DB).

## Requirements (what a fresh machine needs)

The launcher self-checks the first three and prints exactly what's missing:

- **Docker Desktop running** — script aborts with "Docker daemon not reachable" if not.
- **`.env` at the repo root** — NOT in git (has `DATABASE_URL_PROD/STAGING`, `ADMIN_IDS`,
  and LLM keys the backend needs at import). Script aborts with "`.env` not found" if absent.
  Copy it from your other machine / the secrets store.
- **A reachable DB** — the prod Postgres (`34.155.80.153:5432`) must be reachable from
  this host (it's open to the public internet, but a restrictive network/VPN can block it).
- **Frontend deps** — `webapp_frontend/node_modules`; the script's final hint tells you to
  run `npm --prefix webapp_frontend install` if it's missing.
- **`.claude/launch.json`** — gitignored (machine-local). The preview tool auto-creates it;
  or just run the `npm` dev command directly.

The Docker image (`zana-webapp-local`) is built automatically on first run.

## Steps

### 1. Start the backend (Docker, :8080)

```bash
bash scripts/local_preview.sh            # prod DB (default)
# PREVIEW_DB=staging bash scripts/local_preview.sh   # staging DB
# bash scripts/local_preview.sh --build  # force image rebuild
```

This reads `DATABASE_URL_PROD` (or `_STAGING`) and the first `ADMIN_IDS` entry from
`.env`, builds `zana-webapp-local` if missing, runs it on `:8080`, and waits for
`/api/health`. Requires Docker Desktop running.

### 2. Start the frontend (Vite, :5173)

Ensure `webapp_frontend/vite.config.ts` proxy `/api` target is `http://127.0.0.1:8080`
(the repo default). Then start the dev server. Inside Claude Code use the preview tool
with `.claude/launch.json` (config name `webapp-frontend`); a human can run:

```bash
npm --prefix webapp_frontend run dev
```

### 3. Log in as the admin user

Navigate the preview to **`/dev-admin`** and click **"Enter as dev admin"** (or POST
`/api/auth/dev-admin-login`). This stores a `telegram_auth_token` for the admin id and
the dashboard loads real data. `shouldUseLocalMockData()` returns `false` once a token
is present, so mock data is bypassed (see `webapp_frontend/src/api/mockData.ts`).

### 4. Edit

Edit files under `webapp_frontend/src` — Vite hot-reloads. Backend code changes need a
restart: `bash scripts/local_preview.sh` (re-runs the container; add `--build` if you
changed Python deps / backend source baked into the image).

## Teardown

```bash
bash scripts/local_preview.sh --stop     # stop & remove the backend container
bash scripts/local_preview.sh --logs     # tail backend logs
```

## Caveats

- The backend talks to the **real prod DB** by default — check-ins/edits/deletes are
  **real**. Use `PREVIEW_DB=staging` to be safe.
- Only the env needed for the dashboard is passed to the container. LLM/Qdrant-backed
  admin pages need more env — add `--env-file .env` to the `docker run` in the script.
- `Dockerfile.webapp` bakes backend source into the image, so backend edits require a
  `--build`. The frontend is NOT taken from the image here (Vite serves it live).
