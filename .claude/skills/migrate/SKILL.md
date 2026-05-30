---
name: migrate
description: Run Alembic migrations on the Xaana prod or staging container via SSH.
---

# migrate

Run pending Alembic migrations on `zana-prod` or `zana-staging`.

> **Invoke:** `/migrate` — defaults to asking which env, or pass `prod` / `staging` as an argument.

## Steps (always in this order)

### 1. SSH probe

```
gcloud compute ssh vm-telegram-bots --zone=europe-west9-c --command="echo ok"
```

If it fails with a reauth error, ask the user to run `! gcloud auth login` — do **not** run it yourself.

### 2. Check current head

```
# prod
gcloud compute ssh vm-telegram-bots --zone=europe-west9-c --command="sudo docker exec -i zana-prod bash -c 'cd /app && alembic -c tm_bot/db/alembic.ini current'"

# staging
gcloud compute ssh vm-telegram-bots --zone=europe-west9-c --command="sudo docker exec -i zana-staging bash -c 'cd /app && alembic -c tm_bot/db/alembic.ini current'"
```

Report the current revision to the user before proceeding.

### 3. Apply migrations

```
# prod
gcloud compute ssh vm-telegram-bots --zone=europe-west9-c --command="sudo docker exec -i zana-prod bash -c 'cd /app && alembic -c tm_bot/db/alembic.ini upgrade head'"

# staging
gcloud compute ssh vm-telegram-bots --zone=europe-west9-c --command="sudo docker exec -i zana-staging bash -c 'cd /app && alembic -c tm_bot/db/alembic.ini upgrade head'"
```

### 4. Verify

Re-run the `current` command from step 2 and confirm it now shows `(head)`.

---

## Known gotcha: `alembic_version` column too narrow

**Symptom:** `psycopg2.errors.StringDataRightTruncation: value too long for type character varying(32)` on the `UPDATE alembic_version SET version_num=...` statement. The whole transaction rolls back — no columns are added, version stays unchanged.

**Cause:** The `alembic_version` table ships with `version_num varchar(32)`. Revision IDs longer than 32 chars (e.g. `024_plan_session_reminder_preferences` = 36 chars) exceed the limit.

**Fix** — widen the column before retrying:

1. Write this script to a local temp file (no secrets in the file — DB URL comes from the container env):

```python
# /tmp/_fix_alembic_version_col.py
import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL_PROD"])   # or DATABASE_URL_STAGING
conn.autocommit = True
cur = conn.cursor()
cur.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE varchar(64)")
print("Widened to varchar(64)")
conn.close()
```

2. Copy to VM and run inside the container:

```bash
gcloud compute scp /tmp/_fix_alembic_version_col.py vm-telegram-bots:/tmp/ --zone=europe-west9-c
gcloud compute ssh vm-telegram-bots --zone=europe-west9-c --command="sudo docker cp /tmp/_fix_alembic_version_col.py zana-prod:/tmp/ && sudo docker exec -i zana-prod python3 /tmp/_fix_alembic_version_col.py"
```

3. Re-run step 3 above.

This is a one-time fix per environment. Once widened to `varchar(64)`, it won't recur.
