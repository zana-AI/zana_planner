# 🧭 Zana Planner — AI Implementation

This repository contains the **ZanaAI Planner Bot**, a Telegram-based AI assistant for task management, habit tracking, and personal organization.

> [!NOTE]
> This README is the **single source of truth** for the project's status, setup, and roadmap.

---

## 🏃 Getting Started

### Prerequisites
*   Docker & Docker Compose
*   Access to GCP (for Vertex AI credentials)
*   Telegram Bot Token

### 🐳 Docker Setup

The project uses Docker for distinct environments (Production, Staging, Stats).

```bash
# 1. Check status of all containers
docker compose ps

# 2. View logs for a specific service (e.g., prod bot)
docker compose logs -f zana-prod

# 3. Update code and rebuild
cd /opt/zana-bot
git pull
docker compose build
docker compose up -d
```

### 🤖 Bot Commands

The bot supports the following commands:

- `/nightly` - Send nightly reminders
- `/weekly` - Report of the current week
- `/promises` - List all my promises
- `/zana` - What should I do today?

[//]: # (- `/pomodoro` - Start a pomodoro session)
- `/broadcast` - (Admin only) Schedule broadcast messages to all users

### 🔐 Environment Variables

Required environment variables:

- `BOT_TOKEN` - Telegram bot token
- `ROOT_DIR` - Root directory for user data
- `ADMIN_IDS` - Comma-separated list of Telegram user IDs with admin access (e.g., `123456789,987654321`)

Optional (memory and pre-compaction flush):

- `MEMORY_VECTOR_DB_URL` – Leave unset until a vector DB is set up; when set, `memory_search` uses it for semantic search. Until then, memory search returns a disabled payload.
- `MEMORY_FLUSH_ENABLED` – Set to `1` to enable pre-compaction flush (writes durable memories to `memory/YYYY-MM-DD.md` per user when the session is near context limit). Can be used even before a vector DB.
- Memory files live **per user** at `ROOT_DIR/users/<user_id>/MEMORY.md` and `ROOT_DIR/users/<user_id>/memory/` (e.g. `memory/2025-02-19.md`).

Optional (Telegram-triggered production promotion):

- `GITHUB_DEPLOY_REPOSITORY` - GitHub repository in `owner/repo` format.
- `GITHUB_DEPLOY_TOKEN` - GitHub token with permission to dispatch workflows.
- `GITHUB_DEPLOY_WORKFLOW` - Workflow file name to dispatch (default: `deploy-prod.yml`).
- `GITHUB_DEPLOY_REF` - Branch ref used for dispatch (default: `master`).

### 📂 Directory Structure

Optional (content-to-learning pipeline):

- `CONTENT_LEARNING_PIPELINE_ENABLED` - Set to `1` to enable background content analysis jobs.
- `QDRANT_URL` - Qdrant base URL (for example `http://qdrant:6333` in Docker Compose).
- `QDRANT_API_KEY` - Optional API key for secured Qdrant deployments.
- `QDRANT_COLLECTION` - Vector collection name (default: `content_chunks_v1`).
- `VERTEX_EMBEDDING_MODEL` - Embedding model (default: `gemini-embedding-001`).
- `GROQ_API_KEY` - API key for Groq provider access.
- Groq provider/model/fallback/base-url defaults are code-owned; only `GROQ_API_KEY` is required in env for normal use.
- `LLM_FALLBACK_ENABLED` and `LLM_FALLBACK_PROVIDER` are advanced overrides (optional).

The codebase has been refactored into a clean, layered architecture:

*   `tm_bot/` — Main package
    *   `handlers/` — Telegram message & callback handlers
    *   `services/` — Business logic (Sessions, Ranking, Reports)
    *   `repositories/` — Data access layer (CSV/JSON/YAML adapters)
    *   `models/` — Data models & Enums
    *   `ui/` — Pure functions for Messages & Keyboards
    *   `i18n/` — Internationalization & Translations
    *   `infra/` — Infrastructure & Scheduling


## �️ Database Migrations

Migrate both **production** and **staging** PostgreSQL databases in a single command.

The script reads credentials from the server's env files automatically:
- Production env file → `DATABASE_URL_PROD`
- Staging env file → `DATABASE_URL_STAGING`

```bash
# Migrate both DBs (default)
sudo python3 scripts/run_migrations.py

# Prod only
sudo python3 scripts/run_migrations.py --prod

# Staging only
sudo python3 scripts/run_migrations.py --staging
```

To override env-file paths:
```bash
ZANA_ENV_PROD=/custom/.env.prod ZANA_ENV_STAGING=/custom/.env.staging \
    sudo -E python3 scripts/run_migrations.py
```

After running, the script prints a table of row counts per table and a ✓/✗ summary per database.

---

## �💡 Resolution Suggestions & Future Ideas (2026)

| Idea | Priority | Est. Time |
| :--- | :--- | :--- |
| **Agentic Capabilities** | High | 10h |
| **RAG / Conversation History** | High | 20h |
| **Telegram Mini App** | Med | 20h |
| **Offline-first Local Cache** | Low | - |
| **External Calendar Sync** | Med | 6h |
