#!/bin/bash
# Test if web app dependencies are available and can start

echo "=== Testing Web App Dependencies ==="
echo ""

echo "[1/4] Testing uvicorn import:"
sudo docker exec zana-staging python -c "import uvicorn; print('✓ uvicorn OK')" 2>&1 || echo "✗ uvicorn FAILED"
echo ""

echo "[2/4] Testing fastapi import:"
sudo docker exec zana-staging python -c "import fastapi; print('✓ fastapi OK')" 2>&1 || echo "✗ fastapi FAILED"
echo ""

echo "[3/4] Testing webapp.api import:"
sudo docker exec zana-staging python -c "from tm_bot.webapp.api import create_webapp_api; print('✓ webapp.api import OK')" 2>&1 || echo "✗ webapp.api import FAILED"
echo ""

echo "[4/4] Checking for 'Web app server started' in logs:"
sudo docker logs zana-staging 2>&1 | grep -i "web app server started" || echo "✗ 'Web app server started' log NOT found"
echo ""

echo "[5/5] Checking for any webapp-related errors:"
sudo docker logs zana-staging 2>&1 | grep -i -E "(webapp|uvicorn|fastapi)" | tail -10
echo ""

echo "=== Full recent logs (last 20 lines) ==="
sudo docker logs --tail=20 zana-staging 2>&1
