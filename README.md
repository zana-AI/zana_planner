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

### 📂 Directory Structure

The codebase has been refactored into a clean, layered architecture:

*   `tm_bot/` — Main package
    *   `handlers/` — Telegram message & callback handlers
    *   `services/` — Business logic (Sessions, Ranking, Reports)
    *   `repositories/` — Data access layer (CSV/JSON/YAML adapters)
    *   `models/` — Data models & Enums
    *   `ui/` — Pure functions for Messages & Keyboards
    *   `i18n/` — Internationalization & Translations
    *   `infra/` — Infrastructure & Scheduling


## 💡 Resolution Suggestions & Future Ideas (2026)

| Idea | Priority | Est. Time |
| :--- | :--- | :--- |
| **Agentic Capabilities** | High | 10h |
| **RAG / Conversation History** | High | 20h |
| **Telegram Mini App** | Med | 20h |
| **Offline-first Local Cache** | Low | - |
| **External Calendar Sync** | Med | 6h |
