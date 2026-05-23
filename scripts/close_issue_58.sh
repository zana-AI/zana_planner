#!/usr/bin/env bash
# Close GitHub issue #58 with resolution comment.
# Requires: gh auth login (once)

set -euo pipefail

REPO="zana-AI/zana_planner"
ISSUE=58

gh issue comment "$ISSUE" --repo "$REPO" --body "$(cat <<'EOF'
**Resolved** — standalone mobile/browser login is working.

### What shipped (9862f37)
- **Telegram Login Widget** at `/api/auth/telegram-login` for users opening xaana.club outside the Mini App (Safari/Chrome, home-screen PWA).
- **DB-backed sessions** in `auth_sessions` (migration `022_add_auth_sessions`) so logins survive deploys/restarts; API auth via `Authorization: Bearer <session_token>`.

### Ops note (follow-up from testing)
The error reported below (`relation "auth_sessions" does not exist`) was **schema drift**: code was deployed before Alembic `022` ran on the DB. After `alembic upgrade head` (or `python scripts/run_migrations.py`) on staging/prod, login succeeded.

Closing as complete.
EOF
)"

gh issue close "$ISSUE" --repo "$REPO" --comment ""
echo "Issue #$ISSUE closed."
