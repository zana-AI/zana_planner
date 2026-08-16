# Xaana: GCP → Hetzner Migration Plan

**Purpose:** Be ready to move Xaana off Google Cloud onto a single ~€8–10/mo Hetzner VPS
if the credit-extension request is rejected. Everything self-hosted in one Docker Compose
stack (Postgres and Qdrant included — no managed services), zero data left behind on GCP,
and GCP-specific AI APIs dropped in favour of already-wired alternatives.

_Last updated: 2026-07-01. Author: prep session with Claude._

---

## 0. TL;DR

- **Target box:** Hetzner **CPX21** (3 vCPU, 4 GB RAM, 80 GB NVMe, ~€8/mo) in Falkenstein/Nuremberg.
  (CX22 at ~€4.5 also works but 4 GB is the floor given the current ~1.9 GB container footprint + Postgres.)
- **Everything in one `docker-compose` stack:** nginx (TLS), bot, webapp, mcp, hydra + its postgres,
  qdrant, stats, **+ new `postgres` service** replacing Cloud SQL.
- **Files:** <600 MB total. Store on the VM disk (drop object storage entirely) — `object_storage_service.py`
  already has an S3 abstraction, but at this scale a local volume is simpler. (Optional: Cloudflare R2, 10 GB free.)
- **Drop GCP AI services** (Speech, TTS, Translate, Gemini/Vertex). Replace with local models or the
  cheap/already-wired providers (see §3).
- **Estimated Hetzner cost:** ~€8–10/mo all-in, vs. ~$75–90/mo on GCP once the credit is gone.

---

## 1. Current GCP footprint (Xaana-only)

| Resource | Now | Fate |
|---|---|---|
| VM `vm-telegram-bots` (e2-medium, ew9-c) | runs the whole compose stack | replaced by Hetzner box |
| Boot disk 160 GB pd-ssd | oversized | not migrated (rebuild fresh) |
| Cloud SQL `zana-prod` (db-f1-micro, Postgres 18) | app DB `zana` | → Postgres **container** |
| Qdrant (container on the VM) | vector store `content_chunks_v1` | → Qdrant container (re-embed) |
| GCS `zana_bucket_01` (4.9 MB) | misc files / dumps | download → VM disk, then delete |
| GCS `…-podcast-staging` (550 MB) | podcast/content assets | verify needed, download, then delete |
| Static IP `zana-vm1-ip` | 34.163.204.33 | release after DNS cutover |
| Snapshot policy `zana-weekly-keep7` | backups of boot disk | delete after teardown |

> The GCP **project `boreal-furnace-428317-p5` is SHARED** with other people's VMs (bondra, hossein,
> mohammad, nationhug, dideo). **Do NOT delete the project or its billing** — only delete Xaana's own
> resources. Warn the other owners that once the credit lapses, their usage bills the card too.

---

## 2. GCP service dependencies in the code (grounded)

From `requirements.txt` + source:

| GCP service | Package | Used in | Replacement on Hetzner |
|---|---|---|---|
| Cloud SQL Postgres | (network) | `db/postgres_db.py`, `DATABASE_URL_PROD` | **Postgres container** (§4.3) |
| Speech-to-Text | `google-cloud-speech` | `services/learning_pipeline/transcription_service.py`, `voice_service.py` | **Groq Whisper API** (already have Groq) or local `faster-whisper` (base/small, CPU) |
| Text-to-Speech | `google-cloud-texttospeech` | `services/gcp_tts_service.py`, `voice_service.py` | **Piper** (local, free) or **drop voice replies** (OK per owner) |
| Translate | `google-cloud-translate` | `handlers/translator.py` | **LLM-based translate** via existing provider, or drop |
| Gemini (LLM) | `google-genai`, `langchain-google-genai` | `llms/llm_gemini.py`, `llms/providers/gemini_adapter.py`, factory | Switch default provider to **Groq/Anthropic/etc.** (already wired via `llms/providers/factory.py`) |
| Vertex embeddings | `google-cloud-aiplatform` | `services/learning_pipeline/embedding_service.py` (`gemini-embedding-001`) | **Option A:** keep Gemini embeddings via **AI Studio API key** (not GCP-billed) → no re-embed. **Option B:** local `sentence-transformers` (e.g. `bge-m3`, multilingual) → **re-embed all content** |
| BigQuery | `google-cloud-bigquery` | (verify — likely analytics) | drop / replace with Postgres queries |
| Object storage | `google-cloud-storage` + S3 abstraction | `services/object_storage_service.py` | local VM volume (or R2). Abstraction already S3-based |

**Only real gotcha:** changing the embedding model changes vector dimensions, so the Qdrant
`content_chunks_v1` collection must be **rebuilt/re-embedded**. Content is small, so this is cheap.
Choosing **Option A** (Gemini embeddings via AI Studio key) avoids re-embedding entirely.

---

## 3. Decisions to lock before cutover

1. **Embeddings:** A) keep `gemini-embedding-001` via AI Studio key (no re-embed, still "Google" but off-GCP),
   or B) go fully local `sentence-transformers` (re-embed). _Recommend A for least risk, B for full independence._
2. **STT (voice):** Groq Whisper API (simplest, cheap) vs local `faster-whisper` (no API cost, uses CPU/RAM).
3. **TTS:** Piper local vs drop voice-out. _Recommend Piper if Persian/French quality is acceptable; else drop._
4. **Translate:** LLM-based vs drop.
5. **Object files:** local volume (recommended at this size) vs R2.

---

## 4. Migration runbook

### 4.1 Provision (30–60 min)
- Create Hetzner CPX21, Ubuntu 22.04/24.04, add SSH key, enable the firewall (allow 22/80/443).
- Install Docker + compose plugin. Create a non-root deploy user.
- Point a **low-TTL** DNS record for `xaana.club` (set TTL to 300 a day before, so cutover is fast).

### 4.2 Bring the stack over
- `git clone` the repo on the box; copy env files (from `/opt/zana-config/.env.*`) — **do not commit secrets**.
- Add a `postgres` service to `docker-compose.yml` with a named volume `pgdata` and Postgres 18.
- Adjust `DATABASE_URL_PROD` / `DATABASE_URL_STAGING` to point at the local `postgres` service
  (both are now on GCP/Cloud SQL — staging no longer uses Neon).

### 4.3 Migrate the database
- Final dump at cutover (freeze writes briefly):
  `gcloud sql export sql zana-prod gs://zana_bucket_01/zana-final.sql.gz --database=zana`
  → download → `gunzip -c zana-final.sql.gz | docker compose exec -T postgres psql -U <user> -d zana`.
- Run `alembic ... upgrade head` inside the app container; confirm it reports the latest revision.
- Sanity-check row counts vs. source.

### 4.4 Migrate Qdrant + embeddings
- Option A (keep Gemini embeddings): copy the Qdrant storage volume from the old VM
  (`/var/lib/docker/volumes/...qdrant...`) via `rsync`, OR just re-index.
- Option B (local embeddings): stand up Qdrant empty, set the new embedding model env, run the
  indexing pipeline to **re-embed all content** from source rows.

### 4.5 Migrate files
- `gcloud storage rsync -r gs://zana_bucket_01 ./data/objects/` and same for the podcast bucket
  (if still needed) → mount into the relevant container as a volume, set the local path/env.

### 4.6 Bring it up + verify
- `docker compose up -d`; issue Let's Encrypt cert via nginx/certbot.
- **Stop the old GCP bot first** (avoid double Telegram polling), then repoint DNS to the Hetzner IP.
- Smoke tests: `/api/health` 200; send a Telegram text message; a voice message (STT/TTS path);
  a translate path; create/complete a promise; check the Mini App loads; verify reminders fire.
- Watch logs 24–48 h.

---

## 5. "No data left behind" — GCP teardown checklist (only after Hetzner is verified)

- [ ] Final DB dump imported + verified on Hetzner
- [ ] Qdrant migrated or re-embedded + search works
- [ ] `zana_bucket_01` and podcast bucket fully downloaded + verified, then **deleted**
- [ ] Secrets/env copied
- [ ] Delete Cloud SQL **`zana-prod`** (take a final export first)
- [ ] Delete VM **`vm-telegram-bots`** + its boot disk (`disk-20260101-zana-2026-m`)
- [ ] Release static IP **`zana-vm1-ip`**
- [ ] Delete Xaana snapshots + policy **`zana-weekly-keep7`**; delete `predelete-*` snapshots
- [ ] Revoke/delete any API keys + service-account grants we created (incl. the Cloud SQL SA
      bucket binding added 2026-07-01)
- [ ] Confirm no Xaana rows remain in shared buckets (`boreal-furnace-vertex-ew9` was empty)
- [ ] **Do NOT** delete the shared project or other owners' resources — notify them instead

---

## 6. Backups on Hetzner (replace GCP snapshots)
- Nightly `pg_dump` → gzip → off-box (R2/B2 or `scp` to another host). Keep 7–14.
- Weekly Qdrant snapshot to the same store.
- Optional: Hetzner VPS snapshot (~20% of box price) for whole-disk restore.

---

## 7. Cost comparison

| | GCP (credit gone) | Hetzner |
|---|---|---|
| Compute | e2-medium ~$28 | CPX21 ~€8 |
| DB | Cloud SQL f1-micro ~$9 | in-VM Postgres — €0 |
| Disk | 160 GB pd-ssd ~$27 | included in VPS |
| Static IP | ~$4 | included |
| AI APIs (STT/TTS/embed/LLM) | metered | Groq/local — near €0 |
| Backups | snapshots | ~€1.5 |
| **Total** | **~$75–90/mo** | **~€10/mo (~$11)** |

---

## 8. Risks & mitigations
- **Embedding-space change** → must re-embed (Option B). Mitigate by choosing Option A, or re-embed (cheap at this size).
- **Local STT/TTS quality** for Persian/French — validate before dropping the GCP path; keep Groq Whisper as fallback.
- **Double Telegram polling** during cutover → always stop the old instance before starting the new one.
- **DNS propagation** → pre-lower TTL; keep the GCP box running until the new one is confirmed.
- **4 GB RAM ceiling** → Postgres + Qdrant + app must fit; add a 2–4 GB swapfile (as we did on GCP).
- **Shared GCP project** → deleting Xaana resources won't stop others' spend; coordinate with them.
