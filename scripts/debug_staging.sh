#!/bin/bash
# Debug script to check what's happening inside the staging container

echo "=== Debugging Staging Container ==="
echo ""

# 1. Check if port 8080 is listening INSIDE the container
echo "[1/5] Checking if port 8080 is listening inside container:"
sudo docker exec zana-staging ss -tlnp | grep 8080 || echo "Port 8080 NOT listening inside container!"
echo ""

# 2. Check if the web app process is running
echo "[2/5] Checking for uvicorn/python processes:"
sudo docker exec zana-staging ps aux | grep -E "(uvicorn|python.*webapp|python.*api)" | grep -v grep || echo "No web app process found"
echo ""

# 3. Check recent error logs
echo "[3/5] Checking for errors in logs (last 50 lines):"
sudo docker logs --tail=50 zana-staging 2>&1 | grep -i -E "(error|exception|failed|traceback)" | tail -20 || echo "No obvious errors found"
echo ""

# 4. Try to curl from INSIDE the container
echo "[4/5] Testing from inside container:"
sudo docker exec zana-staging curl -s http://localhost:8080/api/health || echo "Failed to connect from inside container"
echo ""

# 5. Check environment variables
echo "[5/5] Checking WEBAPP environment variables:"
sudo docker exec zana-staging env | grep -E "(WEBAPP|ENVIRONMENT)" || echo "No WEBAPP env vars found"
echo ""

# 6. Check if static files exist
echo "[6/6] Checking if static files exist:"
sudo docker exec zana-staging ls -la /app/webapp_frontend/dist 2>&1 | head -10 || echo "Static files directory not found"
echo ""

echo "=== Summary ==="
echo "If port 8080 is NOT listening inside the container, the web app server failed to start."
echo "Check the full logs: sudo docker logs zana-staging"
