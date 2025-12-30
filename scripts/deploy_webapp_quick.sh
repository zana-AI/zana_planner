#!/bin/bash
# =============================================================================
# Quick deployment script (minimal prompts)
# Assumes nginx and SSL are already configured
#
# Usage: bash scripts/deploy_webapp_quick.sh
# =============================================================================

set -e

PROJECT_DIR="/opt/zana-bot/zana_planner"
cd "$PROJECT_DIR"

echo "🚀 Quick deployment - Building and restarting..."

# Build frontend
if [ -d "webapp_frontend" ]; then
    cd webapp_frontend
    npm run build
    cd ..
fi

# Build and restart Docker
docker compose build zana-prod
docker compose up -d zana-prod

echo "✅ Deployment complete!"
echo "View logs: docker compose logs -f zana-prod"

