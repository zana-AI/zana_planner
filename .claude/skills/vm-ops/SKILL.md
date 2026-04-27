---
name: vm-ops
description: SSH into the Xaana production VM (vm-telegram-bots, europe-west9-c) to operate the deployed stack — Docker containers, alembic migrations, postgres queries, nginx, logs, deploys.
---

# vm-ops

Operate the Xaana production VM via `gcloud compute ssh`.

> **For Javad:** invoke this with `/vm-ops` (or just describe the VM problem — Claude will load this skill automatically). One-time per session, you may be asked to run `! gcloud auth login` to refresh GCP credentials. After that, Claude can run any of the recipes below over SSH.

## Connection

```
gcloud compute ssh vm-telegram-bots --zone=europe-west9-c
```

Run any single command remotely:

```
gcloud compute ssh vm-telegram-bots --zone=europe-west9-c --command="<remote command>"
```

**Auth flow at session start.** Try a cheap probe first:

```
gcloud compute ssh vm-telegram-bots --zone=europe-west9-c --command="echo ok"
```

If it returns `ok`, you're authenticated — proceed. If it errors with reauth/credentials, ask the user to run `! gcloud auth login` in this session. The `!` prefix runs it in their shell so the OAuth browser flow works; once it succeeds, `gcloud compute ssh` works for the rest of the session (token TTL ~1h).

Do **not** run `gcloud auth login` yourself — it requires an interactive browser.

## VM layout (memorize)

| Thing | Value |
|---|---|
| VM | `vm-telegram-bots` (zone `europe-west9-c`) |
| Public IP | `34.163.204.33` |
| Domain | `xaana.club` (HTTPS via Let's Encrypt) |
| Project repo on VM | `/opt/zana-bot` |
| Env files | `/opt/zana-config/.env.prod`, `/opt/zana-config/.env.staging` |
| User data | `/srv/zana-users` (prod), `/srv/zana-users-staging` |
| Logs | `/srv/zana-logs-prod`, `/srv/zana-logs-staging` |
| Container UID | `1002` (chown target when fixing volume perms) |

## Docker containers

Defined in `/opt/zana-bot/docker-compose.yml`:

| Container | Image | Role | Env file |
|---|---|---|---|
| `zana-prod` | `zana-ai-bot:prod` | Telegram bot (prod) | `.env.prod` |
| `zana-staging` | `zana-ai-bot:staging` | Telegram bot (staging) | `.env.staging` |
| `zana-webapp` | `zana-project-webapp` | FastAPI + React SPA on `:8080` (internal) | `.env.prod` |
| `zana-stats` | (built from `stats_service/`) | Stats API on host `:8000` | `.env.staging` |
| `zana-qdrant` | `qdrant/qdrant:v1.13.2` | Vector store, internal `:6333` | — |
| `zana-nginx` | `nginx:alpine` | TLS reverse proxy on `:80/:443` | — |

All on the `web` Docker network. `zana-nginx` proxies `https://xaana.club/` → `zana-webapp:8080`.

## Common ops

### Logs

```
gcloud compute ssh vm-telegram-bots --zone=europe-west9-c --command="sudo docker logs --tail=200 zana-prod"
gcloud compute ssh vm-telegram-bots --zone=europe-west9-c --command="sudo docker logs --tail=200 zana-webapp"
gcloud compute ssh vm-telegram-bots --zone=europe-west9-c --command="sudo docker logs --tail=200 zana-nginx"
```

For follow mode (`-f`), use a bounded `--since`/`--tail` instead of streaming forever — SSH-via-command isn't interactive.

### Restart / recreate

```
# Restart only (keeps image)
sudo docker restart zana-prod
sudo docker restart zana-webapp

# Force recreate (after config or env file change)
cd /opt/zana-bot
sudo docker compose up -d --force-recreate zana-prod
```

### Health probes

```
curl -fsS https://xaana.club/api/health
sudo docker exec zana-webapp python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8080/api/health').read().decode())"
sudo docker exec zana-qdrant curl -fsS http://localhost:6333/healthz
```

### Status snapshot

```
sudo docker compose -f /opt/zana-bot/docker-compose.yml ps
sudo docker stats --no-stream
df -h /
free -m
```

### Migrations (alembic)

**Always** run from `/app` inside the container (`alembic.ini`'s `script_location` is now `%(here)s/alembic`, so cwd-relative invocations elsewhere will fail).

```
# Apply pending
sudo docker exec -i zana-prod bash -c "cd /app && alembic -c tm_bot/db/alembic.ini upgrade head"

# Verify head
sudo docker exec -i zana-prod bash -c "cd /app && alembic -c tm_bot/db/alembic.ini current"

# Show last few revisions
sudo docker exec -i zana-prod bash -c "cd /app && alembic -c tm_bot/db/alembic.ini history --rev-range -5:current"
```

Same commands work for `zana-staging`.

### Postgres (Neon/Supabase)

The connection string lives in `/opt/zana-config/.env.prod` (`DATABASE_URL_PROD`) and `.env.staging` (`DATABASE_URL_STAGING`). Two ways to query:

**A. Through the container** (no psql needed on host):

```
sudo docker exec -i zana-prod bash -lc 'psql "$DATABASE_URL_PROD" -c "SELECT count(*) FROM users;"'
```

For multi-line SQL, single-quote the heredoc so `$vars` and backticks aren't expanded locally:

```
sudo docker exec -i zana-prod bash -lc 'psql "$DATABASE_URL_PROD"' <<'SQL'
SELECT model_name, role, sum(input_tokens), sum(output_tokens), count(*)
FROM llm_usage_logs
WHERE created_at_utc > now() - interval '24 hours'
GROUP BY 1,2
ORDER BY 5 DESC;
SQL
```

**B. Directly from the VM** by reading `.env`:

```
DB_URL=$(sudo grep -E '^DATABASE_URL_PROD=' /opt/zana-config/.env.prod | cut -d= -f2-)
psql "$DB_URL" -c "SELECT count(*) FROM users;"
```

Use B when (a) the container is unhealthy / restarting, (b) you want a long interactive psql session, or (c) you're piping output to local files.

**Secrets-safety rule.** `.env.prod` also holds `BOT_TOKEN`, `GROQ_API_KEY`, `OPENAI_API_KEY`, etc. Never `cat` the whole file into the conversation, never echo `$DB_URL`, and prefer narrow `grep -E '^DATABASE_URL_'` over `cat`. If you need to confirm a key is set, print only the *length* (`echo ${#DB_URL}`) — never the value.

Staging: same patterns with `zana-staging` and `DATABASE_URL_STAGING`.

### Env files

Bot containers don't have writable env at runtime — to change a value, edit `/opt/zana-config/.env.prod` (or `.env.staging`) and recreate the container:

```
sudo nano /opt/zana-config/.env.prod
cd /opt/zana-bot && sudo docker compose up -d --force-recreate zana-prod zana-webapp
```

`.env.prod` is reused by both `zana-prod` and `zana-webapp`, so keep them in sync.

### Deploys

| Path | What it does |
|---|---|
| Push to `master` | GH Action `deploy-staging.yml` → SSH into VM, `git reset --hard origin/master`, rebuild `zana-staging` + `zana-webapp` |
| `gh workflow run deploy-prod.yml` | Promotes the existing `zana-ai-bot:staging` image → `:prod` and recreates `zana-prod` |
| `bash scripts/deploy_webapp_quick.sh` (on VM) | Manual frontend+webapp redeploy without GH Actions |

**Migrations are NOT auto-applied by either workflow.** After every deploy that ships a new alembic revision, run the migration command above.

### Nginx / SSL

```
# Reload after editing nginx.conf
sudo docker exec zana-nginx nginx -t && sudo docker exec zana-nginx nginx -s reload

# Cert location on host
sudo ls /etc/letsencrypt/live/xaana.club/

# Cert renewal status
sudo certbot certificates
```

### Disk pressure cleanup

```
sudo docker system df
sudo docker image prune -f
sudo docker builder prune -f
sudo journalctl --vacuum-time=7d
```

## Working style

- **Read-only first.** Default to logs / `ps` / `current` / `SELECT` before any restart, recreate, migration, or write SQL.
- **Confirm before destructive ops.** `force-recreate`, `image prune`, `UPDATE`/`DELETE`, alembic `downgrade`, restarting `zana-prod` during user activity — describe the action and ask before running.
- **Always `sudo` for docker.** The VM's user is not in the `docker` group (matches the user's own session).
- **Quote heredocs / SQL.** When passing multi-line input, use `<<'SQL'` (single-quoted) so `$VAR` doesn't expand on the local side.
- **Don't `gcloud auth login` yourself.** Always ask the user to run it with `!` prefix.
- **Prefer `--command=` over interactive shells.** One-shot commands are easier to log and reason about than a long interactive session.
- **Report what changed.** After any state-mutating action, re-run a status probe (logs tail, `current`, `ps`) and summarize.
