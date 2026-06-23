# The Adapter API contract — how to evolve `PlannerAPIAdapter` safely

`tm_bot/services/planner_api_adapter.py` (`PlannerAPIAdapter`, ~67 public methods) is a
**facade** over the repository + service layers. It is not just "internal helper code" —
its public surface is consumed by **four** independent channels, two of which build their
behaviour by *reflecting over it at runtime*. That makes the adapter a **published API**:
method names, parameter names, docstrings, and return shapes are all load-bearing.

This doc records what is actually contract, the hazards that follow from it, and the
principles/mechanism for changing it without silently breaking a consumer.

## The four consumers

| Consumer | How it binds | Source |
|---|---|---|
| **Bot handlers** | Direct method calls | `tm_bot/handlers/*`, `planner_bot.py` |
| **Webapp REST routers** (React Mini App — the "other channel") | Direct method calls | `tm_bot/webapp/routers/{promises,content,youtube_watch,admin}.py` |
| **LLM agent** ("agent tool-model") | **Reflection**: `dir(adapter)` → denylist → docstring + signature → tool schema | `llms/llm_handler.py:3242` `_build_tools` |
| **MCP server** (Claude / ChatGPT connectors) | **Reflection**: `dir(adapter)` → denylist → docstring + signature → tool schema, + ChatGPT `search`/`fetch` | `tm_bot/mcp_server/tools.py:73` `register_adapter_tools` |

Both reflected surfaces share the same wrapper, `llms/tool_wrappers.py:47` `_wrap_tool`,
which strips `self`/`user_id`, derives required args from no-default params, and copies the
docstring + `__signature__` onto the model-facing tool.

## What is actually "contract" (for the reflected surfaces)

For the LLM and MCP surfaces, changing any of these changes the live tool surface that
Claude/ChatGPT see — with no compiler error:

1. **Method name** → tool name. Rename = a tool disappears and a new one appears.
2. **Public parameter names / types / defaults** (after stripping `self`/`user_id`) → tool
   input schema. **No default ⇒ required arg** (`_required_params`). Renaming `promise_id`→`pid`
   or dropping a default is a breaking schema change.
3. **Docstring first line** → tool description (truncated to 120 chars for the LLM,
   `llm_handler.py:3287`; 200 for MCP, `tools.py:84`). A docstring is no longer "just a comment" —
   it is model-facing copy.
4. **Return type** → serialized result. MCP coerces via `mcp_server/serialization.py`
   (`normalize_result`): dataclasses→dict, dates→ISO, prose strings passed through. The LLM
   consumes prose directly.
5. **Mere existence of a public method** → auto-exposed as a tool. Exposure is a **denylist**
   (`EXCLUDED_TOOLS`), so anything new is **exposed by default**.

## Hazards observed in the current code

- **H1 — Exposure by default (security-relevant).** A new public adapter method is *instantly*
  a remote-callable MCP tool for any authenticated user, unless someone remembers to add it to
  `mcp_server/tools.py:39` `EXCLUDED_TOOLS`. Forgetting = silent remote exposure (imagine an
  `export_all_data` or an admin helper landing on the adapter).
- **H2 — Two denylists, already drifted.** `llm_handler.py:3245` and `tools.py:39` are
  *separate* hand-maintained sets and are **not** in sync despite the comment claiming they
  mirror each other:
  - Exposed to **MCP but hidden from the LLM**: `search_promises`, `resolve_datetime`.
  - Hidden from **MCP but exposed to the LLM**: `schedule_sessions`, `create_reminders`,
    `log_completed_activities`, `clear_profile_pending_question`.
  Some of this is intentional (MCP keeps singular write-verbs, drops batch variants) — but
  nothing enforces or documents which divergences are deliberate.
- **H3 — Docstring-as-API.** Editing a method's first docstring line silently rewrites the tool
  description on both model surfaces. A "tidy-up" comment edit is a behaviour change.
- **H4 — Return-shape duality.** Many methods return chat-formatted *prose strings* (built for
  the Telegram UI). Programmatic surfaces (MCP, REST) want structured JSON. Migrating a method
  string→dict helps MCP/REST but changes what the LLM prompt sees mid-conversation.
- **H5 — No guard.** Nothing in CI fails when the reflected tool surface changes, so the blast
  radius of an adapter edit is invisible in code review.

## Principles for future development

**P1. Treat the adapter's public surface as a published API.** If a method is `public` on
`PlannerAPIAdapter`, assume ≥4 channels depend on it. Internal-only logic belongs on a
repository/service, or is named with a leading underscore.

**P2. Single source of truth for exposure — flip denylist → explicit policy.** Replace the two
`EXCLUDED_TOOLS` sets with one shared classification that both `_build_tools` and
`register_adapter_tools` import. New methods default to **not exposed** until classified.

**P3. Co-locate the policy with the code.** Prefer an explicit marker on the method over a
distant list — e.g. a decorator `@expose(surfaces={"llm", "mcp"})` / `@internal`, read by both
reflectors. Exposure intent then lives next to the method and travels with it in diffs.

**P4. Docstrings and signatures are contract.** Write the first docstring line *for a model*.
Keep parameter names stable and descriptive. Treat param rename / removal / new-required and
return-shape changes as **breaking** and call them out in the PR.

**P5. Add a contract-snapshot test (the mechanism).** Generate a golden snapshot of the reflected
surface — `{tool_name: {params, required, description, surfaces}}` — and diff it in CI. Any change
to the model-facing surface must be acknowledged by updating the snapshot in the *same* PR. This
is what makes "how does this change impact MCP / the LLM / the Mini App" show up automatically in
review, instead of being discovered in production.

**P6. Separate read vs write and tag sensitivity.** Mark mutating / destructive / admin / PII
methods. Remote MCP exposure of a *write* should be a deliberate opt-in, not a denylist oversight.
(The ChatGPT `search`/`fetch` tools are read-only by design — extend that discipline.)

**P7. Return-shape policy.** Prefer structured returns for new methods. Where a method must
return chat prose, either add a structured sibling or let `serialization.normalize_result` own
the conversion — don't change an existing method's return shape without checking the LLM
prompt-side expectations.

**P8. Retire, don't delete.** Canonical one-tool-per-intent is good (e.g. `add_action` →
`log_completed_activity`). Retire superseded names by *excluding them from reflection*, not by
deleting the method — handlers and REST routers may still call them directly. Deleting a method
is breaking for the direct-call channels too.

**P9. "Touching the adapter" PR checklist.**
- [ ] Added a public method? → classify its exposure (P2/P3); default is internal.
- [ ] Renamed a param / changed a default / changed return shape? → flagged as breaking (P4/P7).
- [ ] Edited a docstring first line? → that's model-facing copy (P3/P4).
- [ ] Is it a write / admin / PII method going to MCP? → deliberate opt-in (P6).
- [ ] Updated the contract snapshot (P5)?

## Suggested next step

Implement **P5** first — it is the smallest change that makes every later adapter edit
self-policing — then **P2/P3** to collapse the drifting denylists into one policy. Both are
additive and don't change runtime behaviour.
