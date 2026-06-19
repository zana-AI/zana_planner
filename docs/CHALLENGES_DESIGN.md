# Challenges — v1 Design (creator-led, async interactive challenges)

Status: **draft for review** · Owner: Javad · Date: 2026-06-19
First instance: **Atena's French vocab** (French teacher, ~400-member Telegram channel).

This doc designs a **general interactive-challenge engine**, with vocab/flashcards as the
*first content type* — NOT a flashcard- or language-specific system. See
`memory/project-vocab-challenges-direction.md` for the product rationale.

---

## 1. Goal & scope

Turn the 3rd home tab (Explore/Templates, currently weak) into a home for **async social
challenges**. v1 ships exactly four interaction tools, all of which already exist or are thin:

| Tool | Status |
|------|--------|
| Flashcard review | **new** (interactive content) |
| Multiple-choice quiz | **new** (interactive content) |
| Streaks | **reuse** — `actions_repo.get_checkin_streak()` |
| Leaderboard | **reuse** — `community.py::_rank_club_leaderboard_members` |

Out of scope for v1: audio/pronunciation, synchronous/live play, coach self-authoring UI,
monetization. (Design so they can bolt on later.)

## 2. Principles

1. **General, not vocab-specific.** A challenge is `challenge → decks → items`; an item is
   `{front, back, example?, media?, options?[]}`. Flashcard and MCQ share one item schema.
   A future trivia / math-drill / habit challenge reuses the same tables.
2. **Reuse the promise/action engine.** Streaks, leaderboard, and the heatmap already run on
   `actions` + a `promise`. A challenge participant gets a lightweight count-promise behind the
   scenes; "completed today's deck" logs a `club_checkin` action → streak + leaderboard for free.
3. **Zero-friction entry.** Tap a channel deep-link → Mini App opens *on the challenge* →
   play in <10s. Identity from Telegram, no signup, no promise setup wizard.
4. **The channel is the flywheel.** Manufacture postable moments (weekly leaderboard image,
   "word of the day") that the host wants to re-post — each one re-activates her audience.
5. **No Telegram group, no second bot.** One Xaana bot, DM reminders, Mini App is the surface.

## 3. Concept model & mapping to existing tables

```
Challenge ─┬─ host (a user; Atena)         → users / media (brand: name + avatar)
           ├─ cohort (participants)         → REUSE club + club_members  (a club with NO telegram group)
           ├─ per-participant commitment    → REUSE promises + promise_instances (count metric)
           ├─ progress / streak / rank      → REUSE actions ('club_checkin') + leaderboard query
           └─ interactive content + answers → NEW: challenge_decks, challenge_items, challenge_attempts
```

**Why back the cohort with a `club` row:** the leaderboard + streak code is cohort-based and
already works on `(club → members → promises → actions)`. A club whose `telegram_status =
'not_connected'` is valid today (the Telegram fields are nullable), so a "club with no group"
is a clean fit and avoids re-implementing ranking. *This coupling is the main fork — see §10.*

## 4. New data model (5 tables)

```sql
-- the challenge itself (ties host + cohort + content + schedule)
challenges (
  challenge_id   TEXT PK,
  host_user_id   TEXT,                 -- Atena; drives the brand shown to users
  club_id        TEXT NULL,            -- the cohort (REUSE clubs); see §10
  title          TEXT,                 -- "Atena's French"
  description     TEXT,
  activity_type  TEXT,                 -- 'flashcard' | 'multiple_choice'  (extensible)
  cadence        TEXT,                 -- 'daily' | 'weekly'
  start_date     TEXT, end_date TEXT NULL,
  visibility     TEXT,                 -- 'public' (directory) | 'unlisted' (link-only)
  source_key     TEXT,                 -- startapp deep-link token, e.g. 'atena_fr'
  status         TEXT DEFAULT 'active',
  created_at_utc TEXT, updated_at_utc TEXT
)

-- a scheduled set of items (e.g. "Week 1 — Food")
challenge_decks (
  deck_id        TEXT PK,
  challenge_id   TEXT FK,
  title          TEXT,
  position       INTEGER,              -- order within the challenge
  release_at     TEXT NULL,            -- when this deck unlocks (async schedule)
  created_at_utc TEXT
)

-- one card / question. Same schema serves flashcard AND MCQ.
challenge_items (
  item_id        TEXT PK,
  deck_id        TEXT FK,
  position       INTEGER,
  front          TEXT,                 -- prompt (word/expression/question)
  back           TEXT,                 -- answer (translation / correct choice)
  example        TEXT NULL,            -- example sentence / hint
  media_url      TEXT NULL,            -- reserved (audio/img) — unused in v1
  options        JSONB NULL,           -- MCQ distractors incl. the correct one; null for flashcards
  created_at_utc TEXT
)

-- who joined (could also be derived from club_members; explicit = source attribution + analytics)
challenge_participants (
  challenge_id   TEXT,
  user_id        TEXT,
  joined_at_utc  TEXT,
  source         TEXT NULL,            -- where they came from (startapp source_key)
  PRIMARY KEY (challenge_id, user_id)
)

-- every answer (drives score; feeds leaderboard score_sum + completion)
challenge_attempts (
  attempt_id     TEXT PK,
  challenge_id   TEXT, deck_id TEXT, item_id TEXT,
  user_id        TEXT,
  response       TEXT NULL,            -- chosen option (MCQ) / self-grade (flashcard: knew/didnt)
  is_correct     INTEGER NULL,         -- MCQ; null/derived for flashcards
  answered_at_utc TEXT,
  time_ms        INTEGER NULL
)
```

Indexes: `challenge_items(deck_id, position)`, `challenge_decks(challenge_id, position)`,
`challenge_attempts(user_id, challenge_id, answered_at_utc)`, `challenges(visibility, status)`.

## 5. The two activity types on one schema

- **Flashcard:** show `front` → tap to reveal `back` (+`example`). Self-grade ("knew it / didn't").
  `options` is null. Completion = saw all cards; streak credit on deck completion.
- **Multiple-choice:** show `front` + `options` (one is `back`). Score = `is_correct`.
  Distractors are AI-generated from the deck's other items + the word's confusables.

Both write `challenge_attempts`; both log ONE `club_checkin` action per completed deck (→ streak +
leaderboard participation). MCQ additionally contributes accuracy to the leaderboard `score_sum`.

## 6. Async play loop

1. Deck releases per `cadence` (daily/weekly) at `release_at`.
2. Xaana bot **DMs** the participant: "Your French set is ready 🇫🇷" with a deep-link button.
3. User opens Mini App → plays the deck (flashcards or MCQ).
4. On completion: write `challenge_attempts` + one `club_checkin` action.
   → streak updates (`get_checkin_streak`), leaderboard updates (rolling 7d), heatmap fills.
5. Weekly: generate a **shareable leaderboard image** the host can post back to her channel.

Reminders reuse the existing scheduler/reminder infra (same path as plan-session reminders);
no new bot, no group.

## 7. Entry funnel (the crux)

- Configure a **Main Mini App direct link** in BotFather once: `t.me/<bot>/<app>`.
- Channel post carries `t.me/<bot>/<app>?startapp=atena_fr`.
- App reads `tgWebAppStartParam` → resolves `source_key` → routes straight into the challenge,
  auto-joins on first "play", attributes `source`.
- A plain link works even if Atena posts manually; an inline **button** needs the bot to be a
  channel admin (optional, §10 of the prior discussion). Start with manual links.

## 8. API sketch (new endpoints)

```
GET  /api/challenges                      # directory (public, with social proof counts)
GET  /api/challenges/{id}                 # detail incl. host brand, today's deck
POST /api/challenges/{id}/join            # join (creates participant + club membership + count-promise)
GET  /api/challenges/{id}/decks/today     # the deck due now (items, minus answers for MCQ)
POST /api/challenges/{id}/decks/{deckId}/complete   # batch attempts + log club_checkin action
GET  /api/challenges/{id}/leaderboard     # reuse club leaderboard ranking
# admin/ingestion (no coach UI in v1):
POST /api/admin/challenges                # create challenge + host
POST /api/admin/challenges/{id}/decks     # upload a deck of items (from Atena's list, AI-expanded)
```

## 9. Content ingestion (Atena → decks), no coach UI

Atena supplies what she already has as a teacher: a list of words/expressions. Lowest-friction
intake = a flat table she fills:

| front (FR) | back (EN) | example (optional) | theme/deck |
|------------|-----------|--------------------|------------|
| la pomme | the apple | Je mange une pomme. | Food |

We (admin + AI) turn each row into a `challenge_item`, and **AI generates the MCQ distractors**
(3 plausible-but-wrong options per word, drawn from same-theme items + confusables). So Atena's
effort ≈ paste her list; the system manufactures the interactive content.

## 10. What we reuse vs build, and the one fork to decide

**Reuse (no/low work):** streaks, leaderboard, heatmap, reminder scheduler, user/brand, Mini App
shell, auth, deep-linking.

**Build (the real work):** 5 tables + migration, the deck/item/attempt repos, the play-loop
endpoints, the 2 frontend activity components (flashcard, MCQ), the new Challenges tab/directory,
the admin ingestion + AI distractor generation, the shareable weekly leaderboard image.

**Fork — DECIDED: Option A** (2026-06-19).
- **A — back the cohort with a `club` row (CHOSEN for v1).** Max reuse: leaderboard/streak
  work almost as-is. A challenge "is a" club under the hood (with `telegram_status='not_connected'`,
  no group). Accept the slight conceptual overload to ship and learn which tools users want.
- B — standalone `challenge_participants` + dedicated ranking — deferred; revisit only if the
  club coupling bites.

Implication of A: `POST /join` creates a `club_members` row + a count-`promise`/`promise_instance`
for the participant; deck completion logs a `club_checkin` action so streak + leaderboard light up
with zero new ranking code. `challenge_participants` still kept for source attribution/analytics.

## 11. Open questions

- Do flashcards need spaced-repetition (re-surface missed cards) in v1, or simple linear decks?
- Streak granularity: per-challenge streak, or does it roll into the user's global streak?
- Directory visibility: public browse vs link-only while we pilot with Atena?
- Attribution: keep `challenge_participants.source` for funnel analytics from day one (cheap, yes).
