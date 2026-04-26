# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Xaana (ZanaAI) is a Telegram bot + Mini App for goal/promise accountability. It runs as a Docker container on a GCP VM (`34.163.204.33`, domain `xaana.club`). The bot handles NLP-driven promise tracking via `python-telegram-bot`, while the web layer serves a React SPA via FastAPI/uvicorn.

## Architecture

```
tm_bot/
  planner_bot.py       # Core bot class — message routing and orchestration
  run_bot.py           # Entry point (ENTRYPOINT in Dockerfile)
  handlers/            # Telegram update handlers (message, callback, base)
  repositories/        # Data access layer — one file per domain entity
  services/            # Business logic (reminders, clubs, etc.)
  db/
    postgres_db.py     # SQLAlchemy connection (reads DATABASE_URL_PROD/STAGING)
    alembic/           # Schema migrations (versions/001–018+)
    alembic.ini        # script_location = tm_bot/db/alembic (relative to /app)
  webapp/
    routers/           # FastAPI route modules (admin.py, user.py, etc.)
    schemas.py         # Pydantic request/response models
    auth.py            # Telegram initData HMAC validation
  platforms/           # Platform abstraction layer
    testing/           # MockPlatformAdapter, CLIPlatformAdapter for tests
  llms/                # Claude API integration
  models/models.py     # Domain dataclasses / UserSettings

webapp_frontend/       # React + Vite SPA (built into dist/, served by FastAPI)
stats_service/         # Separate service (port 8000)
```

**Key wiring:** `planner_bot.py` wires handlers to a platform adapter. In production the adapter is the real `python-telegram-bot` integration; in tests it is `MockPlatformAdapter`. Repositories all use `get_db_session()` from `postgres_db.py` — never raw connections.

**Database:** PostgreSQL (Neon/Supabase). Environment selects which URL: `DATABASE_URL_PROD` (when `ENVIRONMENT=production`) or `DATABASE_URL_STAGING`. Alembic handles all schema changes.

## Common Commands

### Running Tests

```bash
# All tests (from zana_planner/)
pytest

# Single test file
pytest tm_bot/tests/test_platform_abstraction.py -v

# By marker
pytest -m unit
pytest -m "not e2e"   # skip tests needing secrets/remote

# Interactive CLI test (no Telegram needed)
python -m tm_bot.platforms.testing.cli_test
```

### Local Development (WSL)

```bash
# Build image
cd /mnt/e/workspace/ZanaAI/zana_planner
docker build -t zana-ai-bot:local .

# Run with live code mount (bot auto-starts)
docker run -d --name zana-local \
  -v $(pwd)/USERS_DATA_DIR:/app/USERS_DATA_DIR:rw \
  -v $(pwd)/tm_bot:/app/tm_bot:ro \
  -v $(pwd)/tests:/app/tests:ro \
  -v $(pwd)/.env:/app/.env:ro \
  zana-ai-bot:local

# Or run without auto-start (manual control)
docker run -d --name zana-local --entrypoint sleep \
  -v $(pwd)/USERS_DATA_DIR:/app/USERS_DATA_DIR:rw \
  -v $(pwd)/tm_bot:/app/tm_bot:ro \
  -v $(pwd)/.env:/app/.env:ro \
  zana-ai-bot:local infinity
docker exec -it zana-local bash
# inside: python -m tm_bot.run_bot
```

### Frontend Development

```bash
cd webapp_frontend
npm install
npm run dev    # dev server at :5173, proxies API to :8080
npm run build  # output to webapp_frontend/dist/
```

### Production Deployment (on server)

```bash
cd /opt/zana-bot/zana_planner

# Quick redeploy (build frontend + Docker + restart)
bash scripts/deploy_webapp_quick.sh

# Full first-time deploy (includes SSL, nginx, firewall)
bash scripts/deploy_webapp.sh xaana.club your@email.com
```

### Database Migrations

Alembic **must** be run from `/app` (inside container) so the relative `script_location` resolves correctly:

```bash
# Apply all pending migrations to production
sudo docker exec -it zana-prod bash -c "cd /app && alembic -c tm_bot/db/alembic.ini upgrade head"

# Or via docker compose run (container need not be running)
sudo docker compose run --rm --entrypoint python zana-prod \
  -m alembic -c /app/tm_bot/db/alembic.ini upgrade head
```

**Do not run `python <migration_file>.py` directly** — that does nothing (upgrade() is never called).

### Logs & Health

```bash
docker compose logs -f zana-prod
curl https://xaana.club/api/health
```

## Test Markers

| Marker | Meaning |
|--------|---------|
| `unit` | Fast, no I/O |
| `repo` | Filesystem/DB only |
| `handler` | Mocked network |
| `integration` | Multi-module, offline |
| `e2e` | Requires secrets/remote |
| `requires_postgres` | Skipped without DATABASE_URL |

## Environment Variables (required)

| Variable | Where |
|----------|-------|
| `BOT_TOKEN` | `.env.prod` / `.env.staging` |
| `DATABASE_URL_PROD` | `.env.prod` |
| `DATABASE_URL_STAGING` | `.env.staging` |
| `ENVIRONMENT` | `production` or `staging` |
| `ADMIN_IDS` | Comma-separated Telegram user IDs |
| `QDRANT_URL` | Vector search service |
