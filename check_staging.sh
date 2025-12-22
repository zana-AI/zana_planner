#!/bin/bash
# Quick diagnostic script for staging (using docker, not docker compose)

echo "=== Checking Staging Container ==="
echo ""

# 1. Check container status
echo "[1/4] Container status:"
sudo docker ps -a | grep zana-staging || echo "Container not found"
echo ""

# 2. Check if port 8081 is mapped
echo "[2/4] Port mapping:"
sudo docker ps | grep zana-staging | grep 8081 || echo "Port 8081 not mapped"
echo ""

# 3. Check recent logs
echo "[3/4] Recent logs (last 30 lines):"
sudo docker logs --tail=30 zana-staging 2>&1 | tail -30
echo ""

# 4. Test connection
echo "[4/4] Testing connection:"
echo "Testing localhost:8081..."
curl -v http://localhost:8081/api/health 2>&1 | head -20
echo ""

echo "=== Summary ==="
if sudo docker ps | grep -q zana-staging; then
    echo "✓ Container is running"
else
    echo "✗ Container is NOT running"
    echo "Check why it stopped: sudo docker logs zana-staging"
fi
