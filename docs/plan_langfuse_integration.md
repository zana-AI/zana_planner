# Plan: Langfuse for trace, dataset, and human review

**Status:** Phase 1 + 2 implemented (committed); Phase 0 recon and Phase 3+ pending.
**Owner:** Javad
**Goal:** export Xaana's LLM conversations, debug them, build a dataset of "better" answers, and measure response improvements over time.

---

## Why Langfuse (and not Argilla, yet)

Both are valid open-source tools. Langfuse alone covers ~80% of what we need:
tracing, datasets, LLM-as-judge scoring, prompt versioning, human annotation,
experiment runs. Argilla is more annotation-focused and adds infra weight
(Elasticsearch). Decision: start with Langfuse, add Argilla later only if its
annotation UX is insufficient.

---

## Phase 0 — Recon (no code, ~15 min)

**Goal:** decide self-host vs. Cloud based on actual VM headroom.

- SSH to VM: `free -m`, `df -h /`, `sudo docker stats --no-stream`
- Decision matrix:
  - Free RAM ≥ 4 GB **and** disk ≥ 30 GB free → self-host on same VM
  - Tighter → either upgrade VM (e2-standard-4), put Langfuse on a second small VM, or **Cloud**
- If Cloud is chosen: enable PII redaction in the SDK before any trace ships off-box

**Done when:** decision recorded in this file (one paragraph at the bottom).

---

## Phase 1 — Instrument the bot (~2 hours, touches 3 files)

**Goal:** every LLM call (router/planner/responder) becomes a Langfuse generation,
grouped by Telegram chat as a trace.

- Add `langfuse` to `requirements.txt`
- New file `tm_bot/llms/providers/langfuse_client.py`: lazy singleton + `trace_generation(...)` helper that swallows all errors (mirror the `_record_usage` pattern in `providers/base.py`)
- Edit `tm_bot/llms/providers/base.py`: inside `ProviderBoundModel.invoke()`, after the existing `_record_usage(...)` call, also call `trace_generation(...)` with: `messages_in`, `content_out`, `model`, `role`, `tokens`, `latency`, `error_type`, plus `user_id` / `chat_id` (extend `LLMInvokeOptions` to carry them)
- Env vars in `/opt/zana-config/.env.prod`: `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_REDACT_PII` (bool)
- Small `redact()` helper for PII (phone, email, URLs) gated by that flag

**Risks:**
- Telegram message content in traces = sensitive. Default `LANGFUSE_REDACT_PII=true` for Cloud, `false` for self-host.
- Fire-and-forget — never block bot response on Langfuse.

**Done when:** test message in dev shows up as one trace with all 3 generations (router/planner/responder) linked.

---

## Phase 2 — Deploy Langfuse (1–3 hours depending on path)

### Self-host path (committed in this repo)

The compose file already includes the six services. Steps to bring them up on the VM:

**1. DNS.** In your DNS provider (or GCP Cloud DNS), add an A record:
   `langfuse.xaana.club` → `34.163.204.33`

**2. Create persistent storage directories on the VM:**
```
sudo mkdir -p /srv/langfuse-postgres /srv/langfuse-clickhouse-data \
              /srv/langfuse-clickhouse-logs /srv/langfuse-minio
sudo chown -R 999:999 /srv/langfuse-postgres
sudo chown -R 101:101 /srv/langfuse-clickhouse-data /srv/langfuse-clickhouse-logs
sudo chown -R 1000:1000 /srv/langfuse-minio
```

**3. Generate secrets (run on the VM, paste into the env file in step 4):**
```
echo "LANGFUSE_DB_PASSWORD=$(openssl rand -hex 16)"
echo "LANGFUSE_CLICKHOUSE_PASSWORD=$(openssl rand -hex 16)"
echo "LANGFUSE_REDIS_PASSWORD=$(openssl rand -hex 16)"
echo "LANGFUSE_MINIO_PASSWORD=$(openssl rand -hex 16)"
echo "NEXTAUTH_SECRET=$(openssl rand -base64 32)"
echo "SALT=$(openssl rand -base64 32)"
echo "ENCRYPTION_KEY=$(openssl rand -hex 32)"
echo "LANGFUSE_INIT_USER_PASSWORD=$(openssl rand -hex 16)"
```

**4. Create `/opt/zana-config/.env.langfuse`** (read by `langfuse-web` and `langfuse-worker`):
```
# DB / queue / storage
DATABASE_URL=postgresql://langfuse:<LANGFUSE_DB_PASSWORD>@langfuse-postgres:5432/langfuse
CLICKHOUSE_MIGRATION_URL=clickhouse://langfuse-clickhouse:9000
CLICKHOUSE_URL=http://langfuse-clickhouse:8123
CLICKHOUSE_USER=clickhouse
CLICKHOUSE_PASSWORD=<LANGFUSE_CLICKHOUSE_PASSWORD>
CLICKHOUSE_CLUSTER_ENABLED=false
REDIS_HOST=langfuse-redis
REDIS_PORT=6379
REDIS_AUTH=<LANGFUSE_REDIS_PASSWORD>
LANGFUSE_S3_EVENT_UPLOAD_BUCKET=langfuse
LANGFUSE_S3_EVENT_UPLOAD_REGION=auto
LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID=minio
LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY=<LANGFUSE_MINIO_PASSWORD>
LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT=http://langfuse-minio:9000
LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE=true
LANGFUSE_S3_EVENT_UPLOAD_PREFIX=events/

# Auth / encryption
NEXTAUTH_URL=https://langfuse.xaana.club
NEXTAUTH_SECRET=<NEXTAUTH_SECRET>
SALT=<SALT>
ENCRYPTION_KEY=<ENCRYPTION_KEY>

# Telemetry (vendor-side, harmless to disable)
TELEMETRY_ENABLED=false

# First-boot admin user (only used until first login)
LANGFUSE_INIT_USER_NAME=Javad
LANGFUSE_INIT_USER_EMAIL=amiryan.j@gmail.com
LANGFUSE_INIT_USER_PASSWORD=<LANGFUSE_INIT_USER_PASSWORD>
LANGFUSE_INIT_PROJECT_NAME=xaana
```

**5. Append the password vars from step 3 to `/opt/zana-config/.env.prod`** (so docker-compose can interpolate them into `langfuse-postgres`/`langfuse-clickhouse`/etc.):
```
LANGFUSE_DB_PASSWORD=...
LANGFUSE_CLICKHOUSE_PASSWORD=...
LANGFUSE_REDIS_PASSWORD=...
LANGFUSE_MINIO_USER=minio
LANGFUSE_MINIO_PASSWORD=...
```

**6. Issue the Let's Encrypt cert** (HTTP-01 needs port 80 reachable; nginx is up so this should work in webroot mode, but easiest is standalone with nginx briefly stopped):
```
sudo certbot certonly --standalone -d langfuse.xaana.club \
  --email amiryan.j@gmail.com --agree-tos --non-interactive \
  --pre-hook "sudo docker stop zana-nginx" \
  --post-hook "sudo docker start zana-nginx"
```

**7. Bring up the stack:**
```
cd /opt/zana-bot
sudo docker compose up -d langfuse-postgres langfuse-clickhouse langfuse-redis langfuse-minio
sleep 10
sudo docker compose up -d langfuse-web langfuse-worker
sudo docker compose restart zana-nginx
```

**8. Wire the bot to it.** Append to `/opt/zana-config/.env.prod`:
```
LANGFUSE_HOST=https://langfuse.xaana.club
LANGFUSE_PUBLIC_KEY=pk-lf-...    # generated in step 9
LANGFUSE_SECRET_KEY=sk-lf-...    # generated in step 9
LANGFUSE_REDACT_PII=false        # we self-host; raw chat content is fine
```

**9. First login + create project keys.**
   - Open `https://langfuse.xaana.club`, log in with the email/password from step 4.
   - Go to *Settings → API Keys → Create new key*.
   - Paste public + secret keys into `.env.prod` (step 8), then:
```
cd /opt/zana-bot
sudo docker compose up -d --force-recreate zana-prod zana-webapp
```

**10. Smoke test.** Send Xaana a Telegram message; within ~10s, the trace should appear under *Tracing* in the Langfuse UI with three generations linked (router/planner/responder).

### Cloud path (alternative, no compose changes)

- Sign up at https://cloud.langfuse.com, create a project, copy keys.
- Append to `/opt/zana-config/.env.prod`:
```
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_REDACT_PII=true   # required: chat content leaves the VM
```
- Recreate prod containers: `sudo docker compose up -d --force-recreate zana-prod zana-webapp`.
- Skip steps 1–7 entirely. Skip Phase 2 nginx work.

**Done when:** dashboard at `https://langfuse.xaana.club` (or cloud) shows live traces and the admin can log in.

---

## Phase 3 — Admin panel hooks (~1 hour, touches 2 files)

**Goal:** zero re-implementation of Langfuse UI; just deep-link from the admin panel.

- `webapp_frontend/src/components/admin/StatsTab.tsx`: in the LLM Usage section, add an "Open in Langfuse →" link per row (URL: `${LANGFUSE_HOST}/project/<id>/traces?model=...`)
- New `tm_bot/webapp/routers/admin.py` endpoint `POST /admin/traces/{trace_id}/flag` that calls Langfuse's score API to mark a trace for review (admin-only)
- *(Optional)* Bot-side: `/feedback` slash command in group chats records a Langfuse score against the most recent assistant message

**Done when:** clicking "Open in Langfuse" from Stats tab takes you to the right trace, and flagging works end-to-end.

---

## Phase 4 — Dataset workflow (process, not code)

**Goal:** the manual loop — find bad answers, write better ones, build a dataset.

1. In Langfuse, create datasets: `xaana_club_responses_v1`, `xaana_router_v1`
2. Triage flagged traces; for each: write the "ideal" answer in the annotation panel; save as a dataset item with input + expected_output
3. When ready to test a prompt change or model swap: run a Langfuse experiment over the dataset, score with LLM-as-judge or manual review, compare runs

**Done when:** ≥ 30 dataset items exist and at least one experiment-run comparison has been recorded.

---

## Phase 5 — Argilla? Defer.

Revisit only if (a) we need preference tuning (A vs. B response ranking at scale) or (b) we want non-technical annotators with a finer-grained UI than Langfuse offers.

---

## Safety summary

- **PII redaction flag** before any data ships off-box
- **Auth on Langfuse UI** — never expose unauthenticated, even self-host
- **Fire-and-forget instrumentation** — bot never blocks on Langfuse
- **Separate DB** for Langfuse — never reuse the Neon prod URL
- **Backups encrypted** if self-host (Langfuse data contains full chat content)

## Day-1-on-a-new-server safety

The integration is built so that nothing here blocks bringing the bot up on a
fresh server before Langfuse itself is configured:

1. **Lazy import.** `providers/base.py::_emit_trace()` imports `langfuse_client`
   inside its try/except. A missing module, missing `langfuse` pip package, or
   broken import all degrade silently — the bot keeps running.
2. **Lazy client construction.** `langfuse_client._get_client()` returns `None`
   if any of `LANGFUSE_HOST`/`PUBLIC_KEY`/`SECRET_KEY` are unset; trace calls
   become no-ops.
3. **Compose profile gate.** All six langfuse services have
   `profiles: ["langfuse"]` so `docker compose up -d` (or the existing GH
   Actions deploys, which name `zana-prod`/`zana-staging`/`zana-webapp`
   explicitly) won't pull or start them. Activate with
   `docker compose --profile langfuse up -d`.
4. **nginx block commented out.** The `langfuse.xaana.club` server block in
   `nginx.conf` is disabled by default to prevent nginx from refusing to start
   on a server where the cert hasn't been issued yet. Uncomment after the cert
   is in place (see Phase 2 step 6).

To roll out on a new server: deploy bot first, verify it works, *then* run the
Phase 2 steps to enable Langfuse.

---

## Order of work

Phase 0 → 1 → 2 → 3 → 4.
Phase 1 (instrumentation) is gated only on Phase 0's keys, so it can run in parallel with Phase 2 if Cloud is chosen.

---

## Decisions log

*(append a one-paragraph entry here as each phase resolves)*

- *(empty)*
