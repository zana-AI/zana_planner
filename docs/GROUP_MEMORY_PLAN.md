# Club context & memory — redesign plan

Status: proposed, not implemented. Written 2026-09-01.

Companion to the model/config changes applied the same day (see "Already done" below).

## The problem

The bot has no durable memory of a club's conversations, and no memory at all of the
people in it beyond their name and today's check-in row. Three concrete gaps, all
verified in the current code:

1. **The transcript is volatile.** `PlannerBot._group_chat_history` is
   `defaultdict(lambda: deque(maxlen=40))` (`tm_bot/planner_bot.py:117`) — process
   memory. Every restart and every deploy wipes every club's conversational history.
   28 messages reach the responder, 4 reach the group router.

2. **Nothing in the conversation path writes club memory.** `club_memory_write` is
   called from exactly one site — `tm_bot/webapp/routers/community.py:770`, storing the
   owner's setup text. The group handler never writes. The bot cannot learn anything
   about anyone from talking to them.

3. **The retrieval layer is dead code.** `club_memory_search` is defined
   (`tm_bot/memory/club_memory.py:48`), exported in `memory/__init__.py`, and called
   from nowhere. `_get_club_memory_block` dumps `MEMORY.md` wholesale into the prompt
   instead.

Net effect: "club memory" today is whatever the owner typed once at setup, plus forty
volatile messages.

## Design principles

- **Cost scales per club per day, not per message.** Distillation happens on a schedule
  or a message-count trigger, never on the hot path.
- **Retrieve, don't dump.** Inject the few facts relevant to this turn, not the whole
  memory file.
- **Selective member notes.** Only inject notes for people active in the current
  window (typically 1–3), never all members.
- **Ground truth stays in Postgres.** Memory adds colour and continuity; it must never
  become a second, competing source for check-in counts. The existing AUTHORITY
  HIERARCHY block in the responder prompt stays exactly as it is.

## Proposed work

### 1. Persist the group transcript
Write group-visible messages to Postgres instead of (or alongside) the in-RAM deque.
`_log_structured_event` already exists and already receives these events — reuse that
path rather than adding a table. Load the recent window from the DB on demand.

- Fixes restart amnesia at zero LLM cost.
- Prerequisite for everything below.
- Retention: keep raw messages ~30 days, then let the digest carry the memory.

### 2. Rolling club digest
One cheap LLM call per club per day (or every N new messages, whichever comes first)
that reads new messages since the last digest and updates durable club facts via the
existing `club_memory_upsert_fact` / `club_memory_write`.

- ~1 extra call/day/club. At grok-4-1-fast pricing this is rounding error.
- Output: short, factual lines. "Sepideh plays in the evenings." "The club agreed to
  pause Fridays."
- Must be told explicitly not to record check-in counts or streaks — those come from
  the DB.

### 3. Per-member notes, injected selectively
A per-member note store keyed by `(club_id, user_id)`, populated by the same digest
pass. At prompt time, inject notes **only for members who appear in the current
window** — the sender, anyone they replied to, anyone named in the last few messages.

This is where the token discipline lives: six members' notes injected on every turn
would undo the savings; two members' notes cost ~60 tokens.

### 4. Use the retrieval layer that already exists
Replace the wholesale `MEMORY.md` dump in `_get_club_memory_block` with a
`club_memory_search` call scoped to the current message, top-k small. The Qdrant
plumbing is already written and already partitioned by `club_id`.

### 5. Compress the transcript window
Currently 28 raw messages. Replace with: last ~8 verbatim + a 2-line rolling summary
of the preceding window. Costs fewer tokens than 28 raw lines while reaching further
back in time.

### Expected cost impact
Responder input today measures ~1,200–1,300 tokens on a real group turn. The digest
block plus 2–3 member notes adds roughly +200. At grok-4-1-fast's $0.20/1M input that
is negligible, and items 4 and 5 give some of it back.

## DM (1:1) path — separate follow-up

Requested 2026-09-01. Not part of the group work above.

**Model.** The DM path should also run a capable model — it is the path with tools,
mutations, and multi-step planning, so it is the *least* tolerant of a weak model. The
provider switch applied today already moves it to `grok-4-1-fast-non-reasoning`
alongside the group path, since `MODEL_CONFIGS` is per-role, not per-surface. If the
DM path later needs more reasoning than the group path, split the responder role by
surface rather than by provider.

**Budget.** DMs need their own quota, and it is a different shape from the group taper:

- The group budget throttles *unprompted* chatter; every DM is prompted, so the group's
  "downgrade to an emoji" strategy does not apply.
- Goal is preventing an unbounded free general-purpose assistant, not managing noise.
- Suggested shape: a per-user daily allowance of LLM-backed turns, with
  club/promise-related turns cheap or free and off-topic general-assistant turns
  drawing from a smaller pool. Route the classification through the existing cheap
  Groq router rather than the responder.
- On exhaustion: answer briefly and say the allowance resets tomorrow — never go
  silent. Silence in a 1:1 chat reads as broken.
- Reuse `apply_budget`'s day-keyed entry shape (`llms/group_router.py`) so both
  surfaces report through one mechanism.

Open question for whoever picks this up: whether the allowance is per-user or
per-user-per-club, and whether club owners get a larger one.

## Follow-up messages (implemented 2026-09-01)

The group responder has no tools, so when a member asked it to remind the others it
produced the socially natural answer — "I'll remind them" — and then never acted.
Nothing carries between turns, so the intention evaporated.

It can now request exactly one follow-up. The responder ends its reply with
`[[ACTION:REMIND_PENDING]]`; `extract_group_followup` strips the marker (wherever it
appears — a leaked marker is worse than a missed action) and `PlannerBot._run_group_followup`
posts the existing club reminder, with check-in buttons, as a second message.

Guardrails, all covered by `tests/unit/test_group_followup.py`:

- The action is only *offered* in the prompt when it would do something: somebody is
  still pending, and the turn is a `FULL_REPLY` (not a one-liner, not proactive).
- A marker the model emits when it wasn't offered is stripped and ignored.
- 30-minute per-chat cooldown, so repeated asks don't re-post the reminder.
- A marker-only reply is honoured as an action with no text, rather than becoming an
  error string.
- The prompt now states plainly what the bot *cannot* do — no DMs, no scheduling, no
  acting later — which also stopped it promising private messages it can't send.

The marker is stripped before the language/script guard runs: it is Latin text and
would otherwise read as a wrong-alphabet answer in a Persian group.

### Extending it
Keep the action set tiny and closed. Each new action needs a real implementation on
the PlannerBot side and its own offer condition; anything not in
`GROUP_FOLLOWUP_ACTIONS` is something the bot must not promise. The natural next
candidates are a club leaderboard post and a "show the week so far" summary, both of
which already have message builders.

## Already done (2026-09-01)

Applied separately, listed here so this plan reads against the right baseline:

- Provider pinned to `xai` in `.env.prod` / `.env.staging`. Auto-detection had been
  selecting Groq `gpt-oss-20b` for router, planner and responder.
- `MODEL_CONFIGS["xai"]` → `grok-4-1-fast-non-reasoning` for all three roles, with
  `grok-4.3` retained as the escalation fallback.
- `FALLBACK_MODELS["groq"]` → `gpt-oss-120b`; it had pointed at the primary model, so
  the first fallback hop retried a model the adapter had just blocked.
- `reasoning_effort="low"` for `gpt-oss-*` in `groq_adapter.build_role_model`. Measured:
  output tokens 362 → 73, latency 2133ms → 591ms, same answer quality.
- Group engagement budget rewritten as a taper (`llms/group_router.py`).

### Why the model changed
`gpt-oss-20b` confirmed a fabricated 50-day streak to the group in 3 of 4 runs
("Congrats on that 50-day streak, @Homa! 🎉" — the member's real streak was 0).
`gpt-oss-120b`, `grok-4-1-fast-non-reasoning`, `grok-4.3` and `deepseek-chat` all
correctly refused. Easier ground-truth tests — mob pressure, correcting the bot's own
earlier wrong answer, prompt injection in the transcript, cross-club data requests —
were passed by every model including 20b. The failure mode is specifically a
**flattering, unverifiable claim about the speaker themselves**.

Any future model swap should be re-checked against that case before shipping.
