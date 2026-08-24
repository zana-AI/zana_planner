---
name: migrate
description: Run Alembic migrations on the Xaana prod or staging container via SSH.
---

# migrate

Run pending Alembic migrations on `zana-prod` or `zana-staging`.

> **Invoke:** `/migrate` — defaults to asking which env, or pass `prod` / `staging` as an argument.

The VM is a Contabo VPS reached by SSH key as `root` (see `/vm-ops` for full layout). You are root, so no `sudo`. Anything mentioning `gcloud compute ssh` is stale — Xaana left GCP in Aug 2026.

## Steps (always in this order)

### 1. SSH probe

```
ssh -o BatchMode=yes root@169.58.186.195 "echo ok"
```

If it hangs or refuses, the key isn't loaded — ask the user. Do not try to add keys or passwords yourself.

### 2. Check current head

```
# prod
ssh root@169.58.186.195 "docker exec -i zana-prod bash -c 'cd /app && alembic -c tm_bot/db/alembic.ini current'"

# staging
ssh root@169.58.186.195 "docker exec -i zana-staging bash -c 'cd /app && alembic -c tm_bot/db/alembic.ini current'"
```

Report the current revision to the user before proceeding.

**Prod and staging drift independently** — staging is not always ahead. Check the one you're about to touch rather than assuming.

### 3. Confirm what will run

Before applying, list exactly which revisions are pending, so neither of you is surprised by a migration that rode along:

```
ssh root@169.58.186.195 "docker exec -i zana-prod bash -c 'cd /app && alembic -c tm_bot/db/alembic.ini history --rev-range current:head'"
```

If more than the expected revision is pending, say so and get agreement before continuing.

### 4. Apply migrations

```
# prod
ssh root@169.58.186.195 "docker exec -i zana-prod bash -c 'cd /app && alembic -c tm_bot/db/alembic.ini upgrade head'"

# staging
ssh root@169.58.186.195 "docker exec -i zana-staging bash -c 'cd /app && alembic -c tm_bot/db/alembic.ini upgrade head'"
```

**The container runs the code baked into its image, not your local working tree.** A migration file that exists only on your machine will not be found. It has to be deployed first — pushed to `master` (rebuilds `zana-staging`) or otherwise copied into the image.

### 5. Verify

Re-run the `current` command from step 2 and confirm it now shows `(head)`.

## Database layout

Postgres is **self-hosted on the VM**, not Neon/Supabase:

| Thing | Value |
|---|---|
| Container | `zana-postgres` (`postgres:18-alpine`) |
| Superuser | `zana` |
| Prod DB | `zana` |
| Staging DB | `zana_staging` |

To inspect schema directly after a migration:

```
ssh root@169.58.186.195 "docker exec zana-postgres psql -U zana -d zana_staging -c '\\d flashcard_card'"
```

---

## Known gotcha: `alembic_version` column too narrow

**Status: already fixed on both prod and staging** (both are `varchar(64)` as of Aug 2026). Kept here in case a fresh database is ever provisioned.

**Symptom:** `psycopg2.errors.StringDataRightTruncation: value too long for type character varying(32)` on the `UPDATE alembic_version SET version_num=...` statement. The whole transaction rolls back — no columns are added, version stays unchanged.

**Cause:** The `alembic_version` table ships with `version_num varchar(32)`. Revision IDs longer than 32 chars (e.g. `024_plan_session_reminder_preferences` = 36 chars) exceed the limit.

**Check before assuming:**

```
ssh root@169.58.186.195 "docker exec zana-postgres psql -U zana -d zana -Atc \"SELECT format_type(atttypid,atttypmod) FROM pg_attribute WHERE attrelid='alembic_version'::regclass AND attname='version_num';\""
```

**Fix** — widen the column, then retry step 4:

```
ssh root@169.58.186.195 "docker exec zana-postgres psql -U zana -d zana -c 'ALTER TABLE alembic_version ALTER COLUMN version_num TYPE varchar(64)'"
```

This is a one-time fix per database.
