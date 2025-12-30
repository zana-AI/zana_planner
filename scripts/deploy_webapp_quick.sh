#!/bin/bash
# =============================================================================
# Quick deployment script (minimal prompts)
# Assumes nginx and SSL are already configured
#
# Usage: bash scripts/deploy_webapp_quick.sh
# =============================================================================

set -e

# Auto-detect project directory
if [ -d "/opt/zana-bot/zana_planner" ]; then
    PROJECT_DIR="/opt/zana-bot/zana_planner"
elif [ -d "/opt/zana-bot" ] && [ -f "/opt/zana-bot/docker-compose.yml" ]; then
    PROJECT_DIR="/opt/zana-bot"
elif [ -f "$(pwd)/docker-compose.yml" ]; then
    PROJECT_DIR="$(pwd)"
else
    PROJECT_DIR="/opt/zana-bot/zana_planner"  # Default fallback
fi

cd "$PROJECT_DIR"

if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Error: docker-compose.yml not found in $PROJECT_DIR"
    echo "Please run this script from the project root directory"
    exit 1
fi

# Check Docker permissions
if docker info &>/dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    DOCKER_COMPOSE_CMD="sudo docker compose"
fi

echo "🚀 Quick deployment - Building and restarting..."

# Build frontend (optional - Docker will build it if npm not available)
if command -v npm &> /dev/null; then
    FRONTEND_DIR=""
    if [ -d "webapp_frontend" ]; then
        FRONTEND_DIR="webapp_frontend"
    elif [ -d "zana_planner/webapp_frontend" ]; then
        FRONTEND_DIR="zana_planner/webapp_frontend"
    fi

    if [ -n "$FRONTEND_DIR" ]; then
        cd "$FRONTEND_DIR"
        npm run build
        cd "$PROJECT_DIR"
    fi
else
    echo "⚠️  npm not found - frontend will be built in Docker"
fi

# Build and restart Docker
$DOCKER_COMPOSE_CMD build zana-prod
$DOCKER_COMPOSE_CMD up -d zana-prod

echo "✅ Deployment complete!"
echo "View logs: $DOCKER_COMPOSE_CMD logs -f zana-prod"

