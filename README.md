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
- `/pomodoro` - Start a pomodoro session
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

---

## 📝 Active Sprint — Concrete TODO List

This list contains high-priority implementation tasks. Each item is linked to a specific file and issue.

### 🛑 Critical Fixes (High Priority)

- [x] **Fix Import Path in `planner_api_adapter.py`** ✅ **DONE**
    - **File**: `tm_bot/services/planner_api_adapter.py:275`
    - **Status**: Already fixed - uses `from llms.schema import UserAction`

- [ ] **Connect Nightly Reminders**
    - **File**: `tm_bot/handlers/message_handlers.py` (Lines 363, 370)
    - **Issue**: Methods are empty placeholders.
    - **Fix**: Connect to `handlers/callback_handlers.py` logic or `services/reminders.py`.

### 🚧 Feature Completion (Medium Priority)

- [ ] **Implement Session Ticker System**
    - **File**: `tm_bot/handlers/callback_handlers.py` (Lines 106-119)
    - **Task**: Implement `_schedule_session_ticker`, `_stop_ticker`, and `_schedule_session_resume` for real-time pinned message updates.
    - **Status**: Currently TODO placeholders

- [x] **Implement Session Time Calculation** ✅ **DONE**
    - **File**: `tm_bot/services/sessions.py` (Lines 73-74)
    - **Status**: Properly calculates `(now - started_at).total_seconds() - paused_seconds_total`

- [x] **Implement Weekly Report Refresh** ✅ **DONE**
    - **File**: `tm_bot/handlers/callback_handlers.py` (Lines 763-782)
    - **Status**: Fully implemented with report regeneration

- [ ] **User Language Persistence**
    - **File**: `tm_bot/handlers/messages_store.py` (Line 237)
    - **Issue**: `get_user_language(user: User)` uses Telegram's `language_code` instead of `SettingsRepository`
    - **Fix**: Update to use `_translation_manager.get_user_language(user.id)` which already uses SettingsRepository

### 🧩 Nice-to-Have (Low Priority)

- [ ] **Session Recovery on Startup**: Handle interrupted sessions in `services/sessions.py`.
- [ ] **Timer Display**: Show live timer in `ui/keyboards.py`.
- [ ] **Chat History**: Enable system messages context in `llms/llm_handler.py`.

---

## 📍 Current Status: Refactoring Complete

The monolithic `planner_bot.py` has been successfully refactored.

*   ✅ **Separation of Concerns**: UI, Logic, and Data are now separate.
*   ✅ **Repository Pattern**: All file I/O is isolated in `repositories/`.
*   ✅ **Internationalization**: Setup ready for multiple languages.
*   ✅ **Dependency Management**: Pandas and YAML are now optional dependencies.

---

## 🗺️ Project Roadmap

### ✅ Phase 1 — Core Infrastructure
*   [x] Telegram bot with conversation + job queue
*   [x] CSV → **MongoDB** migration (Ready via Repositories)
*   [x] CRUD for `Promise`, `Action`, `Session`, `UserSettings`
*   [x] Automatic index management
*   [x] **Integrate `DataManager` logic completely** (Need to ensure all old file-reads are gone)

### 🚧 Phase 2 — Data & Storage
*   [ ] **Encrypt / hash sensitive data** (Fernet + Argon2)
*   [ ] **Backup & Export system** (JSON/ZIP export command)
*   [x] **Migrate old CSV users** to new Schema completely

### 🌍 Phase 3 — User Experience
*   [x] **Multilingual support** (Skeleton ready, need implementation)
*   [ ] **Time zone detection** (Auto-infer from location)
*   [x] **Voice + Image Input** (Whisper + Vision API)
*   [ ] **Smarter Reminders** (Context-aware based on activity)

### 📊 Phase 4 — Visualization & Sharing
*   [ ] **Charts & Stats** (Weekly activity plots)
*   [ ] **Achievement Sharing** (Social proof cards)
*   [ ] **Web Dashboard** (React/Vue frontend for analytics)

### 🧠 Phase 5 — Admin & Operations
*   [ ] **Admin Panel** (User monitoring, broadcasts)
*   [ ] **Analytics Script** (Headless stats collection)
*   [x] **CI/CD** (push github -> build docker -> deploy on GCP) 
*   [ ] Testing** (Automated tests)

---

## 💡 Resolution Suggestions & Future Ideas (2026)

| Idea | Priority | Est. Time |
| :--- | :--- | :--- |
| **Agentic Capabilities** | High | 10h |
| **RAG / Conversation History** | High | 20h |
| **Telegram Mini App** | Med | 20h |
| **Offline-first Local Cache** | Low | - |
| **External Calendar Sync** | Med | 6h |
