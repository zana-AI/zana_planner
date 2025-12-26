#!/bin/bash
# Quick fix script for staging deployment
set -e

echo "=== Checking Staging Status ==="
echo ""

# Step 1: Check if container exists and status
echo "[1/5] Checking container status..."
if docker ps -a | grep -q zana-staging; then
    echo "Container exists. Status:"
    docker ps -a | grep zana-staging
else
    echo "Container does not exist yet."
fi
echo ""

# Step 2: Check if .env.staging exists
echo "[2/5] Checking environment file..."
if [ -f "/opt/zana-config/.env.staging" ]; then
    echo "✓ .env.staging exists"
    if grep -q "BOT_TOKEN" /opt/zana-config/.env.staging; then
        echo "✓ BOT_TOKEN is set"
    else
        echo "✗ BOT_TOKEN is missing!"
    fi
else
    echo "✗ .env.staging NOT FOUND at /opt/zana-config/.env.staging"
    echo "Creating from backup if available..."
    if [ -f "backup_data/.env.staging" ]; then
        sudo mkdir -p /opt/zana-config
        sudo cp backup_data/.env.staging /opt/zana-config/.env.staging
        echo "✓ Copied from backup_data/.env.staging"
    else
        echo "✗ No backup found. You need to create /opt/zana-config/.env.staging"
    fi
fi
echo ""

# Step 3: Check data directory
echo "[3/5] Checking data directory..."
if [ -d "/srv/zana-users-staging" ]; then
    echo "✓ Directory exists"
    ls -ld /srv/zana-users-staging
else
    echo "✗ Directory /srv/zana-users-staging does not exist"
    echo "Creating it..."
    sudo mkdir -p /srv/zana-users-staging
    sudo chown -R 1002:1002 /srv/zana-users-staging 2>/dev/null || sudo chmod -R 777 /srv/zana-users-staging
    echo "✓ Created"
fi
echo ""

# Step 4: Check if we're in the right directory
echo "[4/5] Checking project directory..."
if [ -f "docker-compose.yml" ]; then
    echo "✓ Found docker-compose.yml"
    PROJECT_DIR=$(pwd)
    echo "Current directory: $PROJECT_DIR"
else
    echo "✗ docker-compose.yml not found in current directory"
    echo "Please run this script from zana_planner directory"
    exit 1
fi
echo ""

# Step 5: Try to start/restart
echo "[5/5] Starting staging container..."
echo ""

# Stop if running
docker compose stop zana-staging 2>/dev/null || true

# Remove if exists but broken
if docker ps -a | grep -q zana-staging; then
    if ! docker ps | grep -q zana-staging; then
        echo "Removing old container..."
        docker compose rm -f zana-staging 2>/dev/null || true
    fi
fi

# Build and start
echo "Building image..."
docker compose build zana-staging

echo "Starting container..."
docker compose up -d zana-staging

echo ""
echo "=== Waiting for container to start ==="
sleep 5

# Check status
echo ""
echo "=== Final Status ==="
docker compose ps zana-staging

echo ""
echo "=== Recent Logs ==="
docker compose logs --tail=20 zana-staging

echo ""
echo "=== Testing Port 8081 ==="
if curl -s http://localhost:8081/api/health > /dev/null; then
    echo "✓ Port 8081 is responding!"
    curl http://localhost:8081/api/health
else
    echo "✗ Port 8081 is not responding yet"
    echo "Check logs: docker compose logs -f zana-staging"
fi

echo ""
echo "=== Done ==="
echo "If there are errors, check logs with: docker compose logs -f zana-staging"

