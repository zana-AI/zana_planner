---
name: new-challenge
description: Build a new challenge (async flashcard/quiz content) on the Xaana challenges engine — schema, reusable push pipeline, and deploy/ops gotchas learned from the Atena French-quiz build.
---

# new-challenge

Guide for standing up a new challenge (quiz/flashcard content) on Xaana's challenges engine — either a one-time bulk content load or a recurring auto-generated feed. Written after building the first real one ("French with Atena"), which lives in `scripts/push_atena_quiz.py` as a working reference implementation.

> **Invoke:** `/new-challenge` when starting work on a new challenge (new topic, new creator/source, new content type).

## 1. Resolve design questions FIRST — don't assume

Before writing any code or migration, get explicit answers from the user on:

1. **Host/brand** — who is this challenge attributed to? A real creator/partner (like Atena), or admin/Xaana-authored? This is `challenges.host_user_id` — must be a real `users.user_id`, shown to players for trust transfer.
2. **Format** — MCQ (`activity_type='multiple_choice'`, needs `options` + `back` matching one option) or flashcard (`activity_type='flashcard'`, just `front`/`back`, self-graded)?
3. **Cadence** — `daily` drip-fed one deck at a time (via `release_at` scheduling, like Atena), or a self-paced bulk load where the user can play through many decks immediately? Check `challenges.cadence` CHECK constraint (`'daily'`/`'weekly'`) before assuming other values are allowed.
4. **Volume & batching** — how many total items, and how many per deck? A 500-item corpus doesn't want 10/day (50 days) — batch size should match how the content is actually meant to be consumed.
5. **Source quality** — is the source material curated, or raw (scraped page, ASR transcript, PDF)? Raw sources need an explicit fact-check/cleanup pass before anything is published — assume nothing from a machine transcript is correct without checking (an ASR transcript on a real prior job mis-transcribed "Louis XVI" as "Louis XV" for a French Revolution date — a wrong-but-plausible-sounding fact is worse than an obviously broken one).

## 2. Schema (already built, reuse — don't add new tables for a new challenge)

- `challenges` → `challenge_decks` → `challenge_items` (MCQ items: `front`/`back`/`options` JSON array; `back` must equal one of `options` exactly) → `challenge_participants`, `challenge_attempts`.
- `challenge_decks.release_at` gates visibility — the "due deck" query only serves a deck once `release_at <= now()`. This is the built-in scheduling mechanism; don't build a separate cron for "don't show this yet."
- `challenge_decks.source_ref` — nullable provenance pointer (a URL, file path, whatever identifies the source), used for dedup so re-runs don't regenerate the same content.
- `tm_bot/repositories/challenges_repo.py` (`ChallengesRepository`): `create_challenge()`, `add_deck(challenge_id, title, items, position, release_at, source_ref)`, `get_source_refs()`, `get_latest_release_at()`, `get_deck_count()`, `delete_deck()` (guarded — refuses if the deck is already live or has attempts), `leaderboard()`.
- `tm_bot/webapp/routers/challenges.py`: user play endpoints + `POST/DELETE /api/admin/challenges/{id}/decks`.

## 3. Reusable pipeline pattern

Copy the shape of `scripts/push_atena_quiz.py` rather than writing push logic from scratch:
1. Dedup check — read `get_source_refs(challenge_id)`, skip anything already used.
2. Generate/curate content into the deck JSON shape (`title`, `source_ref`, `items: [{front, back, options, example}]`).
3. Validate — item count matches expectation, every `back` is in its `options`, answer-letter distribution isn't skewed (for MCQ).
4. Compute `release_at` (queue-append: one day after the latest existing deck, but never in the past — skip forward past any gap).
5. Publish via `ChallengesRepository.add_deck(...)`.

For a **one-time bulk load** (like a 500-question corpus), you likely don't need the "one deck per day" drip — decide batch size in step 1's design questions and just call `add_deck` in a loop with sequential `release_at` (or all `release_at=None`/immediate, if the content is meant to be available all at once).

## 4. Operational gotchas (learned the hard way, don't re-learn them)

- **Prod DB/container access**: `ssh root@169.58.186.195 "..."` (Contabo VPS — see the `vm-ops` skill), then `docker exec -i zana-prod python3 <script>`. You are root; no `sudo`. For any script/JSON payload, base64-encode and pipe it: `echo $B64 | base64 -d | ssh root@169.58.186.195 "docker exec -i zana-prod python3 -"`.
  > Anything in older notes about `gcloud compute ssh vm-telegram-bots --zone=europe-west9-c` is **stale** — the GCP VM was suspended in Aug 2026 when the credit lapsed and the stack moved to Contabo. There is no `gcloud` in this loop any more.
- **A scheduled daily push is now genuinely possible.** The old blocker was `gcloud auth login` needing a human browser OAuth flow with a ~1h token TTL, which made unattended automation impossible. Plain SSH key auth has no such expiry, so a cron/systemd timer on the VM can drive the daily push directly. (An HTTPS admin endpoint with a static service token is still the cleaner long-term shape.)
- **`deploy-prod.yml` has a pre-existing bug**: its remote check (`docker images | grep -q staging`) runs as a non-sudo SSH user without docker-group access, so it always reports a false "staging image not found." Workaround — promote manually:
  ```
  docker tag zana-ai-bot:prod zana-ai-bot:prod-rollback
  docker tag zana-ai-bot:staging zana-ai-bot:prod
  cd /opt/zana-bot/zana_planner && docker compose up -d --force-recreate --no-build zana-prod
  ```
  (Note the **nested** repo path — `/opt/zana-bot` alone holds no compose file.)
- **Deploy path**: push to `master` → `deploy-staging.yml` auto-rebuilds `zana-staging` (bot) **and** `zana-webapp`. There's no separate staging/prod split for the webapp — it's prod-facing (`xaana.club`) on every master push. Only the bot (`zana-prod`) needs the separate manual promotion above.
- **Migrations**: sequential `NNN_description.py` under `tm_bot/db/alembic/versions/`, apply via the `migrate` skill (staging then prod) — never auto-applied by the deploy workflows.

## 5. Verification checklist before calling it done

- Dry-run/validate the generated content before any DB write.
- Confirm dedup works (skip a source already used).
- Confirm `release_at` scheduling matches the chosen cadence (check by querying `challenge_decks` directly, not just trusting script output).
- Print the actual published questions back from the DB (not from local generation state) to confirm what's live matches what was intended.
- If a cancel/edit path matters for this challenge, test `delete_deck` on a throwaway future deck and confirm it refuses to delete anything already played.
