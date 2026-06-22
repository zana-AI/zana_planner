#!/usr/bin/env bash
#
# local_preview.sh — Launch the Xaana webapp BACKEND locally for previewing/editing.
#
# Runs the FastAPI webapp (run_webapp_local:app) in Docker on :8080, pointed at the
# REAL prod database, with dev-admin auth enabled so you can log in as your admin
# user WITHOUT Telegram. The React frontend is served separately by the Vite dev
# server (:5173) so edits hot-reload — see the `local-preview` skill / README below.
#
# Why Docker: the repo's Python pins (langchain 1.2.x, uvloop, etc.) don't match the
# local conda envs and uvloop has no Windows wheels, so a host venv is unreliable.
# The Dockerfile.webapp image is the supported, reproducible way to run the backend.
#
# Usage:
#   bash scripts/local_preview.sh           # ensure image, (re)start backend on :8080
#   bash scripts/local_preview.sh --build   # force a rebuild of the image first
#   bash scripts/local_preview.sh --stop    # stop & remove the backend container
#   bash scripts/local_preview.sh --logs    # tail backend container logs
#
# Env target: defaults to the PROD database (DATABASE_URL_PROD in .env). To use the
# staging DB instead, set PREVIEW_DB=staging.
#
set -euo pipefail

# --- resolve repo root (this script lives in scripts/) -----------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

IMAGE="zana-webapp-local"
CONTAINER="zana-webapp-local"
PORT="${PREVIEW_PORT:-8080}"
ENV_FILE="${PREVIEW_ENV_FILE:-.env}"

# --- helpers -----------------------------------------------------------------
read_env() {  # read_env KEY  -> prints first uncommented value from $ENV_FILE
  grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- \
    | sed -E 's/^["'"'"']//; s/["'"'"']$//' | tr -d '\r'
}

die() { echo "ERROR: $*" >&2; exit 1; }

# --- subcommands -------------------------------------------------------------
case "${1:-}" in
  --stop)
    docker rm -f "$CONTAINER" >/dev/null 2>&1 && echo "Stopped $CONTAINER." || echo "$CONTAINER not running."
    exit 0 ;;
  --logs)
    exec docker logs -f "$CONTAINER" ;;
esac

FORCE_BUILD=0
[ "${1:-}" = "--build" ] && FORCE_BUILD=1

# --- preconditions -----------------------------------------------------------
docker info >/dev/null 2>&1 || die "Docker daemon not reachable. Start Docker Desktop and retry."
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found in $ROOT_DIR."

# --- pick database -----------------------------------------------------------
PREVIEW_DB="${PREVIEW_DB:-prod}"
if [ "$PREVIEW_DB" = "staging" ]; then
  DB_URL="$(read_env DATABASE_URL_STAGING)"
else
  DB_URL="$(read_env DATABASE_URL_PROD)"
fi
[ -n "$DB_URL" ] || die "Could not read DATABASE_URL_${PREVIEW_DB^^} from $ENV_FILE."

# admin user to impersonate via dev-admin login (first id in ADMIN_IDS, fallback default)
ADMIN_ID="${WEBAPP_DEV_ADMIN_USER_ID:-$(read_env ADMIN_IDS | tr ',' '\n' | head -1)}"
ADMIN_ID="${ADMIN_ID:-900000001}"

echo ">> DB target : $PREVIEW_DB ($(echo "$DB_URL" | sed -E 's#://[^@]+@#://***@#'))"
echo ">> Admin user: $ADMIN_ID (dev-admin login impersonates this id)"

# --- build image if needed ---------------------------------------------------
if [ "$FORCE_BUILD" = "1" ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo ">> Building $IMAGE (Dockerfile.webapp)... (first build installs deps, be patient)"
  DOCKER_BUILDKIT=1 docker build -f Dockerfile.webapp -t "$IMAGE" .
else
  echo ">> Reusing existing image $IMAGE (pass --build to rebuild)."
fi

# --- (re)start container -----------------------------------------------------
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
echo ">> Starting backend on http://127.0.0.1:$PORT ..."
# --env-file supplies the real keys (the backend needs LLM creds at import time);
# the -e overrides come AFTER so they win: run as `staging` (to allow dev auth)
# against the chosen DB, with dev-admin login enabled for $ADMIN_ID.
docker run -d --name "$CONTAINER" -p "$PORT:8080" \
  --env-file "$ENV_FILE" \
  -e ENVIRONMENT=staging \
  -e "DATABASE_URL_STAGING=$DB_URL" \
  -e WEBAPP_DEV_AUTH_ENABLED=1 \
  -e "WEBAPP_DEV_ADMIN_USER_ID=$ADMIN_ID" \
  "$IMAGE" >/dev/null

# --- wait for health ---------------------------------------------------------
echo -n ">> Waiting for /api/health "
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
    echo " — healthy ✓"
    break
  fi
  echo -n "."; sleep 2
done
curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 \
  || { echo; echo "Backend did not become healthy. Logs:"; docker logs --tail 40 "$CONTAINER"; exit 1; }

# frontend deps hint (script is backend-only, but flag the common "fresh PC" gap)
FE_HINT="npm --prefix webapp_frontend run dev   (serves :5173)"
if [ ! -d "webapp_frontend/node_modules" ]; then
  FE_HINT="npm --prefix webapp_frontend install   (node_modules missing!) then: npm --prefix webapp_frontend run dev"
fi

cat <<EOF

Backend is up on http://127.0.0.1:$PORT  (proxied by Vite under /api).

Next:
  1. Start the frontend:  $FE_HINT
  2. Open  http://localhost:5173/dev-admin  and click "Enter as dev admin".
     -> logs you in as user $ADMIN_ID with real $PREVIEW_DB data, no Telegram needed.
  3. Edit code under webapp_frontend/src — Vite hot-reloads.

Stop the backend:  bash scripts/local_preview.sh --stop
EOF
