---
name: vm-ops
description: SSH into the Xaana production VM (Contabo vmi3512459, 169.58.186.195) to operate the deployed stack — Docker containers, alembic migrations, postgres queries, nginx, logs, deploys.
---

# vm-ops

Operate the Xaana production VM over plain SSH.

> **For Javad:** invoke this with `/vm-ops` (or just describe the VM problem — Claude will load this skill automatically). No cloud CLI or auth dance: the VM is a Contabo VPS reached by SSH key as `root`.

## Connection

```
ssh root@169.58.186.195
```

Run any single command remotely:

```
ssh root@169.58.186.195 "<remote command>"
```

**Probe at session start:**

```
ssh -o BatchMode=yes root@169.58.186.195 "echo ok"
```

If it returns `ok`, proceed. If it hangs or refuses, the key isn't loaded — ask the user; do not try to add keys or passwords yourself.

You are **root**, so `sudo` is neither needed nor present in these recipes. Older notes that prefix every docker command with `sudo` predate the migration.

> **History:** Xaana ran on GCP (`vm-telegram-bots`, `europe-west9-c`) until the credit lapsed and the VM was suspended in Aug 2026. Anything mentioning `gcloud compute ssh` is stale — the GCP VM is gone.

## VM layout (memorize)

| Thing | Value |
|---|---|
| Provider | Contabo VPS |
| Host | `169.58.186.195` (hostname `vmi3512459`) |
| SSH user | `root` |
| Domain | `xaana.club` (HTTPS via Let's Encrypt) |
| Project repo on VM | `/opt/zana-bot/zana_planner` |
| Compose file | `/opt/zana-bot/zana_planner/docker-compose.yml` |
| Env files | `/opt/zana-config/.env.prod`, `/opt/zana-config/.env.staging` |

Note the repo path has a **nested** `zana_planner` — `/opt/zana-bot` alone is the parent and holds no compose file.

## Docker containers

Running:

| Container | Image | Role | Env file |
|---|---|---|---|
| `zana-prod` | `zana-ai-bot:prod` | Telegram bot (prod) | `.env.prod` |
| `zana-staging` | `zana-ai-bot:staging` | Telegram bot (staging) | `.env.staging` |
| `zana-webapp` | `zana-project-webapp` | FastAPI + React SPA on `:8080` (internal) | `.env.prod` |
| `zana-postgres` | `postgres:18-alpine` | **Self-hosted** database, internal `:5432` | — |
| `zana-qdrant` | `qdrant/qdrant:v1.13.2` | Vector store, internal `:6333` | — |
| `zana-nginx` | `nginx:alpine` | TLS reverse proxy on `:80/:443` | — |

Defined in compose but **not currently running**: `zana-stats`, and everything behind the `mcp` profile (`zana-mcp`, `zana-hydra*`) and the `langfuse` profile.

`zana-nginx` proxies `https://xaana.club/` → `zana-webapp:8080`.

## Postgres (self-hosted — not Neon/Supabase)

The database is a container on this VM. Older notes calling it Neon or Supabase are stale.

| Thing | Value |
|---|---|
| Container | `zana-postgres` (`postgres:18-alpine`) |
| Superuser | `zana` |
| Prod DB | `zana` |
| Staging DB | `zana_staging` |
| Reachable from other containers as | `zana-postgres:5432` |

Query directly — no password needed via `docker exec` (local socket trust):

```
docker exec zana-postgres psql -U zana -d zana -c "SELECT count(*) FROM users;"
docker exec zana-postgres psql -U zana -d zana_staging -c "SELECT count(*) FROM users;"
```

For multi-line SQL, single-quote the heredoc so `$vars` and backticks aren't expanded locally:

```
ssh root@169.58.186.195 "docker exec -i zana-postgres psql -U zana -d zana" <<'SQL'
SELECT model_name, role, sum(input_tokens), sum(output_tokens), count(*)
FROM llm_usage_logs
WHERE created_at_utc > now() - interval '24 hours'
GROUP BY 1,2
ORDER BY 5 DESC;
SQL
```

You can also go through a bot container using its env var, which is the right choice when you want to confirm *what the app actually connects to*:

```
docker exec -i zana-prod bash -lc 'psql "$DATABASE_URL_PROD" -c "SELECT count(*) FROM users;"'
```

**Secrets-safety rule.** `.env.prod` also holds `BOT_TOKEN`, `GROQ_API_KEY`, `OPENAI_API_KEY`, etc. Never `cat` the whole file into the conversation, never echo a connection string, and prefer narrow `grep -E '^DATABASE_URL_'` over `cat`. To confirm a key is set, print only its *length* (`echo ${#DB_URL}`) — never the value.

## Common ops

### Logs

```
ssh root@169.58.186.195 "docker logs --tail=200 zana-prod"
ssh root@169.58.186.195 "docker logs --tail=200 zana-webapp"
ssh root@169.58.186.195 "docker logs --tail=200 zana-nginx"
```

For follow mode (`-f`), use a bounded `--since`/`--tail` instead of streaming forever — SSH-via-command isn't interactive.

### Restart / recreate

```
# Restart only (keeps image)
docker restart zana-prod
docker restart zana-webapp

# Force recreate (after config or env file change)
cd /opt/zana-bot/zana_planner
docker compose up -d --force-recreate zana-prod
```

### Health probes

```
curl -fsS https://xaana.club/api/health
docker exec zana-webapp python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/api/health').read().decode())"
docker exec zana-postgres pg_isready -U zana
```

### Status snapshot

```
docker compose -f /opt/zana-bot/zana_planner/docker-compose.yml ps
docker stats --no-stream
df -h /
free -m
```

### Migrations (alembic)

See the `/migrate` skill for the full procedure. Quick form — **always** run from `/app` inside the container:

```
docker exec -i zana-prod bash -c "cd /app && alembic -c tm_bot/db/alembic.ini current"
docker exec -i zana-prod bash -c "cd /app && alembic -c tm_bot/db/alembic.ini upgrade head"
```

Same commands work for `zana-staging`.

### Env files

Bot containers don't have writable env at runtime — to change a value, edit `/opt/zana-config/.env.prod` (or `.env.staging`) and recreate the container:

```
nano /opt/zana-config/.env.prod
cd /opt/zana-bot/zana_planner && docker compose up -d --force-recreate zana-prod zana-webapp
```

`.env.prod` is reused by both `zana-prod` and `zana-webapp`, so keep them in sync.

### Deploys

CI connects over generic SSH secrets (`DEPLOY_HOST`, `DEPLOY_USER`, `PROJECT_PATH`, `DEPLOY_SSH_KEY`) — it is **not** cloud-specific, and already points at Contabo.

| Path | What it does |
|---|---|
| Push to `master` | GH Action `deploy-staging.yml` → SSH into VM, `git reset --hard origin/master`, rebuild `zana-staging` + `zana-webapp` |
| `gh workflow run deploy-prod.yml` | Promotes the existing `zana-ai-bot:staging` image → `:prod` and recreates `zana-prod` |
| `bash scripts/deploy_webapp_quick.sh` (on VM) | Manual frontend+webapp redeploy without GH Actions |

**`zana-webapp` is rebuilt by the *staging* workflow but runs with `ENVIRONMENT=production` against the prod DB.** So a push to `master` ships the web app to production even though the workflow is named "staging". Sequence any migration the web app needs *before* the push.

**Migrations are NOT auto-applied by either workflow.** After every deploy that ships a new alembic revision, run the migration command above.

### Nginx / SSL

```
# Reload after editing nginx.conf
docker exec zana-nginx nginx -t && docker exec zana-nginx nginx -s reload

# Cert location on host
ls /etc/letsencrypt/live/xaana.club/

# Cert renewal status
certbot certificates
```

### Disk pressure cleanup

```
docker system df
docker image prune -f
docker builder prune -f
journalctl --vacuum-time=7d
```

### git on the VM

The checkout is owned by a different user than `root`, so git refuses it as "dubious ownership". Pass the override inline rather than mutating global config:

```
cd /opt/zana-bot/zana_planner && git -c safe.directory='*' log --oneline -3
```

## Working style

- **Read-only first.** Default to logs / `ps` / `current` / `SELECT` before any restart, recreate, migration, or write SQL.
- **Confirm before destructive ops.** `force-recreate`, `image prune`, `UPDATE`/`DELETE`, alembic `downgrade`, restarting `zana-prod` during user activity — describe the action and ask before running.
- **No `sudo`.** You are root. Recipes that prefix `sudo docker` are pre-migration leftovers.
- **Quote heredocs / SQL.** When passing multi-line input, use `<<'SQL'` (single-quoted) so `$VAR` doesn't expand on the local side.
- **Prefer one-shot `ssh host "cmd"` over interactive shells.** Easier to log and reason about.
- **Report what changed.** After any state-mutating action, re-run a status probe (logs tail, `current`, `ps`) and summarize.
