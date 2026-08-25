# Flashcards — operating guide

Everything needed to work on **flashcard content** (the words themselves) without
re-deriving the infrastructure. Read this before touching cards.

For the design rationale — why flashcards are a separate engine from
`challenge_*` — see the header of
`tm_bot/db/alembic/versions/032_flashcards_srs.py`. That boundary is deliberate
and must not be collapsed.

---

## 1. Where the database is

Production Postgres is **self-hosted in a container on the Contabo VPS**. It is
*not* Neon, not Supabase, and not on GCP (Xaana left GCP in Aug 2026 — anything
mentioning `gcloud compute ssh` is stale).

| Thing | Value |
|---|---|
| VM | Contabo `vmi3512459`, `169.58.186.195` |
| SSH | `ssh root@169.58.186.195` (key-based; you are **root**, so no `sudo`) |
| DB container | `zana-postgres` (`postgres:18-alpine`) |
| Superuser | `zana` |
| Prod DB | `zana` |
| Staging DB | `zana_staging` (lags prod — check before assuming) |
| App container | `zana-webapp` (serves `https://xaana.club`) |

**Postgres is not reachable from the internet** — no published host port. Query it
through `docker exec`:

```bash
ssh root@169.58.186.195 "docker exec zana-postgres psql -U zana -d zana -c 'SELECT count(*) FROM flashcard_note;'"
```

Multi-line SQL — single-quote the heredoc so `$` and backticks don't expand locally:

```bash
ssh root@169.58.186.195 "docker exec -i zana-postgres psql -U zana -d zana" <<'SQL'
SELECT fields->>'front', fields->>'back'
FROM flashcard_note
WHERE user_id = '108648163'
ORDER BY 1;
SQL
```

**Secrets rule:** `.env.prod` on the VM holds `BOT_TOKEN` and LLM keys. Never
`cat` it into a conversation and never echo a connection string.

---

## 2. Whose cards

Javad's Telegram user id is **`108648163`**. `user_id` is `Text`, so quote it in
SQL. Every query below must be scoped by it — the tables are multi-tenant.

Current state (2026-08-24):

```
French                          0 notes   <- container deck
  French::B1                    0 notes   <- container deck
    French::B1::Édito B1 Livre 48 notes
    French::B1::Unité 2        16 notes
    French::B1::Grammaire       3 notes
  French::B2.1                  0 notes   <- container deck
    French::B2.1::Lingoda      38 notes
                              -----------
                              105 notes
```

**Notes only ever hang off leaf decks.** Parent decks are containers with zero
notes. Any query filtering by a parent deck must expand the subtree recursively
or it silently returns nothing — this has already caused one production bug:

```sql
WITH RECURSIVE sub AS (
  SELECT deck_id FROM flashcard_deck WHERE deck_id = :deck
  UNION ALL
  SELECT d.deck_id FROM flashcard_deck d JOIN sub s ON d.parent_deck_id = s.deck_id
)
SELECT * FROM flashcard_note WHERE deck_id IN (SELECT deck_id FROM sub);
```

---

## 3. The tables

Created by migration `032_flashcards_srs`, extended by `033_flashcard_deck_promise`.
Prod is at `033`.

| Table | Holds |
|---|---|
| `flashcard_deck` | nested decks (`parent_deck_id`, self-referencing) + `promise_id` |
| `flashcard_note` | the authored content — **this is what content work edits** |
| `flashcard_note_reference` | where a card came from (FKs into `content*`) |
| `flashcard_card` | FSRS scheduling state — **do not hand-edit** |
| `flashcard_review_log` | append-only rating history — **never edit or delete** |

### `flashcard_note` — the one you'll touch

| Column | Notes |
|---|---|
| `note_id` | 32-char hex |
| `user_id` | Text |
| `deck_id` | FK, `ON DELETE CASCADE` |
| `note_type` | `vocab` or `grammar` |
| `fields` | **JSONB** — the actual content, see below |
| `source_key` | normalised `front`; **unique per user** |
| `source` | `vocab.md` (67) or `lingoda` (38) |

`fields` keys currently in use:

| Key | Meaning |
|---|---|
| `front` | the prompt (required) |
| `back` | definition or translation |
| `example` | usage example (grammar cards) |
| `note_fa` | Javad's own note, often Persian — renders RTL |
| `source_page` | page in Édito B1 |
| `lingoda_status` | Lingoda's own Known/New; **reference only** |

`fields` is JSONB precisely so new keys need no migration. Add keys freely; the
UI renders `front`, `back`, `example`, `note_fa`, `source_page`.

### Two content conventions that differ by deck

- **Édito B1** cards are **monolingual**: French word → French definition.
- **Lingoda B2.1** cards are **bilingual**: French → English gloss.

They are kept in separate decks on purpose. Don't merge them: one deck would
mean the same prompt sometimes wants a definition and sometimes a translation.

---

## 4. Editing content safely

### The rule that matters

**Editing a note's content must never reset its scheduling.** The API guarantees
this (`PATCH /api/flashcards/notes/{id}` touches `fields` only). If you write SQL
instead, update `flashcard_note` and leave `flashcard_card` alone.

`source_key` is the normalised `front` (HTML stripped, accents stripped,
lowercased, whitespace collapsed — see `normalise_key` in
`tm_bot/repositories/flashcard_repo.py`). It is how a re-import finds an existing
card instead of orphaning its history.

**Changing `front` changes `source_key`, and raw SQL will get it wrong.**
`normalise_key` strips accents via NFKD — `très` becomes `tres` — so a naive
`lower(trim(...))` produces a key that doesn't match, and the next import creates
a duplicate instead of finding the card. This deck is full of accented words.

Use the service, which recomputes the key correctly and keeps the card and its
history (they hang off `note_id`, not the key):

```bash
ssh root@169.58.186.195 "docker exec -e PYTHONIOENCODING=utf-8 zana-webapp python3 -c \"
import sys; sys.path.insert(0,'/app/tm_bot')
from services import flashcard_service as fc
print(fc.update_note('108648163', '<note_id>', {'front': 'nouvelle entrée'}))
\""
```

If you must use SQL, replicate the normalisation exactly — see `normalise_key`
in `tm_bot/repositories/flashcard_repo.py`; Postgres's `unaccent` extension is
not installed by default.

Editing only the definition is safe and needs no `source_key` change:

```sql
UPDATE flashcard_note
SET fields = jsonb_set(fields, '{back}', '"new definition"'),
    updated_at = now()
WHERE note_id = '...' AND user_id = '108648163';
```

### Deleting

`DELETE FROM flashcard_note` cascades to the card **and its review history**.
That history cannot be reconstructed. Prefer suspending:

```sql
UPDATE flashcard_card SET suspended = true WHERE note_id = '...';
```

### Never do these

- Don't write to `flashcard_review_log` — append-only, and the FSRS optimiser's
  training input.
- Don't hand-set `stability` / `difficulty` / `due` / `state`. They're a fitted
  model's output, not free parameters; a plausible-looking guess degrades
  scheduling in ways that take months to notice.
- Don't seed FSRS state from an external "known" flag (e.g. `lingoda_status`).
  That asserts a review history that never happened in this system.
- Don't store review state in `challenge_attempts`, or let
  `challenge_decks.release_at` drive what gets reviewed. Different engine.

---

## 5. Importers

Both live in `scripts/` and are **idempotent** — re-running updates existing
notes rather than duplicating them or resetting schedules.

`scripts/` is **not** copied into the webapp image, so copy a script in before
running it:

```bash
scp scripts/import_french_vocab.py root@169.58.186.195:/tmp/
ssh root@169.58.186.195 "docker exec zana-webapp mkdir -p /app/scripts && \
  docker cp /tmp/import_french_vocab.py zana-webapp:/app/scripts/"
```

### `import_french_vocab.py` — markdown tables

Source: `E:\Dropbox\Dropbox\French\vocab\vocab.md` (Zotero highlights, Édito B1).
Parsing needs no database, so `--dry-run` works anywhere:

```bash
python3 scripts/import_french_vocab.py --file vocab.md --dry-run
```

```bash
ssh root@169.58.186.195 "docker exec -e PYTHONIOENCODING=utf-8 zana-webapp \
  python3 /app/scripts/import_french_vocab.py --file /tmp/vocab.md --user-id 108648163 --publish"
```

It deliberately skips the file's "Notes libres" section (no definition column).
One of those, **خانوار → le foyer / le ménage (household)**, is genuinely missing
vocabulary rather than a duplicate — still unimported.

### `import_lingoda_vocab.py` — Lingoda PDF exports

Lingoda's table flattens when extracted as text, so the French column is read by
coordinate and used to split each line. Parsing needs `pypdf`, which is
**deliberately not in the runtime image** — parse locally, publish from JSON:

```bash
python3 scripts/import_lingoda_vocab.py --file a.pdf --file b.pdf --json > lingoda.json
# copy lingoda.json to the container, then:
python3 /app/scripts/import_lingoda_vocab.py --from-json /tmp/lingoda.json \
  --user-id 108648163 --publish
```

It refuses to publish if its self-checks fail (Lingoda's own "of N words" count,
or any term it couldn't split).

---

## 6. Verifying your work

Always re-check after a write:

```bash
ssh root@169.58.186.195 "docker exec zana-postgres psql -U zana -d zana -c \"
SELECT (SELECT count(*) FROM flashcard_note WHERE user_id='108648163') AS notes,
       (SELECT count(*) FROM flashcard_card c JOIN flashcard_note n ON n.note_id=c.note_id
        WHERE n.user_id='108648163') AS cards,
       (SELECT count(DISTINCT source_key) FROM flashcard_note WHERE user_id='108648163') AS keys;\""
```

`notes`, `cards` and `keys` should all be equal. If `keys` is lower, two notes
collided on `source_key` and one overwrote the other.

Content changes are **live immediately** — no deploy needed, the API reads the
database directly. Only code changes need a deploy (push to `master`; note that
this rebuilds `zana-webapp` with `ENVIRONMENT=production`, so a push to master is
a production web release).

**Migrations do not run on deploy.** Apply them yourself, before the code that
needs them lands — new code against an old schema is how issue 58 happened:

```bash
ssh root@169.58.186.195 "docker exec -w /app/tm_bot/db zana-webapp alembic upgrade head"
```

The app: `https://xaana.club` → **Play → French**, or **Explore → Quiz → French**.

---

## 6b. Decks and promises

There is exactly **one root deck, `French`**, holding `B1`, `B2.1` and
`Actualités`. It carries `promise_id` = P22 (`French with Atena`), which is what
puts it under Play and on the promise card.

Two rules keep it that way:

- **Never invent a root name.** `get_or_create_path` creates whatever it is
  given, so `Français::B1` silently builds a second tree next to `French::B1`.
  That is exactly how the deck list came to show "Français (26)" and
  "French (105)" as if they were unrelated. Match the existing root exactly.
- **Attach new roots to a promise**, or they are reachable only from Explore:

```bash
curl -X PATCH .../api/flashcards/decks/<deck_id> -d '{"promise_id": "<promise_uuid>"}'
```

---

## 7. Related

- `tm_bot/db/alembic/versions/032_flashcards_srs.py` — schema + design rationale
- `tm_bot/db/alembic/versions/033_flashcard_deck_promise.py` — the deck→promise edge
- `webapp_frontend/src/components/sheets/PlaySheet.tsx` — the Play launcher
- `tm_bot/repositories/flashcard_repo.py` — decks, notes, references
- `tm_bot/repositories/flashcard_review_repo.py` — cards, review log
- `tm_bot/services/flashcard_service.py` — the only place that opens sessions for these
- `tm_bot/webapp/routers/flashcards.py` — HTTP API
- `webapp_frontend/src/pages/FlashcardsPage.tsx` — the study UI
- `.claude/skills/vm-ops/SKILL.md` — general VM operations
