# 🧭 Zana Planner — Development Roadmap

## ✅ Phase 1 — Core Infrastructure

* [x] Telegram bot with conversation + job queue
* [x] CSV → **MongoDB** migration using Motor (async)
* [x] CRUD for `Promise`, `Action`, `Session`, `UserSettings`
* [x] Automatic index management (safe & idempotent)
* [x] Basic encryption / hashing placeholders (Fernet + Argon2)
* [ ] ⚠️ **Integrate `DataManager` with the rest of the bot logic**

  * Currently implemented but **not yet wired** into command handlers, jobs, or conversation flow.
  * Need to replace file-based reads/writes with `DataManager` calls.

---

## 🚧 Phase 2 — Data & Storage Improvements

* [ ] **Encrypt / hash sensitive data**

  * Use Fernet (`DATA_ENC_KEY`) for reversible fields (Telegram IDs, messages).
  * Use Argon2 for irreversible identifiers (emails, usernames).
* [ ] **Backup & Export system**

  * Command to export user data (JSON, ZIP).
* [ ] **Add metadata layer** (per user, per action) for analytics.
* [ ] **Migrate old CSV users** automatically to MongoDB schema.

---

## 🌍 Phase 3 — User Experience

* [ ] **Multilingual support**

  * Ask user preferred language on `/start`.
  * Use LLM or context-aware translator for all text prompts.
* [ ] **Time zone detection**

  * Ask user for city or share location → auto infer timezone.
* [ ] **Voice + image input**

  * Integrate Whisper (ASR) for speech-to-text.
  * Add lightweight image analysis for OCR or context extraction.
* [ ] **Improved reminders**

  * Smarter scheduling (based on activity patterns).
  * Pre-task “start/snooze” + live timers.

---

## 💬 Phase 4 — Conversation & AI Layer

* [ ] Refine LLM call prompts to prevent unintended API triggers in group chats.
* [ ] Abstract the LLM conversation layer to support multiple front-ends (Telegram, Web, WhatsApp).
* [ ] Add contextual “intent detection” to reduce false positives.
* [ ] Create conversation state machine independent of UI layer.

---

## 📊 Phase 5 — Visualization & Sharing

* [ ] **Charts & stats**

  * Weekly activity plots, streak counters, category distributions.
* [ ] **Achievement sharing**

  * Share success cards or progress messages in groups (“👏 X just completed 3h of French practice!”).
* [ ] **User summary dashboard**

  * Visual analytics for personal progress (web interface).

---

## 🧠 Phase 6 — Admin & Monitoring

* [ ] **Admin panel**

  * Monitor user growth and activity.
  * Trigger bulk messages or updates.
  * Export anonymized usage stats.
* [ ] **Analytics script** (headless)

  * Scan MongoDB for:

    * Total users
    * Users with at least one promise
    * Recent activity (last week / month)
  * Send reports via a separate manager bot.

---

## 🔬 Phase 7 — Architecture Refactor

* [ ] Split into modular layers:

  * `core/` (models, logic, ranking, scheduling)
  * `platforms/telegram`, `platforms/web`, `platforms/whatsapp`
  * `llms/` (LangChain integration)
  * `repositories/` (MongoDB, file adapters)
* [ ] Support running planner engine standalone (no Telegram).
* [ ] Add test coverage and typing across modules.

---

## 🧩 Optional Future Add-ons

* [ ] Integrate CalDAV / Google Calendar sync.
* [ ] Lightweight WebApp (React/Vue) for desktop/mobile.
* [ ] Offline-first local cache for user data.
* [ ] Add open API for third-party integrations.

---
