# Zana Planner — Design B (Layered Refactor Plan)

**Goal:** make `planner_bot.py` thin (Telegram glue only), move business logic into testable services, and isolate data I/O. Enable upcoming features: smart top-3 reminders, start-of-task pre-pings + timers, per-user timezone, and habit patterns.

## 0) Context (what the bot does)

* Personal planning bot on Telegram.
* Stores per-user data under `USERS_DATA_DIR/<user_id>/`:

  * `promises.csv` (user’s “promises” / tasks with weekly targets)
  * `actions.csv` (time logs and other actions)
  * `settings.yaml` (user preferences: timezone, etc.)
* Nightly reminders + weekly report. (We’ll add pre-pings/timers.)

---

## 1) Target folder layout

```
zana_planner/
  tm_bot/
    planner_bot.py              # controller: handlers & callbacks → call services
    cbdata.py                   # callback encode/decode (a=...&p=...&v=...)
    infra/
      scheduler.py              # JobQueue helpers (run_once/daily/repeating)
      logging_conf.py           # consistent logger factory (optional)
    schema/
      models.py                 # dataclasses: Promise, Action, Session, UserSettings
      enums.py                  # small Enums (ActionType, SessionStatus, Weekday)
    repositories/
      promises_repo.py          # CSV adapter for promises
      actions_repo.py           # CSV adapter for actions
      sessions_repo.py          # CSV adapter for sessions (new)
      settings_repo.py          # YAML adapter for user settings
    services/
      reminders.py              # nightly & pre-pings; select top-N
      ranking.py                # scoring signals & weights (rule-based first)
      sessions.py               # start/pause/resume/finish + nightly catch-up
      reports.py                # weekly report data aggregation
    ui/
      keyboards.py              # InlineKeyboard builders (pure functions)
      messages.py               # message text builders (pure functions)
    utils/
      time_utils.py             # beautify_time, round_time, get_week_range
      pd_utils.py               # small pandas helpers (optional)
```

> Cursor: create missing files/folders as above; do **incremental** edits.

---

## 2) Data models (schema/models.py)

```python
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional

@dataclass
class Promise:
    id: str
    text: str
    hours_per_week: float
    recurring: bool = False
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    # Optional viz fields (keep if already present in CSVs)
    angle_deg: int = 0
    radius: Optional[int] = 0
    # Future: pinned/focus flags, tags

@dataclass
class Action:
    user_id: int
    promise_id: str
    action: str           # e.g., "log_time", "skip", "delete", etc.
    time_spent: float     # hours (can be 0 for skip/delete)
    at: datetime          # action timestamp

@dataclass
class UserSettings:
    user_id: int
    timezone: str = "Europe/Paris"
    nightly_hh: int = 22
    nightly_mm: int = 0

@dataclass
class Session:
    session_id: str
    user_id: int
    promise_id: str
    status: str              # "running" | "paused" | "finished" | "aborted"
    started_at: datetime
    ended_at: Optional[datetime] = None
    paused_seconds_total: int = 0
    last_state_change_at: Optional[datetime] = None
    message_id: Optional[int] = None
    chat_id: Optional[int] = None
```

### CSV/YAML expectations

* **promises.csv**: `id,text,hours_per_week,recurring,start_date,end_date,angle_deg,radius`
* **actions.csv**: `user_id,promise_id,action,time_spent,at`
* **sessions.csv (new)**: `session_id,user_id,promise_id,status,started_at,ended_at,paused_seconds_total,last_state_change_at,message_id,chat_id`
* **settings.yaml**: keys `timezone`, `nightly_hh`, `nightly_mm`

> Cursor: when reading/writing, tolerate missing optional columns and cast types safely.

---

## 3) Repositories (CSV/YAML adapters)

**Promised APIs** (synchronous; keep pandas under the hood):

* `promises_repo.py`

  * `list_promises(user_id) -> list[Promise]`
  * `get_promise(user_id, promise_id) -> Optional[Promise]`
  * `upsert_promise(user_id, promise: Promise) -> None`
  * `delete_promise(user_id, promise_id) -> None`

* `actions_repo.py`

  * `append_action(action: Action) -> None`
  * `list_actions(user_id, since: Optional[datetime] = None) -> list[Action]`
  * `last_action_for_promise(user_id, promise_id) -> Optional[Action]`

* `sessions_repo.py` (new)

  * `create_session(sess: Session) -> None`
  * `update_session(sess: Session) -> None`
  * `get_session(user_id, session_id) -> Optional[Session]`
  * `list_active_sessions(user_id) -> list[Session]`

* `settings_repo.py`

  * `get_settings(user_id) -> UserSettings`
  * `save_settings(settings: UserSettings) -> None`

> Cursor: move any direct CSV/YAML I/O out of `planner_bot.py` into these repos. Keep paths under `USERS_DATA_DIR/<user_id>/…`. Create files with headers if missing.

---

## 4) Services

### 4.1 sessions.py (timers & lifecycle)

```python
class SessionsService:
    def __init__(self, sessions_repo, actions_repo):
        self.sessions_repo = sessions_repo
        self.actions_repo = actions_repo

    def start(self, user_id: int, promise_id: str) -> Session: ...
    def pause(self, user_id: int, session_id: str) -> Session: ...
    def resume(self, user_id: int, session_id: str) -> Session: ...
    def finish(self, user_id: int, session_id: str, override_hours: float | None = None) -> Action:
        # compute elapsed - paused, or use override_hours; append Action("log_time")
        ...
    def abort(self, user_id: int, session_id: str) -> None: ...
    def recover_on_startup(self, user_id: int) -> list[Session]: ...
```

* **Nightly catch-up**: find `running|paused` sessions started earlier that day; propose logging with computed hours.

### 4.2 ranking.py (rule-based top-N)

```python
class RankingService:
    def __init__(self, promises_repo, actions_repo, settings_repo):
        ...

    def score_promises_for_today(self, user_id: int, now: datetime) -> list[tuple[Promise, float]]:
        """
        Signals (transparent):
        - weekly_deficit: behind target this week (↑)
        - recency_decay: not touched in N days (↑)
        - touched_today: small penalty (↓)
        - pinned/focus (when added later): boost
        - day_of_week fit (optional): small boost
        """

    def top_n(self, user_id: int, now: datetime, n: int = 3) -> list[Promise]:
        scores = self.score_promises_for_today(user_id, now)
        return [p for p, _ in sorted(scores, key=lambda t: t[1], reverse=True)[:n]]
```

> Start simple; weights hardcoded. Future: learn from history.

### 4.3 reminders.py (nightly & pre-pings)

```python
class RemindersService:
    def __init__(self, ranking: RankingService, settings_repo):
        ...

    def select_nightly_top(self, user_id: int, now: datetime, n=3) -> list[Promise]:
        # exclude inactive, one-offs completed, and already logged today
        return self.ranking.top_n(user_id, now, n)

    def compute_prepings(self, user_id: int, now: datetime) -> list[tuple[Promise, datetime]]:
        # use patterns (later); for now: none or fixed windows
        return []
```

### 4.4 reports.py (weekly)

* Provide a `get_weekly_summary(user_id, ref_time)` returning totals per promise and a date range; UI layer renders it.

---

## 5) UI (pure builders)

* `ui/messages.py`: functions that return plain text strings.

  * `nightly_card_text(user_id, promises, now) -> str`
  * `session_status_text(session, elapsed_str) -> str`
  * `weekly_report_text(summary) -> str`

* `ui/keyboards.py`: functions that return `InlineKeyboardMarkup`.

  * `nightly_card_kb(promises_top3, has_more: bool)`
  * `session_controls_kb(session_running: bool)`
  * `weekly_report_kb(ref_time)`

> Explicitly **no** I/O here. Make them depend only on inputs; easy to unit test.

---

## 6) Callback data format (tm\_bot/cbdata.py)

* Use URL query format `a=...&p=...&v=...` to keep under Telegram’s 64-byte limit.

```python
# encode_cb(action, pid=None, value=None) -> str
# decode_cb(data) -> {"a": str, "p": Optional[str], "v": Optional[float]}
```

Actions to support (non-exhaustive):
`time_spent`, `update_time_spent`, `remind_next_week`, `delete_promise`, `confirm_delete`, `cancel_delete`, `report_promise`, `pomodoro_start`, `pomodoro_pause`, `pomodoro_stop`, `session_start`, `session_pause`, `session_resume`, `session_finish`, `show_more`.

---

## 7) Scheduler helpers (tm\_bot/infra/scheduler.py)

Tiny wrappers around JobQueue:

```python
def schedule_user_daily(job_queue, user_id: int, tz: str, callback, hh=22, mm=0, name_prefix="nightly"):
    # (re)create a daily job named f"{name_prefix}-{user_id}" at tz-aware time

def schedule_repeating(job_queue, name: str, callback, seconds: int, data=None):
    # used for session tickers (e.g., every 5–15s)

def schedule_once(job_queue, name: str, callback, when_dt: datetime, data=None):
    # used for pre-pings and snoozes
```

---

## 8) planner\_bot.py (controller only)

* Handlers (`/start`, `/weekly`, `/nightly`, `/pomodoro` etc.) should:

  1. read `user_id`
  2. call the right **service**
  3. render text/keyboard via **ui** module
  4. send/edit messages

* Callback router:

  * decode via `cbdata.decode_cb`
  * dispatch to private methods or service calls

* No direct CSV/YAML access here.

---

## 9) Logging & errors

* One logger per layer (e.g., `planner.bot`, `planner.services.sessions`, …).
* Handlers wrapped with a small decorator to catch & log exceptions with `user_id` / `promise_id` context.
* Services raise typed exceptions (optional) that handlers map to user-facing messages.

---

## 10) Testing strategy (incremental)

* **Repositories:** unit tests using tmp dirs; ensure round-trip I/O.
* **Services:** mock repos; test ranking selection, session lifecycle math.
* **UI:** snapshot tests (strings & keyboard payloads).
* **Controller:** thin; smoke tests only (optional).

---

## 11) Migration & compatibility

* Keep existing `promises.csv`, `actions.csv`, `settings.yaml` columns; tolerate missing optional fields.
* Create `sessions.csv` on demand with the specified header.
* Maintain backward compatibility for callback payloads:

  * `cbdata.decode_cb` should also parse legacy `action:pid:value`.

---

## 12) Implementation phases for Cursor (safe order)

**Phase 1 — Scaffolding (no behavior change)**

1. Create folders/files per layout.
2. Move `beautify_time`, `round_time`, `get_week_range` into `utils/time_utils.py` (if not already).
3. Add `cbdata.py` and replace in-line parsing/formatting **only in newly touched code**.

**Phase 2 — Repositories extraction**

1. Implement `settings_repo`, `promises_repo`, `actions_repo`.
2. Change `planner_bot.py` to use repos via simple adapter functions but keep logic local.

**Phase 3 — UI split**

1. Extract message & keyboard builders for nightly/weekly into `ui/messages.py` and `ui/keyboards.py`.

**Phase 4 — Services**

1. Implement `reports.py` (weekly summary) and wire `/weekly`.
2. Implement `ranking.py` (rule-based) + `reminders.py` (top-3 nightly). Wire `/nightly`.
3. Implement `sessions_repo.py` + `sessions.py` with `start/pause/resume/finish`. Add minimal buttons to try the flow (no pre-pings yet).

**Phase 5 — Infra**

1. Add `infra/scheduler.py` and switch per-user scheduling in `/start` to use it.
2. Add session ticker jobs (5–15s) with graceful fallback if rate-limited.

**Phase 6 — Pre-pings & nightly catch-up**

1. In `reminders.py`, add `compute_prepings` (stub: none, or a fixed window).
2. On bot startup, call `SessionsService.recover_on_startup` and recreate tickers.
3. Nightly: if a session was started today but not finished, prompt to log.

---

## 13) Coding notes for Cursor

* Prefer **type hints** on public functions.
* Keep **pure functions** in UI and Ranking; no side effects.
* Reuse existing environment loading; set tz via `Defaults(tzinfo=ZoneInfo(settings.timezone))` or per job `time(..., tzinfo=...)`.
* When editing messages for timers, avoid over-refreshing: start at 5s; back off to 15–30s if exceptions (flood control).
* Keep callback payloads compact; use `cbdata.encode_cb`.

---

## 14) Acceptance criteria

* All existing commands still work (`/start`, `/nightly`, `/weekly`, `/pomodoro` minimal).
* Code compiles & runs; basic unit tests pass.
* Nightly uses **top-3** selection (not the entire list).
* Ability to start a **session** for a promise and finish it; time logged to `actions.csv`.
* Repo layer is the **only** place doing file I/O; `planner_bot.py` has no CSV/YAML code.

---
