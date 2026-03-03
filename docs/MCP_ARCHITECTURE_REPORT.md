# MCP-First Architecture for Xaana — Design Report

## Executive Summary

This report evaluates a proposed redesign of Xaana from its current Telegram-centric, monolithic bot architecture to an **MCP-first (Model Context Protocol-first)** architecture. It sketches the redesign plan with full awareness of Xaana's core values and functionality, and discusses the trade-offs involved.

---

## 1. Current Architecture Overview

Xaana is today a **Telegram-first AI personal planner** built around a Python monolith. Its key layers are:

| Layer | Key Components | Role |
|---|---|---|
| **Platform** | `TelegramPlatformAdapter`, `planner_bot.py` | Receives updates from Telegram; routes to handlers |
| **Handlers** | `message_handlers.py`, `callback_handlers.py` | Parse input, coordinate translation, format output |
| **LLM Agent** | `llm_handler.py`, `agent.py` (LangGraph plan-execute graph) | Drive multi-step reasoning; call tools |
| **Tools / API** | `PlannerAPIAdapter` + `tool_wrappers.py` | Expose business-logic operations to the LLM as callable tools |
| **Services** | `reports.py`, `ranking.py`, `reminders.py`, `content_service.py`, … | Business logic (reports, rankings, reminders, content) |
| **Repositories** | `promises_repo.py`, `actions_repo.py`, `settings_repo.py`, … | Data access (PostgreSQL via SQLAlchemy) |
| **Memory** | `memory/read.py`, `memory/write.py`, `memory/search.py` | Per-user persistent and vector-searchable memory |
| **Web App** | `webapp/api.py` + React front-end | Telegram Mini App / stats dashboard |
| **Stats Service** | `stats_service/stats_service.py` | Read-only analytics endpoint |

The LLM agent uses a **Planner → Executor** pattern (LangGraph). The Planner produces a structured JSON plan; the Executor runs each step, calling `PlannerAPIAdapter` methods that are registered as LangChain-compatible tools.

### Core Values and Differentiators
- **Personal accountability**: promises + weekly commitment tracking
- **Conversational UX**: natural language via Telegram
- **Multi-lingual**: Google Translate layer post-LLM
- **Voice-first option**: voice transcription and TTS
- **Privacy by design**: per-user isolated data directories and IDs
- **Lightweight infrastructure**: SQLite/PostgreSQL + Docker on a single server

---

## 2. What Is MCP?

The **Model Context Protocol (MCP)**, introduced by Anthropic, is an open standard for connecting LLM-based applications to external tools and data sources using a uniform client-server protocol. In an MCP architecture:

- **MCP Servers** expose *resources* (read), *tools* (write/call), and *prompts* (templated instructions) over a JSON-RPC 2.0 transport (stdio, HTTP/SSE, or WebSocket).
- **MCP Clients** (AI hosts like Claude Desktop, LLM agents, or custom runners) discover and call those capabilities at runtime.
- The LLM chooses which server and tool to invoke; the host mediates the call.

### MCP-First vs. Current Approach

| Aspect | Current | MCP-First |
|---|---|---|
| Tool binding | `tool_wrappers.py` wraps `PlannerAPIAdapter` methods into LangChain tools, tightly coupled to LangGraph | Each capability is an independently deployable MCP server |
| LLM framework | LangGraph plan-execute graph | Any MCP-compatible host (Claude, GPT-4o, custom agent loop) |
| Transport | In-process Python function calls | JSON-RPC 2.0 over stdio/HTTP |
| Discovery | Hard-coded tool list registered at startup | Dynamic: hosts query `tools/list` at runtime |
| Platform coupling | Telegram-specific adapter wraps everything | Platform adapter remains; LLM layer becomes protocol-neutral |

---

## 3. Proposed MCP-First Architecture Sketch

### 3.1 High-Level Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                       Platform Layer                             │
│  Telegram Adapter │ Discord Adapter │ Web API │ CLI Adapter      │
└────────────┬─────────────────────────────────────────────────────┘
             │  Natural-language message + user context
             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    MCP Host / Agent Runner                        │
│  • Receives user message                                          │
│  • Loads MCP server registry for this user                        │
│  • Sends message + available tools to LLM                         │
│  • Executes tool calls returned by LLM via MCP clients            │
│  • Streams / returns final response to platform layer             │
└────────────┬─────────────────────────────────────────────────────┘
             │  MCP JSON-RPC calls
   ┌──────────┼──────────────────────────────────────────┐
   ▼          ▼                    ▼                     ▼
┌──────┐  ┌──────────┐  ┌────────────────────┐  ┌────────────────┐
│Planner│  │ Memory   │  │  Content / Learning│  │ Social / Club  │
│ MCP  │  │  MCP     │  │      MCP Server    │  │   MCP Server   │
│Server│  │ Server   │  │                    │  │                │
└──┬───┘  └────┬─────┘  └─────────┬──────────┘  └───────┬────────┘
   │           │                  │                      │
   ▼           ▼                  ▼                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Data / Infrastructure Layer                   │
│  PostgreSQL  │  Qdrant (vector)  │  GCP (Vertex AI / TTS)        │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 Proposed MCP Servers

#### `xaana-planner-mcp`
The core planner server — maps directly from today's `PlannerAPIAdapter`.

**Tools exposed:**
- `add_promise`, `get_promises`, `update_promise`, `delete_promise`
- `log_action`, `get_actions`, `delete_action`
- `get_weekly_report`, `get_ranking`, `get_nightly_reminders`
- `set_timezone`, `set_language`, `get_settings`
- `resolve_datetime`, `search_promises`
- `get_plan_by_zana` (AI planning suggestion)

**Resources exposed:**
- `promises://{user_id}` — list of active promises
- `actions://{user_id}/{date_range}` — time-log entries
- `report://{user_id}/weekly` — current week summary

#### `xaana-memory-mcp`
Wraps today's `memory/` module.

**Tools exposed:**
- `memory_write`, `memory_read`, `memory_search`
- `memory_flush` (pre-compaction)

**Resources exposed:**
- `memory://{user_id}/active` — current MEMORY.md content
- `memory://{user_id}/archive/{date}` — historical flush files

#### `xaana-content-mcp`
Wraps `ContentService` and the learning pipeline.

**Tools exposed:**
- `process_link`, `get_content_progress`, `summarize_content`
- `search_knowledge_base`

**Resources exposed:**
- `content://{user_id}/queue` — unread content items

#### `xaana-social-mcp`
Wraps `SocialService` and club/follows functionality.

**Tools exposed:**
- `follow_user`, `unfollow_user`, `get_leaderboard`
- `get_club_stats`

**Resources exposed:**
- `social://{user_id}/follows`
- `social://leaderboard`

#### `xaana-voice-mcp` *(optional, progressive)*
Wraps `VoiceService` and `GCPTTSService`.

**Tools exposed:**
- `transcribe_audio`, `synthesize_speech`

### 3.3 MCP Host / Agent Runner

Replace the current `LLMHandler` + LangGraph agent with a **thin MCP host** that:
1. Accepts a message and user context from the platform adapter.
2. Calls `tools/list` on all registered MCP servers for that user.
3. Sends the message plus the tool manifest to the LLM.
4. Forwards any `tools/call` requests from the LLM to the correct MCP server.
5. Iterates until the LLM produces a final response.
6. Returns the response to the platform adapter.

This can be implemented with an existing MCP client library (e.g., the official `mcp` Python SDK, or `langchain-mcp-adapters`) so the host itself stays small.

### 3.4 Platform Layer (Unchanged in Shape)

The existing `IPlatformAdapter` abstraction (`platforms/interfaces.py`) already decouples Telegram from the bot logic. Under MCP-first, the platform adapters call the **MCP host** instead of `LLMHandler` directly — a one-line swap.

### 3.5 Authentication and User Context

Each MCP tool call must carry a `user_id`. Today this is enforced by `_sanitize_user_id` and `ContextVar` in `tool_wrappers.py`. In an MCP architecture this becomes an **HTTP header** or a signed **session token** passed in the JSON-RPC request metadata, validated server-side before any database operation.

---

## 4. Pros of MCP-First Architecture

### 4.1 Framework Independence
Today the agent is tightly coupled to LangGraph and LangChain's tool format. MCP-first makes the tool layer consumable by any MCP-compatible LLM host — Claude Desktop, OpenAI Assistants API (via adapter), or a future in-house runner — without changing server code.

### 4.2 Independent Deployability and Scalability
Each MCP server is a separate process that can be:
- Scaled independently (e.g., `xaana-planner-mcp` is CPU-bound; `xaana-content-mcp` is I/O-bound).
- Deployed on different hardware tiers.
- Restarted or updated without touching the rest of the system.

### 4.3 Interoperability and Ecosystem
MCP is gaining adoption across Anthropic, OpenAI, Google DeepMind, and IDE vendors (Cursor, VS Code). Xaana's tools become reusable in:
- Claude Desktop (users can chat with their planner from the desktop app).
- Custom developer setups.
- Future third-party integrations.

### 4.4 Cleaner Separation of Concerns
The current codebase mixes LLM orchestration, tool execution, platform handling, and business logic in a chain of adapters. MCP forces explicit API boundaries at each server boundary, which improves testability, documentation, and on-boarding time.

### 4.5 Improved Observability
JSON-RPC is trivially loggable. Every tool call and result is a structured log entry, making it straightforward to add distributed tracing, latency dashboards, and audit logs — today these require custom instrumentation inside `tool_wrappers.py`.

### 4.6 Multi-Client Support Without Duplication
A single `xaana-planner-mcp` server can be called by:
- The Telegram bot agent runner.
- The web Mini App back-end.
- The stats service.
- A developer's personal Claude client.

This eliminates the current duplication between `webapp/api.py` and `PlannerAPIAdapter`.

---

## 5. Cons and Risks of MCP-First Architecture

### 5.1 Significant Refactoring Cost
The entire `PlannerAPIAdapter` + `tool_wrappers.py` + LangGraph agent loop must be rewritten or re-wrapped. Estimated effort: **3–5 weeks** for a single engineer to migrate core planner tools, validate parity, and migrate tests.

### 5.2 Latency Overhead
In-process function calls (current) are microseconds. JSON-RPC over localhost HTTP adds ~1–5 ms per hop; over the network, 5–50 ms. With multiple tool calls per user turn, this adds up. The plan-execute pattern already averages 3–5 tool calls per response; each becomes a network round-trip.

*Mitigation*: Run MCP servers on localhost / Unix sockets for co-located deployment; HTTP-SSE streaming can mask latency for the user.

### 5.3 Operational Complexity
Running five MCP servers alongside the bot process, the web API, and the stats service increases the number of processes to manage in Docker Compose. Healthchecks, restart policies, log aggregation, and secret distribution all multiply.

*Mitigation*: Start with a single `xaana-planner-mcp` server; add others incrementally.

### 5.4 Authentication and Multi-Tenancy Complexity
MCP's current specification does not define a standard multi-tenant authentication model. Passing `user_id` securely across process boundaries requires designing and maintaining a session/token mechanism that today is handled implicitly by `ContextVar`.

### 5.5 Protocol Immaturity
MCP is less than two years old. The spec has evolved rapidly (Streamable HTTP transport added in 2025-03-26). Libraries and tooling are still maturing. Breaking changes in the spec could require migration work.

### 5.6 Debugging Becomes Harder
The current monolith allows `print`/`pdb`-level debugging of a full request in one process. With MCP, a single user turn spans multiple processes; reproducing bugs requires distributed tracing from day one.

### 5.7 Minimal Benefit for Single-User / Low-Traffic Deployments
Xaana currently runs on a single server for a small user base. The scalability benefits of MCP are not realized at this scale, while the operational overhead is immediate.

---

## 6. Recommended Transition Strategy

Rather than a full rewrite, a **gradual MCP adoption** approach is recommended:

| Phase | Action | Effort |
|---|---|---|
| **Phase 1** | Wrap `PlannerAPIAdapter` as a single MCP server (`xaana-planner-mcp`), called via stdio from the existing LangGraph agent using `langchain-mcp-adapters`. No change to the agent or platform layer. | 1 week |
| **Phase 2** | Replace the LangGraph agent with a thin MCP host. Keep platform adapters unchanged. | 1–2 weeks |
| **Phase 3** | Extract `memory/` into `xaana-memory-mcp`. Publish to MCP registry. | 1 week |
| **Phase 4** | Extract remaining services (content, social, voice) into dedicated MCP servers. | 2–3 weeks |
| **Phase 5** | Publish `xaana-planner-mcp` as a standalone installable server for Claude Desktop / VS Code users. | 1 week |

Each phase is independently valuable and can be paused without regressing the system.

---

## 7. Conclusion

An MCP-first architecture for Xaana is **architecturally sound and strategically valuable**: it aligns with the direction of the AI tooling ecosystem, eliminates framework lock-in, and opens Xaana's capabilities to users beyond Telegram. The existing platform-abstraction layer (`IPlatformAdapter`) and the clean service/repository split already provide a solid foundation for the transition.

However, the **immediate cost is non-trivial** for a single-engineer project at the current scale. The recommendation is to pursue a phased migration starting with Phase 1 (MCP wrapper over `PlannerAPIAdapter`), which delivers interoperability with minimal disruption, and progress through subsequent phases as user growth justifies the added operational complexity.

> **Decision gate**: adopt MCP-first fully once Xaana reaches a user base or partner ecosystem where external tool access (Claude Desktop, IDE plugins, third-party clients) provides measurable user value.
